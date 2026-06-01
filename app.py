import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
import database as db

# ─── Cached DB reads (TTL 30s, cleared on any write) ─────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def _expenses(m, y):      return db.get_expenses(month=m, year=y)

@st.cache_data(ttl=30, show_spinner=False)
def _budgets(m, y):       return db.get_budgets(month=m, year=y)

def _spending(m, y):
    return db.calculate_spending_by_person_category(m, y, expenses=_expenses(m, y))

def _balance(m, y):
    exp  = _expenses(m, y) if m is not None else None
    sett = _settlements(m, y) if m is not None else None
    return db.calculate_debt_balance(m, y, expenses=exp, settlements=sett, manual=_manual_debts())

def _daily(m, y):
    return db.get_daily_spending(m, y, expenses=_expenses(m, y))

@st.cache_data(ttl=30, show_spinner=False)
def _settlements(m, y):   return db.get_settlements(month=m, year=y)

@st.cache_data(ttl=30, show_spinner=False)
def _manual_debts():      return db.get_manual_debts(only_pending=True)

@st.cache_data(ttl=60, show_spinner=False)
def _categories():        return db.get_categories()

def _clear_cache():
    _expenses.clear(); _budgets.clear(); _spending.clear()
    _balance.clear();  _daily.clear();   _settlements.clear()
    _manual_debts.clear(); _categories.clear()

