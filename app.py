import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
import database as db

# ─── Cached DB reads ──────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def _expenses(m, y):    return db.get_expenses(month=m, year=y)

@st.cache_data(ttl=30, show_spinner=False)
def _all_expenses():    return db.get_expenses()

@st.cache_data(ttl=30, show_spinner=False)
def _budgets(m, y):     return db.get_budgets(month=m, year=y)

@st.cache_data(ttl=30, show_spinner=False)
def _settlements(m, y): return db.get_settlements(month=m, year=y)

@st.cache_data(ttl=30, show_spinner=False)
def _all_settlements(): return db.get_settlements()

@st.cache_data(ttl=30, show_spinner=False)
def _manual_debts():    return db.get_manual_debts(only_pending=True)

@st.cache_data(ttl=60, show_spinner=False)
def _categories():      return db.get_categories()

@st.cache_data(ttl=30, show_spinner=False)
def _savings_bal(person):        return db.get_savings_balance(person)

@st.cache_data(ttl=30, show_spinner=False)
def _savings_entries(person=None): return db.get_savings(person)

def _spending(m, y):
    return db.calculate_spending_by_person_category(m, y, expenses=_expenses(m, y))

def _period_balance(m, y):
    return db.calculate_period_balance(m, y, expenses=_expenses(m, y), settlements=_settlements(m, y))

def _accum_balance():
    all_exp  = _all_expenses()
    rec_exp  = all_exp[all_exp["is_reconciled"].fillna(0) == 1] if not all_exp.empty else all_exp
    all_sett = _all_settlements()
    accum_s  = (all_sett[all_sett["debt_type"] == "accumulated"]
                if not all_sett.empty and "debt_type" in all_sett.columns else all_sett.iloc[0:0])
    return db.calculate_accumulated_balance(reconciled_expenses=rec_exp, manual=_manual_debts(),
                                            accumulated_settlements=accum_s)

def _daily(m, y):
    return db.get_daily_spending(m, y, expenses=_expenses(m, y))

def _clear_cache():
    _expenses.clear(); _all_expenses.clear(); _budgets.clear()
    _settlements.clear(); _all_settlements.clear()
    _manual_debts.clear(); _categories.clear()
    _savings_bal.clear(); _savings_entries.clear()

st.set_page_config(
    page_title="El jardín 🪲 · SG & AZ",
    page_icon="🪲",
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
    background: #1e2130;
    border-radius: 12px;
    padding: .9rem 1.1rem;
    box-shadow: 0 1px 8px rgba(0,0,0,0.4);
    border-top: 3px solid #667eea;
  }

  .sec-head {
    font-size: .95rem; font-weight: 700; color: #a0aec0;
    border-bottom: 2px solid #2d3748;
    padding-bottom: 5px; margin-bottom: 10px;
  }

  .debt-card {
    border-radius: 12px; padding: 1.2rem 1.6rem;
    font-size: 1.05rem; font-weight: 700;
    text-align: center; margin-bottom: .8rem;
  }
  .debt-owe  { background:#2d1515; border:2px solid #fc8181; color:#fc8181; }
  .debt-even { background:#1a2e22; border:2px solid #68d391; color:#68d391; }
  .debt-recv { background:#152233; border:2px solid #63b3ed; color:#63b3ed; }

  .badge {
    display:inline-block; padding:2px 9px; border-radius:10px; font-size:11px; font-weight:600;
  }

  div[data-testid="stRadio"] > div { flex-direction: row !important; gap: 8px; }
  div[data-testid="stRadio"] label { cursor: pointer; }

  hr { border-color: #2d3748 !important; }

  /* Vertically center button columns in expense rows */
  div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:has(.stButton) {
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:has(.stButton) button {
    padding: 2px 6px;
    line-height: 1;
  }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🪲 El jardín")
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
    try:
        excel_bytes = db.build_excel_export(M, Y)
        st.download_button(
            label="📥 Descargar Excel",
            data=excel_bytes,
            file_name=f"presupuesto_{sel_month_name}_{Y}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="dl_excel",
        )
    except Exception as e:
        st.caption(f"Excel no disponible: {e}")

    st.caption("v1.2 · SG & AZ")


# ─── Fragment: formulario nuevo gasto ────────────────────────────────────────
@st.fragment
def _new_expense_panel(M: int, Y: int, cat_name_to_id: dict):
    _SAVINGS_CATS = {"Spain Move Fund", "Emergency Savings", "Viajes"}
    _SPLIT_CAPTIONS = {
        "personal":  "Solo cuenta para quien pagó.",
        "shared":    "Se divide 50/50 en el presupuesto de cada uno.",
        "for_other": "Lo pagó uno, pero es gasto del otro.",
        "custom":    "Elegí qué porcentaje paga el otro.",
    }
    if "nexp_fk" not in st.session_state:
        st.session_state["nexp_fk"] = 0
    fk = st.session_state["nexp_fk"]

    description  = st.text_input("Descripción", placeholder="Ej: Almuerzo, Supermercado…",
                                 key=f"nexp_desc_{fk}")
    nc1, nc2 = st.columns(2)
    cat_name = nc1.selectbox("Categoría", list(cat_name_to_id.keys()), key=f"nexp_cat_{fk}")
    payer    = nc2.selectbox("Pagó", db.PERSONS,
                             format_func=lambda x: f"{x} · {db.PERSON_NAMES[x]}",
                             key=f"nexp_payer_{fk}")
    nc3, nc4 = st.columns(2)
    amount       = nc3.number_input("Monto ($)", min_value=0.0, value=None, step=1.0,
                                    format="%.2f", key=f"nexp_amount_{fk}")
    expense_date = nc4.date_input("Fecha real", value=date.today(), key=f"nexp_date_{fk}")

    split_type = st.selectbox(
        "Tipo de gasto", list(db.SPLIT_TYPES.keys()),
        format_func=lambda x: db.SPLIT_TYPES[x],
        key=f"nexp_split_{fk}",
    )
    st.caption(_SPLIT_CAPTIONS[split_type])
    split_pct = None
    if split_type == "custom":
        split_pct = st.slider("% que paga el otro", 0, 100, 50, step=5,
                              key=f"nexp_pct_{fk}",
                              help="Ej: 30 → el otro paga el 30%, vos el 70%")

    notes = st.text_area("Notas (opcional)", height=55, placeholder="Detalles adicionales…",
                         key=f"nexp_notes_{fk}")

    st.caption(f"📅 Se asignará al presupuesto de **{db.MONTHS_ES[M]} {Y}**")
    if cat_name in _SAVINGS_CATS:
        st.info("💰 Esta categoría también agregará el monto a Ahorros automáticamente.")

    if st.button("💾 Guardar", use_container_width=True, type="primary", key="nexp_save"):
        if not description.strip():
            st.error("La descripción es requerida.")
        elif amount is None or amount <= 0:
            st.error("El monto debe ser mayor a $0.")
        else:
            bm = M if (expense_date.month != M or expense_date.year != Y) else None
            by = Y if bm is not None else None
            new_exp_id = db.add_expense(
                description.strip(), cat_name_to_id[cat_name], payer, float(amount),
                split_type, expense_date.isoformat(), notes.strip() or None,
                budget_month=bm, budget_year=by,
                split_pct=float(split_pct) if split_pct is not None else None,
            )
            if cat_name in _SAVINGS_CATS:
                amt    = float(amount)
                desc_s = f"{cat_name}: {description.strip()}"
                other  = "AZ" if payer == "SG" else "SG"
                opct   = (float(split_pct) / 100) if split_pct is not None else 0.5
                if split_type == "personal":
                    db.add_savings_entry(payer, amt, "deposit", desc_s, expense_date.isoformat(), expense_id=new_exp_id)
                elif split_type == "shared":
                    db.add_savings_entry(payer, amt * 0.5, "deposit", desc_s, expense_date.isoformat(), expense_id=new_exp_id)
                    db.add_savings_entry(other, amt * 0.5, "deposit", desc_s, expense_date.isoformat(), expense_id=new_exp_id)
                elif split_type == "for_other":
                    db.add_savings_entry(other, amt, "deposit", desc_s, expense_date.isoformat(), expense_id=new_exp_id)
                elif split_type == "custom":
                    db.add_savings_entry(payer, amt * (1 - opct), "deposit", desc_s, expense_date.isoformat(), expense_id=new_exp_id)
                    db.add_savings_entry(other, amt * opct,        "deposit", desc_s, expense_date.isoformat(), expense_id=new_exp_id)
            st.session_state["nexp_fk"] += 1
            _clear_cache()
            st.rerun()  # full app rerun para refrescar lista


# ─── Fragment: lista de movimientos ──────────────────────────────────────────
@st.fragment
def _expense_list_panel(M: int, Y: int, cat_name_to_id: dict,
                        sel_month_name: str, sel_year: int,
                        years: list, month_names: list, months_inv: dict):
    st.markdown(f'<div class="sec-head">Movimientos de {sel_month_name} {sel_year}</div>',
                unsafe_allow_html=True)

    expenses = _expenses(M, Y)

    if expenses.empty:
        st.info("No hay movimientos registrados para este mes.")
        return

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
    sm1.metric("Total movimientos ($)", f"${filtered['amount'].sum():,.0f}")
    sm2.metric("Transacciones", len(filtered))
    sm3.metric("Promedio", f"${filtered['amount'].mean():,.0f}" if not filtered.empty else "$0.00")

    st.markdown("")

    TYPE_COLORS = {"personal": "#667eea", "shared": "#f6ad55", "for_other": "#fc8181"}
    SAVINGS_CATS = {"Spain Move Fund", "Emergency Savings", "Viajes"}

    for _, row in filtered.iterrows():
        row_id = int(row["id"])
        editing = st.session_state.get("edit_expense_id") == row_id

        if editing:
            st.markdown(
                f"<div style='background:#252d42;border-radius:10px;padding:12px 16px;margin-bottom:4px'>"
                f"<b>✏️ Editando:</b> {row['description']}</div>",
                unsafe_allow_html=True,
            )
            with st.form(f"edit_expense_form_{row_id}"):
                e_desc = st.text_input("Descripción", value=row["description"])

                ef1, ef2 = st.columns(2)
                cat_keys = list(cat_name_to_id.keys())
                e_cat_name = ef1.selectbox(
                    "Categoría", cat_keys,
                    index=cat_keys.index(row["category_name"]) if row["category_name"] in cat_keys else 0,
                )
                e_payer = ef2.selectbox(
                    "Pagó", db.PERSONS,
                    index=db.PERSONS.index(row["payer"]),
                    format_func=lambda x: f"{x} · {db.PERSON_NAMES[x]}",
                )

                ef3, ef4 = st.columns(2)
                e_amount = ef3.number_input("Monto ($)", min_value=0.0,
                                            value=float(row["amount"]), step=1.0, format="%.2f")
                e_date = ef4.date_input(
                    "Fecha real",
                    value=date.fromisoformat(str(row["date"])[:10]),
                )

                split_keys = list(db.SPLIT_TYPES.keys())
                e_split_type = st.selectbox(
                    "Tipo de gasto", split_keys,
                    index=split_keys.index(row["split_type"]) if row["split_type"] in split_keys else 0,
                    format_func=lambda x: db.SPLIT_TYPES[x],
                )

                cur_pct = int(row["split_pct"]) if (row.get("split_pct") is not None
                                                    and not pd.isna(row["split_pct"])) else 50
                e_split_pct = st.slider(
                    "% que paga el otro (solo para % Personalizado)",
                    0, 100, cur_pct, step=5,
                )

                e_bm_val = row.get("budget_month")
                e_by_val = row.get("budget_year")
                has_override = (e_bm_val is not None
                                and not (isinstance(e_bm_val, float) and pd.isna(e_bm_val)))
                e_override = st.checkbox("📅 Asignar a un mes de presupuesto diferente",
                                         value=has_override)
                e_bm, e_by = None, None
                if e_override:
                    eo1, eo2 = st.columns(2)
                    bm_idx = int(e_bm_val) - 1 if has_override else M - 1
                    by_idx = years.index(int(e_by_val)) if has_override and int(e_by_val) in years else years.index(Y)
                    e_bm_name = eo1.selectbox("Mes presupuesto", month_names, index=bm_idx,
                                               key=f"ebm_{row_id}")
                    e_by = eo2.selectbox("Año presupuesto", years, index=by_idx, key=f"eby_{row_id}")
                    e_bm = months_inv[e_bm_name]

                e_notes = st.text_area("Notas (opcional)",
                                       value=row.get("notes") or "", height=55)

                es1, es2 = st.columns(2)
                save_edit   = es1.form_submit_button("💾 Actualizar", use_container_width=True, type="primary")
                cancel_edit = es2.form_submit_button("✖ Cancelar",   use_container_width=True)

                if save_edit:
                    if not e_desc.strip():
                        st.error("La descripción es requerida.")
                    elif e_amount <= 0:
                        st.error("El monto debe ser mayor a $0.")
                    else:
                        final_split_pct = float(e_split_pct) if e_split_type == "custom" else None
                        db.update_expense(
                            row_id,
                            e_desc.strip(),
                            cat_name_to_id[e_cat_name],
                            e_payer,
                            float(e_amount),
                            e_split_type,
                            e_date.isoformat(),
                            e_notes.strip() or None,
                            e_bm, e_by,
                            final_split_pct,
                        )
                        db.delete_savings_by_expense(row_id)
                        if e_cat_name in SAVINGS_CATS:
                            amt    = float(e_amount)
                            desc_s = f"{e_cat_name}: {e_desc.strip()}"
                            other  = "AZ" if e_payer == "SG" else "SG"
                            opct   = (float(e_split_pct) / 100) if e_split_type == "custom" else 0.5
                            if e_split_type == "personal":
                                db.add_savings_entry(e_payer, amt, "deposit", desc_s, e_date.isoformat(), expense_id=row_id)
                            elif e_split_type == "shared":
                                db.add_savings_entry(e_payer, amt * 0.5, "deposit", desc_s, e_date.isoformat(), expense_id=row_id)
                                db.add_savings_entry(other,   amt * 0.5, "deposit", desc_s, e_date.isoformat(), expense_id=row_id)
                            elif e_split_type == "for_other":
                                db.add_savings_entry(other, amt, "deposit", desc_s, e_date.isoformat(), expense_id=row_id)
                            elif e_split_type == "custom":
                                db.add_savings_entry(e_payer, amt * (1 - opct), "deposit", desc_s, e_date.isoformat(), expense_id=row_id)
                                db.add_savings_entry(other,   amt * opct,        "deposit", desc_s, e_date.isoformat(), expense_id=row_id)
                        st.session_state["edit_expense_id"] = None
                        _clear_cache(); st.rerun()

                if cancel_edit:
                    st.session_state["edit_expense_id"] = None
                    st.rerun()

        else:
            tc = TYPE_COLORS.get(row["split_type"], "#aaa")
            tl = db.SPLIT_TYPES.get(row["split_type"], row["split_type"])

            bm_info = ""
            bm_val  = row.get("budget_month")
            by_val  = row.get("budget_year")
            if bm_val is not None and not (isinstance(bm_val, float) and pd.isna(bm_val)):
                bm_label = db.MONTHS_ES.get(int(bm_val), "?")
                bm_info  = f" · <span style='color:#3182ce;font-size:10px'>📅 Presup. {bm_label} {int(by_val)}</span>"

            _nv = row.get("notes")
            notes_html = (f"<br><small style='color:#aaa'>{_nv}</small>"
                          if _nv and isinstance(_nv, str) and _nv.strip() else "")

            c_desc, c_tag, c_who, c_amt, c_edit, c_del = st.columns([3.5, 2, 1, 1.2, 0.4, 0.4])
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
            c_amt.markdown(f"**${row['amount']:,.0f}**")
            if c_edit.button("✏️", key=f"edit_e_{row_id}", help="Editar",
                             use_container_width=True):
                st.session_state["edit_expense_id"] = row_id
                st.rerun()
            if c_del.button("🗑", key=f"del_e_{row_id}", help="Eliminar",
                            use_container_width=True):
                db.delete_expense(row_id)
                _clear_cache(); st.rerun()

        st.markdown("<hr style='margin:2px 0;border-color:#f5f5f5'>", unsafe_allow_html=True)


# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_gastos, tab_presup, tab_dash, tab_deudas, tab_ahorros = st.tabs(
    ["💸  Movimientos", "📋  Presupuesto", "📊  Dashboard", "🤝  Deudas", "💰  Ahorros"]
)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def debt_html(balance: float, suffix: str = "") -> str:
    a = abs(balance)
    if balance > 0.01:
        return f'<div class="debt-card debt-owe">Alex debe a Santiago{suffix}<br><b>${a:,.0f}</b></div>'
    elif balance < -0.01:
        return f'<div class="debt-card debt-recv">Santiago debe a Alex{suffix}<br><b>${a:,.0f}</b></div>'
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
                "color":   "#b03a3a" if spent > budget else ("#b07a2a" if pct >= 80 else "#4a5bb8"),
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
        orientation="h", marker=dict(color="#252d42", line_width=0),
        customdata=list(zip(df["total"], df["budget"], df["pct"])),
        hovertemplate="<b>%{y}</b><br>Gastado: $%{customdata[0]:,.2f} / $%{customdata[1]:,.2f}<br>%{customdata[2]:.1f}%<extra></extra>",
        showlegend=True,
    ))
    # Over-budget segment
    fig.add_trace(go.Bar(
        name="Exceso", x=df["over"], y=df["label"],
        orientation="h", marker=dict(color="#b03a3a", opacity=0.9, line_width=0),
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
    balance     = _period_balance(M, Y) + _accum_balance()

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

    # ── KPI cards — una fila por Santiago, Alex y Ambos ──────────────────────
    FUN_CATS = ["Salidas a comer", "Bares", "Café", "Cultura", "Miscellaneous"]

    if dash_filter == "Santiago (SG)":
        kpi_rows = [("Santiago", ["SG"])]
    elif dash_filter == "Alex (AZ)":
        kpi_rows = [("Alex", ["AZ"])]
    else:
        kpi_rows = [("Santiago", ["SG"]), ("Alex", ["AZ"]), ("Ambos", ["SG", "AZ"])]

    for row_label, row_persons in kpi_rows:
        budget = (sum(budgets_df[f"budget_{p}"].sum() for p in row_persons)
                  if not budgets_df.empty else 0.0)
        spent  = (spending_df[spending_df["person"].isin(row_persons)]["spent"].sum()
                  if not spending_df.empty else 0.0)
        rem    = budget - spent

        fun_bdf    = budgets_df[budgets_df["category_name"].isin(FUN_CATS)] if not budgets_df.empty else budgets_df
        fun_budget = sum(fun_bdf[f"budget_{p}"].sum() for p in row_persons) if not fun_bdf.empty else 0.0
        fun_spent  = (spending_df[
                          spending_df["person"].isin(row_persons) &
                          spending_df["category_name"].isin(FUN_CATS)
                      ]["spent"].sum() if not spending_df.empty else 0.0)
        fun_rem = fun_budget - fun_spent

        st.markdown(f"**{row_label}**")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("💼 Presupuesto",      f"${budget:,.0f}")
        c2.metric("💸 Utilizado",         f"${spent:,.0f}")
        c3.metric("✅ Restante",         f"${rem:,.0f}")
        c4.metric("🎉 Presup. Diversión", f"${fun_budget:,.0f}")
        c5.metric("🎉 Utilizado Diversión", f"${fun_spent:,.0f}")
        c6.metric("🎉 Restante Diversión", f"${fun_rem:,.0f}")

    # Debt chip
    st.markdown("")
    st.markdown(debt_html(balance, " · este mes"), unsafe_allow_html=True)

    st.divider()

    # ── Progress bars (Plotly) ────────────────────────────────────────────────
    if not budgets_df.empty:
        ph1, ph2, ph3 = st.columns([2, 2, 3])
        ph1.markdown('<div class="sec-head">Progreso de Presupuesto</div>', unsafe_allow_html=True)

        # Category group filter
        CAT_GROUPS = {
            "Todas": None,
            "Diversión": ["Salidas a comer", "Bares", "Café", "Cultura", "Miscellaneous"],
            "Ahorro":    ["Spain Move Fund", "Emergency Savings", "Viajes"],
            "Hogar":     ["Arriendo", "Gastos comunes", "Luz", "Agua", "Gas", "Internet", "Higiene hogar"],
        }
        prog_group = ph2.selectbox("Grupo", list(CAT_GROUPS.keys()),
                                   label_visibility="collapsed", key="prog_group")
        prog_filter = CAT_GROUPS[prog_group]

        # Apply category filter to budgets_df for chart
        bdf_filtered = (budgets_df[budgets_df["category_name"].isin(prog_filter)]
                        if prog_filter else budgets_df)

        if len(persons_dash) == 2:
            c_sg, c_az = st.columns(2)
            for person, col in [("SG", c_sg), ("AZ", c_az)]:
                with col:
                    st.markdown(f"**{db.PERSON_NAMES[person]}**")
                    fig_prog = progress_chart([person], bdf_filtered, spending_df)
                    if fig_prog:
                        st.plotly_chart(fig_prog, use_container_width=True, config={"displayModeBar": False})
                    else:
                        st.caption("Sin presupuesto configurado.")
        else:
            person = persons_dash[0]
            st.markdown(f"**{db.PERSON_NAMES[person]}**")
            fig_prog = progress_chart([person], bdf_filtered, spending_df)
            if fig_prog:
                st.plotly_chart(fig_prog, use_container_width=True, config={"displayModeBar": False})
            else:
                st.caption("Sin presupuesto configurado.")

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    if not expenses_df.empty:
        c_left, c_right = st.columns([3, 2])

        with c_left:
            st.markdown('<div class="sec-head">Movimientos Diarios</div>', unsafe_allow_html=True)
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
                        color_discrete_sequence=px.colors.qualitative.Safe,
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
        st.info("No hay movimientos registrados para este mes. Empieza en la pestaña 💸 Movimientos.")

    st.divider()

    # ── Dashboard Deudas ──────────────────────────────────────────────────────
    st.markdown('<div class="sec-head">🤝 Resumen de Deudas</div>', unsafe_allow_html=True)
    dd1, dd2, dd3 = st.columns(3)
    period_bal = _period_balance(M, Y)
    accum_bal  = _accum_balance()
    total_bal  = period_bal + accum_bal

    def _fmt_debt(val):
        a = abs(val)
        if val > 0.01:   return f"AZ → SG  ${a:,.0f}"
        if val < -0.01:  return f"SG → AZ  ${a:,.0f}"
        return "Sin deuda"

    dd1.metric("📅 Deuda del período",   _fmt_debt(period_bal))
    dd2.metric("📦 Deuda acumulada",      _fmt_debt(accum_bal))
    dd3.metric("🔢 Total deuda",          _fmt_debt(total_bal))

    st.divider()

    # ── Dashboard Ahorros + Proyección ────────────────────────────────────────
    st.markdown('<div class="sec-head">💰 Resumen de Ahorros y Proyección (12 meses)</div>',
                unsafe_allow_html=True)

    bal_sg = _savings_bal("SG")
    bal_az = _savings_bal("AZ")

    sa1, sa2, sa3 = st.columns(3)
    sa1.metric("💰 Ahorros Santiago", f"${bal_sg:,.0f}")
    sa2.metric("💰 Ahorros Alex",     f"${bal_az:,.0f}")
    sa3.metric("💰 Total Ahorros",    f"${bal_sg + bal_az:,.0f}")

    # Proyección: tasa mensual = presupuesto de categorías de ahorro del mes seleccionado
    PROJ_CATS = {"Spain Move Fund", "Emergency Savings", "Viajes"}
    if not budgets_df.empty:
        proj_mask = budgets_df["category_name"].isin(PROJ_CATS)
        rate_sg = float(budgets_df[proj_mask]["budget_SG"].sum())
        rate_az = float(budgets_df[proj_mask]["budget_AZ"].sum())
    else:
        rate_sg = rate_az = 0.0

    # Build 13-point projection — combined SG + AZ
    rate_total  = rate_sg + rate_az
    bal_total   = bal_sg + bal_az
    proj_months, proj_total = [], []
    now = datetime.now()
    for i in range(13):
        m = ((now.month - 1 + i) % 12) + 1
        y = now.year + (now.month - 1 + i) // 12
        proj_months.append(f"{db.MONTHS_ES[m][:3]} {y}")
        proj_total.append(bal_total + rate_total * i)

    fig_proj = go.Figure()
    fig_proj.add_trace(go.Scatter(
        x=proj_months, y=proj_total,
        name=f"Total SG + AZ (${rate_total:,.0f}/mes)",
        mode="lines+markers",
        line=dict(color="#667eea", width=3),
        marker=dict(size=7),
        fill="tozeroy", fillcolor="rgba(102,126,234,0.15)",
        hovertemplate="<b>Total Ahorros</b><br>%{x}<br>$%{y:,.0f}<extra></extra>",
    ))
    fig_proj.update_layout(
        height=280, margin=dict(l=0, r=0, t=20, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.12, font_size=11),
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="#2d3748", tickprefix="$"),
    )
    st.plotly_chart(fig_proj, use_container_width=True, config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 · MOVIMIENTOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_gastos:
    _cats_df = _categories()
    cat_name_to_id = dict(zip(_cats_df["name"], _cats_df["id"]))

    col_form, col_list = st.columns([1, 2], gap="large")

    with col_form:
        st.markdown('<div class="sec-head">➕ Nuevo Movimiento</div>', unsafe_allow_html=True)
        _new_expense_panel(M, Y, cat_name_to_id)

    with col_list:
        _expense_list_panel(M, Y, cat_name_to_id, sel_month_name, sel_year,
                            years, month_names, months_inv)


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
    tc1, tc2 = st.columns(2)
    tc1.metric("Total Santiago", f"${total_sg:,.0f}")
    tc2.metric("Total Alex",     f"${total_az:,.0f}")

    if st.button("💾 Guardar Presupuesto", type="primary"):
        for idx, row in edited.iterrows():
            cat_id = int(budgets_df.iloc[idx]["category_id"])
            db.set_budget(cat_id, "SG", float(row["Santiago (SG) $"]), M, Y)
            db.set_budget(cat_id, "AZ", float(row["Alex (AZ) $"]),    M, Y)
        st.success("✅ Presupuesto guardado!")
        _clear_cache(); st.rerun()

    st.divider()

    # ── Category management ───────────────────────────────────────────────────
    with st.expander("⚙️ Gestionar Categorías", expanded=False):
        cat_col_new, cat_col_list = st.columns([1, 2], gap="large")

        with cat_col_new:
            st.markdown("**Nueva categoría**")
            with st.form("new_category_form", clear_on_submit=True):
                new_cat_name  = st.text_input("Nombre", placeholder="Ej: Mascotas, Médico…")
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
@st.fragment
def _deudas_panel(M: int, Y: int):
    month_name = db.MONTHS_ES[M]
    st.markdown(f"## 🤝 Deudas · {month_name} {Y}")

    period_bal = _period_balance(M, Y)
    accum_bal  = _accum_balance()
    total_bal  = period_bal + accum_bal
    manual_df  = _manual_debts()

    kd1, kd2, kd3 = st.columns(3)
    with kd1:
        st.markdown("### Período")
        st.markdown(debt_html(period_bal, f" · {month_name}"), unsafe_allow_html=True)
    with kd2:
        st.markdown("### Acumulada")
        st.markdown(debt_html(accum_bal, " · acumulada"), unsafe_allow_html=True)
    with kd3:
        st.markdown("### Total")
        st.markdown(debt_html(total_bal, " · total"), unsafe_allow_html=True)

    st.divider()

    col_shared, col_manual, col_pay = st.columns([2, 2, 1.4], gap="medium")

    with col_shared:
        st.markdown('<div class="sec-head">Gastos del período con deuda (Pueden Acumularse)</div>',
                    unsafe_allow_html=True)
        exp_this   = _expenses(M, Y)
        shared_exp = (
            exp_this[exp_this["split_type"].isin(["shared", "for_other", "custom"])]
            if not exp_this.empty else pd.DataFrame()
        )
        if shared_exp.empty:
            st.info("Sin gastos compartidos este mes.")
        else:
            for _, row in shared_exp.iterrows():
                other      = "AZ" if row["payer"] == "SG" else "SG"
                bc         = "#f6ad55" if row["split_type"] == "shared" else ("#667eea" if row["split_type"] == "custom" else "#fc8181")
                tl         = db.SPLIT_TYPES[row["split_type"]]
                debt_amt   = float(row["amount"]) * db._other_pct(row)
                reconciled = (row.get("is_reconciled") or 0) == 1
                fade       = "opacity:0.4;" if reconciled else ""
                tag        = " · <b style='color:#38a169'>Acumulada</b>" if reconciled else " · <b style='color:#e53e3e'>Período</b>"
                c1, c2, c3 = st.columns([2.5, 1.8, 1.0])
                c1.markdown(
                    f"<div style='{fade}'>"
                    f"<b>{row['description']}</b> — ${row['amount']:,.0f}<br>"
                    f"<small style='color:#888'>{row['category_name']} · {row['date']} · Pagó {row['payer']}{tag}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                c2.markdown(
                    f"<div style='{fade}'>"
                    f"<span class='badge' style='background:{bc}18;color:{bc}'>{tl}</span><br>"
                    f"<small style='color:#888'>{other} debe ${debt_amt:,.0f}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if reconciled:
                    if c3.button("↩ Período", key=f"unrec_{row['id']}", help="Volver a deuda del período", use_container_width=True):
                        db.reconcile_expense(int(row["id"]), reconciled=False)
                        _clear_cache(); st.rerun(scope="fragment")
                else:
                    if c3.button("Acum. →", key=f"rec_{row['id']}", help="Mover a deuda acumulada", use_container_width=True):
                        db.reconcile_expense(int(row["id"]), reconciled=True)
                        _clear_cache(); st.rerun(scope="fragment")
                st.markdown("<hr style='margin:3px 0;border-color:#f5f5f5'>", unsafe_allow_html=True)

    with col_manual:
        st.markdown('<div class="sec-head">Deudas acumuladas</div>',
                    unsafe_allow_html=True)

        with st.expander("➕ Nueva deuda manual"):
            with st.form("manual_debt_form", clear_on_submit=True):
                md_desc    = st.text_input("Descripción", placeholder="Ej: Plata prestada…")
                md_c1, md_c2 = st.columns(2)
                md_debtor  = md_c1.selectbox("Quien debe", db.PERSONS,
                                              format_func=lambda x: f"{x} · {db.PERSON_NAMES[x]}",
                                              key="md_debtor")
                md_creditor_val = "AZ" if md_debtor == "SG" else "SG"
                md_c2.markdown(f"**A quien:** {md_creditor_val} · {db.PERSON_NAMES[md_creditor_val]}")
                md_amount  = st.number_input("Monto ($)", min_value=0.01, value=None, step=1.0, format="%.2f", key="md_amt")
                md_date    = st.date_input("Fecha", value=date.today(), key="md_date")
                if st.form_submit_button("💾 Agregar", use_container_width=True, type="primary"):
                    if not md_desc.strip():
                        st.error("La descripción es requerida.")
                    elif md_amount is None or md_amount <= 0:
                        st.error("El monto debe ser mayor a $0.")
                    else:
                        db.add_manual_debt(md_debtor, md_creditor_val, float(md_amount),
                                           md_desc.strip(), md_date.isoformat())
                        st.success("✅ Deuda registrada!")
                        _clear_cache(); st.rerun(scope="fragment")

        if manual_df.empty:
            st.caption("Sin deudas manuales pendientes.")
        else:
            for _, row in manual_df.iterrows():
                creditor_name = db.PERSON_NAMES[row["creditor"]]
                debtor_name   = db.PERSON_NAMES[row["debtor"]]
                c1, c2, c3, c4 = st.columns([3, 1.5, 0.5, 0.5])
                c1.markdown(
                    f"**{row['description']}**<br>"
                    f"<small style='color:#888'>{debtor_name} → {creditor_name} · {row['date']}</small>",
                    unsafe_allow_html=True,
                )
                c2.markdown(f"**${row['amount']:,.0f}**")
                if c3.button("✅", key=f"settle_md_{row['id']}", help="Marcar como saldada"):
                    db.settle_manual_debt(int(row["id"]))
                    _clear_cache(); st.rerun(scope="fragment")
                if c4.button("🗑", key=f"del_md_{row['id']}", help="Eliminar"):
                    db.delete_manual_debt(int(row["id"]))
                    _clear_cache(); st.rerun(scope="fragment")
                st.markdown("<hr style='margin:3px 0;border-color:#f5f5f5'>", unsafe_allow_html=True)

    with col_pay:
        st.markdown('<div class="sec-head">💳 Registrar Pago</div>', unsafe_allow_html=True)

        default_from = "AZ" if total_bal >= 0 else "SG"
        suggested    = max(0.01, round(abs(total_bal), 2))

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
            s_debt_type = st.radio("Desconta de", ["Deuda del período", "Deuda acumulada"],
                                   horizontal=True)
            s_desc = st.text_input("Descripción", value="Liquidación de deudas")
            s_date = st.date_input("Fecha", value=date.today())
            if st.form_submit_button("✅ Registrar", use_container_width=True, type="primary"):
                dt = "period" if s_debt_type == "Deuda del período" else "accumulated"
                db.add_settlement(s_from, s_to_val, float(s_amount), s_desc, s_date.isoformat(), debt_type=dt)
                st.success("✅ Pago registrado!")
                _clear_cache(); st.rerun(scope="fragment")

        st.markdown("")
        st.markdown('<div class="sec-head">Historial de Pagos</div>', unsafe_allow_html=True)
        all_sett_hist = _all_settlements()
        if all_sett_hist.empty:
            st.caption("Sin pagos registrados.")
        else:
            for _, row in all_sett_hist.iterrows():
                dt_label = "📅 Período" if row.get("debt_type", "period") == "period" else "📦 Acumulada"
                c1, c2, c3 = st.columns([2.5, 2, 0.4])
                c1.markdown(
                    f"**{row['from_person']}** → **{row['to_person']}**<br>"
                    f"<small style='color:#888'>{row['date']} · {dt_label}</small>",
                    unsafe_allow_html=True,
                )
                c2.markdown(f"${row['amount']:,.0f}<br><small>{row['description']}</small>",
                            unsafe_allow_html=True)
                if c3.button("🗑", key=f"del_s_{row['id']}"):
                    db.delete_settlement(int(row["id"]))
                    _clear_cache(); st.rerun(scope="fragment")
                st.markdown("<hr style='margin:3px 0;border-color:#f5f5f5'>", unsafe_allow_html=True)


with tab_deudas:
    _deudas_panel(M, Y)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 5 · AHORROS
# ══════════════════════════════════════════════════════════════════════════════
with tab_ahorros:
    st.markdown("## 💰 Ahorros")

    ENTRY_LABELS = {
        "deposit":    "Depósito",
        "previous":   "Ahorro previo",
        "withdrawal": "Retiro",
        "return":     "Rentabilidad +",
        "loss":       "Rentabilidad −",
    }
    ENTRY_COLORS = {
        "deposit":    "#38a169",
        "previous":   "#3182ce",
        "withdrawal": "#e53e3e",
        "return":     "#805ad5",
        "loss":       "#dd6b20",
    }
    ENTRY_SIGNS = {"withdrawal": "-", "loss": "-"}  # rest are "+"

    col_sg, col_az = st.columns(2, gap="large")

    for person, col in [("SG", col_sg), ("AZ", col_az)]:
        name    = db.PERSON_NAMES[person]
        balance = _savings_bal(person)
        entries = _savings_entries(person)

        with col:
            st.markdown(f"### {name}")
            st.metric("💰 Saldo actual", f"${balance:,.0f}")

            st.markdown("")

            # ── Formulario ahorros ─────────────────────────────────────────────
            SAVINGS_TYPES = ["deposit", "previous", "withdrawal"]
            RETURN_TYPES  = ["return", "loss"]

            with st.expander("➕ Movimiento de ahorro"):
                with st.form(f"savings_form_{person}", clear_on_submit=True):
                    sv_type = st.selectbox(
                        "Tipo", SAVINGS_TYPES,
                        format_func=lambda x: ENTRY_LABELS[x],
                        key=f"sv_type_{person}",
                    )
                    sv_desc   = st.text_input("Descripción",
                                              placeholder="Ej: Ahorro mensual, Retiro viaje…",
                                              key=f"sv_desc_{person}")
                    sv_amount = st.number_input("Monto ($)", min_value=0.01, value=None,
                                                step=1.0, format="%.2f", key=f"sv_amt_{person}")
                    sv_date   = st.date_input("Fecha", value=date.today(), key=f"sv_date_{person}")
                    if st.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
                        if not sv_desc.strip():
                            st.error("La descripción es requerida.")
                        elif sv_amount is None or sv_amount <= 0:
                            st.error("El monto debe ser mayor a $0.")
                        else:
                            db.add_savings_entry(person, float(sv_amount), sv_type,
                                                 sv_desc.strip(), sv_date.isoformat())
                            st.success("✅ Movimiento guardado!")
                            _clear_cache(); st.rerun()

            with st.expander("📈 Rentabilidad"):
                with st.form(f"return_form_{person}", clear_on_submit=True):
                    rv_type = st.radio(
                        "Tipo", ["return", "loss"],
                        format_func=lambda x: ENTRY_LABELS[x],
                        horizontal=True, key=f"rv_type_{person}",
                    )
                    rv_desc   = st.text_input("Descripción",
                                              placeholder="Ej: Rendimiento fondo, Ajuste mercado…",
                                              key=f"rv_desc_{person}")
                    rv_amount = st.number_input("Monto ($)", min_value=0.01, value=None,
                                                step=1.0, format="%.2f", key=f"rv_amt_{person}")
                    rv_date   = st.date_input("Fecha", value=date.today(), key=f"rv_date_{person}")
                    if st.form_submit_button("💾 Guardar rentabilidad", use_container_width=True, type="primary"):
                        if not rv_desc.strip():
                            st.error("La descripción es requerida.")
                        elif rv_amount is None or rv_amount <= 0:
                            st.error("El monto debe ser mayor a $0.")
                        else:
                            db.add_savings_entry(person, float(rv_amount), rv_type,
                                                 rv_desc.strip(), rv_date.isoformat())
                            st.success("✅ Rentabilidad guardada!")
                            _clear_cache(); st.rerun()

            # ── Historial ─────────────────────────────────────────────────────
            st.markdown('<div class="sec-head">Historial</div>', unsafe_allow_html=True)
            if entries.empty:
                st.caption("Sin movimientos.")
            else:
                for _, row in entries.iterrows():
                    etype = row.get("entry_type", "deposit")
                    color = ENTRY_COLORS.get(etype, "#888")
                    label = ENTRY_LABELS.get(etype, etype)
                    sign  = ENTRY_SIGNS.get(etype, "+")
                    c1, c2, c3 = st.columns([3.5, 1.5, 0.5])
                    c1.markdown(
                        f"**{row['description']}**<br>"
                        f"<small style='color:#888'>{row['date']} · "
                        f"<span style='color:{color}'>{label}</span></small>",
                        unsafe_allow_html=True,
                    )
                    c2.markdown(
                        f"<span style='color:{color};font-weight:700'>"
                        f"{sign}${row['amount']:,.0f}</span>",
                        unsafe_allow_html=True,
                    )
                    if c3.button("🗑", key=f"del_sv_{row['id']}", help="Eliminar"):
                        db.delete_savings_entry(int(row["id"]))
                        _clear_cache(); st.rerun()
                    st.markdown("<hr style='margin:2px 0;border-color:#f5f5f5'>",
                                unsafe_allow_html=True)