st.set_page_config(
    page_title="Budget Tracker · SG & AZ",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    db.init_db()
except Exception as _db_err:
    st.error(f"❌ Error de conexión a la base de datos:\n\n```\n{_db_err}\n```")
    st.info("Verificá que el secret DATABASE_URL esté correctamente configurado en Streamlit Cloud.")
    st.stop()

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main .block-container { padding-top: 1rem; padding-bottom: 2rem; }

  div[data-testid="stMetric"] {
    background: #ffffff;
    border-radius: 12px;
    padding: .9rem 1.1rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.08);
    border-top: 3px solid #667eea;
  }

  .sec-head {
    font-size: .95rem; font-weight: 700; color: #2d3748;
    border-bottom: 2px solid #e8f0fe;
    padding-bottom: 5px; margin-bottom: 10px;
  }

  .debt-card {
    border-radius: 12px; padding: 1.2rem 1.6rem;
    font-size: 1.05rem; font-weight: 700;
    text-align: center; margin-bottom: .8rem;
  }
  .debt-owe  { background:#fff5f5; border:2px solid #fc8181; color:#c53030; }
  .debt-even { background:#f0fff4; border:2px solid #68d391; color:#276749; }
  .debt-recv { background:#ebf8ff; border:2px solid #63b3ed; color:#2b6cb0; }

  .badge {
    display:inline-block; padding:2px 9px; border-radius:10px; font-size:11px; font-weight:600;
  }

  /* Pill filter */
  div[data-testid="stRadio"] > div { flex-direction: row !important; gap: 8px; }
  div[data-testid="stRadio"] label { cursor: pointer; }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💰 Budget Tracker")
    st.markdown("**Santiago & Alex**")
    st.divider()

    now   = datetime.now()
    years = list(range(now.year - 1, now.year + 2))
    month_names = list(db.MONTHS_ES.values())
    months_inv  = {v: k for k, v in db.MONTHS_ES.items()}

    sel_year       = st.selectbox("Año", years, index=years.index(now.year))
    sel_month_name = st.selectbox("Mes", month_names, index=now.month - 1)
    M = months_inv[sel_month_name]
    Y = sel_year

    st.divider()
    st.caption(f"📅 {sel_month_name} {sel_year}")

    # ── Export ────────────────────────────────────────────────────────────────
    export_key = f"excel_{M}_{Y}"
    if st.button("📊 Generar Excel", use_container_width=True, key="gen_excel"):
        try:
            st.session_state["excel_bytes"] = db.build_excel_export(M, Y)
            st.session_state["excel_key"]   = export_key
            st.session_state["excel_name"]  = f"presupuesto_{sel_month_name}_{Y}.xlsx"
        except Exception as e:
            st.error(f"Error al generar: {e}")

    if st.session_state.get("excel_key") == export_key and "excel_bytes" in st.session_state:
        st.download_button(
            label="📥 Descargar Excel",
            data=st.session_state["excel_bytes"],
            file_name=st.session_state["excel_name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="dl_excel",
        )

    st.caption("v1.2 · SG & AZ")


# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_dash, tab_gastos, tab_presup, tab_deudas = st.tabs(
    ["📊  Dashboard", "💸  Gastos", "📋  Presupuesto", "🤝  Deudas"]
)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def debt_html(balance: float, suffix: str = "") -> str:
    a = abs(balance)
    if balance > 0.01:
        return f'<div class="debt-card debt-owe">Alex debe a Santiago{suffix}<br><b>${a:,.2f}</b></div>'
    elif balance < -0.01:
        return f'<div class="debt-card debt-recv">Santiago debe a Alex{suffix}<br><b>${a:,.2f}</b></div>'
    return f'<div class="debt-card debt-even">✅ Sin deudas{suffix}</div>'


def progress_chart(persons: list, budgets_df: pd.DataFrame, spending_df: pd.DataFrame) -> go.Figure:
    """Stacked horizontal bars: spent + remaining (+ excess in red)."""
    rows = []
    for person in persons:
        for _, brow in budgets_df[budgets_df[f"budget_{person}"] > 0].iterrows():
            budget = brow[f"budget_{person}"]
            sp = spending_df[
                (spending_df["person"] == person) & (spending_df["category_name"] == brow["category_name"])
            ]
            spent = sp["spent"].sum() if not sp.empty else 0.0
            pct   = (spent / budget * 100) if budget > 0 else 0
            name  = db.PERSON_NAMES[person]
            label = brow["category_name"] if len(persons) == 1 else f"{brow['category_name']}  ·  {name}"
            rows.append({
                "label":   label,
                "budget":  budget,
                "spent":   min(spent, budget),
                "over":    max(0.0, spent - budget),
                "total":   spent,
                "pct":     pct,
                "color":   "#fc8181" if spent > budget else ("#f6ad55" if pct >= 80 else "#667eea"),
            })

    if not rows:
        return None

    df = pd.DataFrame(rows).sort_values("total", ascending=True)

    fig = go.Figure()
    # Spent segment
    fig.add_trace(go.Bar(
        name="Gastado", x=df["spent"], y=df["label"], orientation="h",
        marker=dict(color=df["color"].tolist(), line_width=0),
        customdata=list(zip(df["total"], df["budget"], df["pct"])),
        hovertemplate="<b>%{y}</b><br>Gastado: $%{customdata[0]:,.2f} / $%{customdata[1]:,.2f}<br>%{customdata[2]:.1f}%<extra></extra>",
    ))
    # Remaining segment — carries hover for when spent=0 (zero-width gastado bar is not hoverable)
    fig.add_trace(go.Bar(
        name="Restante", x=(df["budget"] - df["spent"]).clip(lower=0), y=df["label"],
        orientation="h", marker=dict(color="#e8edf7", line_width=0),
        customdata=list(zip(df["total"], df["budget"], df["pct"])),
        hovertemplate="<b>%{y}</b><br>Gastado: $%{customdata[0]:,.2f} / $%{customdata[1]:,.2f}<br>%{customdata[2]:.1f}%<extra></extra>",
        showlegend=True,
    ))
    # Over-budget segment
    fig.add_trace(go.Bar(
        name="Exceso", x=df["over"], y=df["label"],
        orientation="h", marker=dict(color="#fc8181", opacity=0.85, line_width=0),
        hovertemplate="<b>%{y}</b><br>Exceso: $%{x:,.2f}<extra></extra>",
    ))

    chart_h = max(280, len(df) * 26 + 70)
    fig.update_layout(
        barmode="stack",
        height=chart_h,
        margin=dict(l=0, r=20, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="Monto ($)", gridcolor="#f0f0f0", tickprefix="$"),
        yaxis=dict(showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        bargap=0.25,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 · DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    expenses_df = _expenses(M, Y)
    budgets_df  = _budgets(M, Y)
    spending_df = _spending(M, Y)
    balance     = _balance(M, Y)

    # ── Person filter ─────────────────────────────────────────────────────────
    hdr, filter_col = st.columns([3, 2])
    hdr.markdown(f"## {sel_month_name} {sel_year}")
    with filter_col:
        st.markdown("&nbsp;")
        dash_filter = st.radio(
            "Persona", ["Ambos", "Santiago (SG)", "Alex (AZ)"],
            horizontal=True, label_visibility="collapsed", key="dash_filter",
        )

    if dash_filter == "Santiago (SG)":
        persons_dash = ["SG"]
    elif dash_filter == "Alex (AZ)":
        persons_dash = ["AZ"]
    else:
        persons_dash = ["SG", "AZ"]

    st.divider()

    # ── KPI cards ─────────────────────────────────────────────────────────────
    n_cols = len(persons_dash) * 3
    kpi_cols = st.columns(n_cols)
    col_idx  = 0
    for person in persons_dash:
        name   = db.PERSON_NAMES[person]
        budget = budgets_df[f"budget_{person}"].sum() if not budgets_df.empty else 0.0
        spent  = (
            spending_df[spending_df["person"] == person]["spent"].sum()
            if not spending_df.empty else 0.0
        )
        remaining = budget - spent

        kpi_cols[col_idx].metric(f"💼 Presupuesto {name}", f"${budget:,.0f}")
        kpi_cols[col_idx + 1].metric(
            f"💸 Gastado {name}", f"${spent:,.2f}",
            delta=f"${remaining:,.2f} restante",
            delta_color="normal" if remaining >= 0 else "inverse",
        )
        kpi_cols[col_idx + 2].metric(f"✅ Restante {name}", f"${remaining:,.2f}")
        col_idx += 3

    # Debt chip
    st.markdown("")
    st.markdown(debt_html(balance, " · este mes"), unsafe_allow_html=True)

    st.divider()

    # ── Progress bars (Plotly) ────────────────────────────────────────────────
    if not budgets_df.empty:
        st.markdown('<div class="sec-head">Progreso de Presupuesto</div>', unsafe_allow_html=True)

        if len(persons_dash) == 2:
            c_sg, c_az = st.columns(2)
            for person, col in [("SG", c_sg), ("AZ", c_az)]:
                with col:
                    st.markdown(f"**{db.PERSON_NAMES[person]}**")
                    fig_prog = progress_chart([person], budgets_df, spending_df)
                    if fig_prog:
                        st.plotly_chart(fig_prog, use_container_width=True, config={"displayModeBar": False})
                    else:
                        st.caption("Sin presupuesto configurado.")
        else:
            person = persons_dash[0]
            st.markdown(f"**{db.PERSON_NAMES[person]}**")
            fig_prog = progress_chart([person], budgets_df, spending_df)
            if fig_prog:
                st.plotly_chart(fig_prog, use_container_width=True, config={"displayModeBar": False})
            else:
                st.caption("Sin presupuesto configurado.")

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    if not expenses_df.empty:
        c_left, c_right = st.columns([3, 2])

        with c_left:
            st.markdown('<div class="sec-head">Gastos Diarios</div>', unsafe_allow_html=True)
            daily = _daily(M, Y)
            if not daily.empty:
                if len(persons_dash) < 2:
                    daily = daily[daily["person"] == persons_dash[0]]
                daily["Persona"] = daily["person"].map(db.PERSON_NAMES)
                fig_daily = px.area(
                    daily, x="date", y="amount", color="Persona",
                    color_discrete_map={"Santiago": "#667eea", "Alex": "#f093fb"},
                    labels={"amount": "Monto ($)", "date": "Fecha"},
                    markers=True,
                )
                fig_daily.update_layout(
                    height=270, margin=dict(l=0, r=0, t=10, b=0),
                    legend_title="", plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                fig_daily.update_xaxes(
                    showgrid=False,
                    type="date",
                    tickformat="%d %b",   # e.g. "28 May" — never shows hours
                    dtick="D1",           # one tick per day
                )
                fig_daily.update_yaxes(gridcolor="#f0f0f0")
                st.plotly_chart(fig_daily, use_container_width=True, config={"displayModeBar": False})

        with c_right:
            st.markdown('<div class="sec-head">Top Categorías</div>', unsafe_allow_html=True)
            if not spending_df.empty:
                filtered_sp = spending_df[spending_df["person"].isin(persons_dash)]
                cat_totals = (
                    filtered_sp.groupby("category_name")["spent"]
                    .sum().sort_values(ascending=False).head(8)
                )
                if not cat_totals.empty:
                    fig_pie = px.pie(
                        values=cat_totals.values, names=cat_totals.index,
                        hole=0.42,
                        color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig_pie.update_layout(
                        height=270, margin=dict(l=0, r=0, t=10, b=0),
                        showlegend=True,
                        legend=dict(orientation="v", font_size=10),
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    )
                    fig_pie.update_traces(
                        textposition="inside", textinfo="percent",
                        hovertemplate="<b>%{label}</b><br>$%{value:,.2f}<br>%{percent}<extra></extra>",
                    )
                    st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No hay gastos registrados para este mes. Empieza en la pestaña 💸 Gastos.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 · GASTOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_gastos:
    col_form, col_list = st.columns([1, 2], gap="large")

    with col_form:
        st.markdown('<div class="sec-head">➕ Nuevo Gasto</div>', unsafe_allow_html=True)
        cats_df       = _categories()
        cat_name_to_id = dict(zip(cats_df["name"], cats_df["id"]))

        with st.form("new_expense", clear_on_submit=True):
            description = st.text_input("Descripción *", placeholder="Ej: Almuerzo, Supermercado…")

            c1, c2 = st.columns(2)
            cat_name = c1.selectbox("Categoría *", list(cat_name_to_id.keys()))
            payer    = c2.selectbox("Pagó *", db.PERSONS,
                                    format_func=lambda x: f"{x} · {db.PERSON_NAMES[x]}")

            c3, c4 = st.columns(2)
            amount       = c3.number_input("Monto ($) *", min_value=0.0, value=None, step=1.0, format="%.2f")
            expense_date = c4.date_input("Fecha real *", value=date.today())

            split_type = st.selectbox(
                "Tipo de gasto *", list(db.SPLIT_TYPES.keys()),
                format_func=lambda x: db.SPLIT_TYPES[x],
            )
            st.caption({
                "personal":  "Solo cuenta para quien pagó.",
                "shared":    "Se divide 50/50 en el presupuesto de cada uno.",
                "for_other": "Lo pagó uno, pero es gasto del otro.",
            }[split_type])

            # Budget month override
            override = st.checkbox(
                "📅 Asignar a un mes de presupuesto diferente",
                help="Útil cuando el gasto es de fines de mes pero corresponde al presupuesto del mes siguiente.",
            )
            bm, by = None, None
            if override:
                co1, co2 = st.columns(2)
                bm_name = co1.selectbox("Mes presupuesto", month_names, index=M - 1, key="bm_sel")
                by      = co2.selectbox("Año presupuesto", years, index=years.index(Y), key="by_sel")
                bm      = months_inv[bm_name]

            notes = st.text_area("Notas (opcional)", height=55, placeholder="Detalles adicionales…")

            if st.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
                if not description.strip():
                    st.error("La descripción es requerida.")
                elif amount is None or amount <= 0:
                    st.error("El monto debe ser mayor a $0.")
                else:
                    db.add_expense(
                        description.strip(),
                        cat_name_to_id[cat_name],
                        payer,
                        float(amount),
                        split_type,
                        expense_date.isoformat(),
                        notes.strip() or None,
                        budget_month=bm,
                        budget_year=by,
                    )
                    st.success("✅ Gasto guardado!")
                    _clear_cache(); st.rerun()

    with col_list:
        st.markdown(f'<div class="sec-head">Gastos de {sel_month_name} {sel_year}</div>',
                    unsafe_allow_html=True)

        expenses = _expenses(M, Y)

        if expenses.empty:
            st.info("No hay gastos registrados para este mes.")
        else:
            cf1, cf2, cf3 = st.columns(3)
            with cf1:
                fp = st.multiselect("Persona", db.PERSONS,
                                    format_func=lambda x: f"{x} · {db.PERSON_NAMES[x]}")
            with cf2:
                all_cats = ["Todas"] + sorted(expenses["category_name"].unique().tolist())
                fc = st.selectbox("Categoría", all_cats)
            with cf3:
                all_types = ["Todos"] + list(db.SPLIT_TYPES.keys())
                ft = st.selectbox("Tipo", all_types,
                                  format_func=lambda x: "Todos" if x == "Todos" else db.SPLIT_TYPES[x])

            filtered = expenses.copy()
            if fp:
                filtered = filtered[filtered["payer"].isin(fp)]
            if fc != "Todas":
                filtered = filtered[filtered["category_name"] == fc]
            if ft != "Todos":
                filtered = filtered[filtered["split_type"] == ft]

            sm1, sm2, sm3 = st.columns(3)
            sm1.metric("Total pagado", f"${filtered['amount'].sum():,.2f}")
            sm2.metric("Transacciones", len(filtered))
            sm3.metric("Promedio", f"${filtered['amount'].mean():,.2f}" if not filtered.empty else "$0.00")

            st.markdown("")

            TYPE_COLORS = {"personal": "#667eea", "shared": "#f6ad55", "for_other": "#fc8181"}

            for _, row in filtered.iterrows():
                tc = TYPE_COLORS.get(row["split_type"], "#aaa")
                tl = db.SPLIT_TYPES.get(row["split_type"], row["split_type"])

                # Show budget month badge if different from real date
                bm_info = ""
                bm_val  = row.get("budget_month")
                by_val  = row.get("budget_year")
                if bm_val is not None and not (isinstance(bm_val, float) and pd.isna(bm_val)):
                    bm_label = db.MONTHS_ES.get(int(bm_val), "?")
                    bm_info  = f" · <span style='color:#3182ce;font-size:10px'>📅 Presup. {bm_label} {int(by_val)}</span>"

                notes_html = f"<br><small style='color:#aaa'>{row['notes']}</small>" if row.get("notes") else ""

                c_desc, c_tag, c_who, c_amt, c_del = st.columns([3.5, 2, 1, 1.2, 0.4])
                c_desc.markdown(
                    f"**{row['description']}**"
                    f"<br><small style='color:#888'>{row['category_name']} · {row['date']}{bm_info}</small>"
                    f"{notes_html}",
                    unsafe_allow_html=True,
                )
                c_tag.markdown(
                    f"<span class='badge' style='background:{tc}18;color:{tc}'>{tl}</span>",
                    unsafe_allow_html=True,
                )
                c_who.markdown(f"**{row['payer']}**")
                c_amt.markdown(f"**${row['amount']:,.2f}**")
                if c_del.button("🗑", key=f"del_e_{row['id']}", help="Eliminar"):
                    db.delete_expense(int(row["id"]))
                    _clear_cache(); st.rerun()
                st.markdown("<hr style='margin:2px 0;border-color:#f5f5f5'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 · PRESUPUESTO
# ══════════════════════════════════════════════════════════════════════════════
with tab_presup:
    st.markdown(f"## Presupuesto · {sel_month_name} {sel_year}")

    prev_m    = M - 1 if M > 1 else 12
    prev_y    = Y if M > 1 else Y - 1
    prev_name = db.MONTHS_ES[prev_m]

    cp_col, _ = st.columns([1, 3])
    if cp_col.button(f"📋 Copiar desde {prev_name} {prev_y}"):
        db.copy_budgets_from_month(prev_m, prev_y, M, Y)
        st.success(f"✅ Copiado desde {prev_name} {prev_y}")
        _clear_cache(); st.rerun()

    st.divider()

    budgets_df = _budgets(M, Y)
    edit_df    = budgets_df[["category_name", "budget_SG", "budget_AZ"]].copy()
    edit_df    = edit_df.rename(columns={
        "category_name": "Categoría",
        "budget_SG": "Santiago (SG) $",
        "budget_AZ": "Alex (AZ) $",
    })

    edited = st.data_editor(
        edit_df,
        column_config={
            "Categoría":         st.column_config.TextColumn(disabled=True, width="medium"),
            "Santiago (SG) $":   st.column_config.NumberColumn(min_value=0.0, format="$ %.2f", step=10.0),
            "Alex (AZ) $":       st.column_config.NumberColumn(min_value=0.0, format="$ %.2f", step=10.0),
        },
        hide_index=True,
        use_container_width=True,
        height=min(900, (len(edit_df) + 1) * 36 + 40),
        key="budget_editor",
    )

    total_sg = edited["Santiago (SG) $"].sum()
    total_az = edited["Alex (AZ) $"].sum()
    st.markdown(f"**Total Santiago:** ${total_sg:,.2f} &nbsp;&nbsp; **Total Alex:** ${total_az:,.2f}", unsafe_allow_html=True)

    if st.button("💾 Guardar Presupuesto", type="primary"):
        for idx, row in edited.iterrows():
            cat_id = int(budgets_df.iloc[idx]["category_id"])
            db.set_budget(cat_id, "SG", float(row["Santiago (SG) $"]), M, Y)
            db.set_budget(cat_id, "AZ", float(row["Alex (AZ) $"]),    M, Y)
        st.success("✅ Presupuesto guardado!")
        _clear_cache(); st.rerun()

    st.divider()

    # ── Category management ───────────────────────────────────────────────────
    st.markdown('<div class="sec-head">⚙️ Gestionar Categorías</div>', unsafe_allow_html=True)

    cat_col_new, cat_col_list = st.columns([1, 2], gap="large")

    with cat_col_new:
        st.markdown("**Nueva categoría**")
        with st.form("new_category_form", clear_on_submit=True):
            new_cat_name  = st.text_input("Nombre *", placeholder="Ej: Mascotas, Médico…")
            new_cat_color = st.color_picker("Color", value="#667eea")
            if st.form_submit_button("➕ Crear categoría", use_container_width=True, type="primary"):
                ok, msg = db.add_category(new_cat_name, new_cat_color)
                if ok:
                    st.success(msg)
                    _clear_cache(); st.rerun()
                else:
                    st.error(msg)

    with cat_col_list:
        st.markdown("**Categorías existentes**")
        all_cats = _categories()
        default_names = {c[0] for c in db.DEFAULT_CATEGORIES}
        edit_cat_id = st.session_state.get("edit_cat_id")

        for _, cat in all_cats.iterrows():
            is_default = cat["name"] in default_names
            cat_id_int = int(cat["id"])

            if edit_cat_id == cat_id_int:
                # Inline edit row
                ec1, ec2, ec3, ec4 = st.columns([2.5, 1.5, 0.5, 0.5])
                new_name  = ec1.text_input("Nombre", value=cat["name"],
                                           key=f"ecn_{cat_id_int}", label_visibility="collapsed")
                new_color = ec2.color_picker("Color", value=cat["color"],
                                             key=f"ecc_{cat_id_int}", label_visibility="collapsed")
                if ec3.button("✅", key=f"save_cat_{cat_id_int}", help="Guardar"):
                    ok, msg = db.update_category(cat_id_int, new_name.strip(), new_color)
                    if ok:
                        st.session_state["edit_cat_id"] = None
                        _clear_cache(); st.rerun()
                    else:
                        st.error(msg)
                if ec4.button("✖", key=f"cancel_cat_{cat_id_int}", help="Cancelar"):
                    st.session_state["edit_cat_id"] = None
                    _clear_cache(); st.rerun()
            else:
                c1, c2, c3, c4 = st.columns([0.4, 2.8, 0.7, 0.7])
                c1.markdown(
                    f"<div style='width:18px;height:18px;border-radius:50%;"
                    f"background:{cat['color']};margin-top:6px'></div>",
                    unsafe_allow_html=True,
                )
                c2.markdown(cat["name"])
                if c3.button("✏️", key=f"edit_cat_{cat_id_int}", help="Editar nombre y color"):
                    st.session_state["edit_cat_id"] = cat_id_int
                    _clear_cache(); st.rerun()
                if not is_default:
                    if c4.button("🗑", key=f"del_cat_{cat_id_int}", help="Eliminar categoría"):
                        ok, msg = db.delete_category(cat_id_int)
                        if ok:
                            st.success(msg)
                            _clear_cache(); st.rerun()
                        else:
                            st.warning(msg)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 4 · DEUDAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_deudas:
    st.markdown(f"## 🤝 Deudas · {sel_month_name} {sel_year}")

    balance     = _balance(M, Y)
    balance_all = _balance(None, None)
    manual_df   = _manual_debts()

    kd1, kd2 = st.columns(2)
    with kd1:
        st.markdown("### Este mes")
        st.markdown(debt_html(balance, " · este mes"), unsafe_allow_html=True)
    with kd2:
        st.markdown("### Acumulado total")
        st.markdown(debt_html(balance_all, " · total"), unsafe_allow_html=True)

    st.divider()

    # ── Three column layout ───────────────────────────────────────────────────
    col_shared, col_manual, col_pay = st.columns([2, 2, 1.4], gap="medium")

    # ── Shared / for-other expenses ───────────────────────────────────────────
    with col_shared:
        st.markdown('<div class="sec-head">Gastos Compartidos / Para el Otro</div>',
                    unsafe_allow_html=True)
        exp_this = _expenses(M, Y)
        shared_exp = (
            exp_this[exp_this["split_type"].isin(["shared", "for_other"])]
            if not exp_this.empty else pd.DataFrame()
        )
        if shared_exp.empty:
            st.info("Sin gastos compartidos este mes.")
        else:
            for _, row in shared_exp.iterrows():
                other      = "AZ" if row["payer"] == "SG" else "SG"
                bc         = "#f6ad55" if row["split_type"] == "shared" else "#fc8181"
                tl         = db.SPLIT_TYPES[row["split_type"]]
                debt_amt   = row["amount"] / 2 if row["split_type"] == "shared" else row["amount"]
                reconciled = (row.get("is_reconciled") or 0) == 1
                fade       = "opacity:0.4;" if reconciled else ""
                c1, c2, c3 = st.columns([2.5, 1.8, 1.0])
                c1.markdown(
                    f"<div style='{fade}'>"
                    f"<b>{row['description']}</b> — ${row['amount']:,.2f}<br>"
                    f"<small style='color:#888'>{row['category_name']} · {row['date']} · Pagó {row['payer']}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                c2.markdown(
                    f"<div style='{fade}'>"
                    f"<span class='badge' style='background:{bc}18;color:{bc}'>{tl}</span><br>"
                    f"<small style='color:#888'>{other} debe ${debt_amt:,.2f}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if reconciled:
                    if c3.button("↩ Deshacer", key=f"unrec_{row['id']}", help="Deshacer conciliación", use_container_width=True):
                        db.reconcile_expense(int(row["id"]), reconciled=False)
                        _clear_cache(); st.rerun()
                else:
                    if c3.button("✅ Conciliar", key=f"rec_{row['id']}", help="Marcar como saldado (excluye del balance)", use_container_width=True):
                        db.reconcile_expense(int(row["id"]), reconciled=True)
                        _clear_cache(); st.rerun()
                st.markdown("<hr style='margin:3px 0;border-color:#f5f5f5'>", unsafe_allow_html=True)

    # ── Manual debts ──────────────────────────────────────────────────────────
    with col_manual:
        st.markdown('<div class="sec-head">Deudas Manuales (fuera de presupuesto)</div>',
                    unsafe_allow_html=True)

        with st.expander("➕ Nueva deuda manual"):
            with st.form("manual_debt_form", clear_on_submit=True):
                md_desc    = st.text_input("Descripción *", placeholder="Ej: Plata prestada, entrada concierto…")
                md_c1, md_c2 = st.columns(2)
                md_debtor  = md_c1.selectbox("Quien debe", db.PERSONS,
                                              format_func=lambda x: f"{x} · {db.PERSON_NAMES[x]}",
                                              key="md_debtor")
                md_creditor_val = "AZ" if md_debtor == "SG" else "SG"
                md_c2.markdown(f"**A quien:** {md_creditor_val} · {db.PERSON_NAMES[md_creditor_val]}")
                md_amount  = st.number_input("Monto ($) *", min_value=0.01, value=None, step=1.0, format="%.2f", key="md_amt")
                md_date    = st.date_input("Fecha", value=date.today(), key="md_date")

                if st.form_submit_button("💾 Agregar deuda", use_container_width=True, type="primary"):
                    if not md_desc.strip():
                        st.error("La descripción es requerida.")
                    elif md_amount is None or md_amount <= 0:
                        st.error("El monto debe ser mayor a $0.")
                    else:
                        db.add_manual_debt(md_debtor, md_creditor_val, float(md_amount),
                                           md_desc.strip(), md_date.isoformat())
                        st.success("✅ Deuda registrada!")
                        _clear_cache(); st.rerun()

        if manual_df.empty:
            st.caption("Sin deudas manuales pendientes.")
        else:
            for _, row in manual_df.iterrows():
                creditor_name = db.PERSON_NAMES[row["creditor"]]
                debtor_name   = db.PERSON_NAMES[row["debtor"]]
                c1, c2, c3 = st.columns([3, 1.5, 0.8])
                c1.markdown(
                    f"**{row['description']}**<br>"
                    f"<small style='color:#888'>{debtor_name} → {creditor_name} · {row['date']}</small>",
                    unsafe_allow_html=True,
                )
                c2.markdown(f"**${row['amount']:,.2f}**")
                btn_col1, btn_col2 = c3.columns(2)
                if btn_col1.button("✅", key=f"settle_md_{row['id']}", help="Marcar como saldada"):
                    db.settle_manual_debt(int(row["id"]))
                    _clear_cache(); st.rerun()
                if btn_col2.button("🗑", key=f"del_md_{row['id']}", help="Eliminar"):
                    db.delete_manual_debt(int(row["id"]))
                    _clear_cache(); st.rerun()
                st.markdown("<hr style='margin:3px 0;border-color:#f5f5f5'>", unsafe_allow_html=True)

    # ── Registrar pago / historial ────────────────────────────────────────────
    with col_pay:
        st.markdown('<div class="sec-head">💳 Registrar Pago</div>', unsafe_allow_html=True)

        # Default direction based on balance
        default_from = "AZ" if balance >= 0 else "SG"
        suggested    = max(0.01, round(abs(balance), 2))   # ← fix: never below 0.01

        with st.form("settlement_form", clear_on_submit=True):
            s_from = st.selectbox(
                "Quien paga", db.PERSONS,
                index=db.PERSONS.index(default_from),
                format_func=lambda x: f"{x} · {db.PERSON_NAMES[x]}",
            )
            s_to_val = "AZ" if s_from == "SG" else "SG"
            st.markdown(f"**Pago a:** {s_to_val} · {db.PERSON_NAMES[s_to_val]}")

            s_amount = st.number_input("Monto ($)", min_value=0.01,
                                       value=suggested, step=1.0, format="%.2f")
            s_desc  = st.text_input("Descripción", value="Liquidación de deudas")
            s_date  = st.date_input("Fecha", value=date.today())

            if st.form_submit_button("✅ Registrar", use_container_width=True, type="primary"):
                db.add_settlement(s_from, s_to_val, float(s_amount), s_desc, s_date.isoformat())
                st.success("✅ Pago registrado!")
                _clear_cache(); st.rerun()

        st.markdown("")
        st.markdown('<div class="sec-head">Historial de Pagos</div>', unsafe_allow_html=True)
        settlements = _settlements(M, Y)
        if settlements.empty:
            st.caption("Sin pagos este mes.")
        else:
            for _, row in settlements.iterrows():
                c1, c2, c3 = st.columns([2.5, 2, 0.4])
                c1.markdown(
                    f"**{row['from_person']}** → **{row['to_person']}**<br>"
                    f"<small style='color:#888'>{row['date']}</small>",
                    unsafe_allow_html=True,
                )
                c2.markdown(f"${row['amount']:,.2f}<br><small>{row['description']}</small>",
                            unsafe_allow_html=True)
                if c3.button("🗑", key=f"del_s_{row['id']}"):
                    db.delete_settlement(int(row["id"]))
                    _clear_cache(); st.rerun()
                st.markdown("<hr style='margin:3px 0;border-color:#f5f5f5'>", unsafe_allow_html=True)
