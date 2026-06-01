@echo off
cd /d "%~dp0"

echo Verificando dependencias...
pip install -r requirements.txt -q

echo.
echo Iniciando Budget Tracker...
echo Abre tu navegador en: http://localhost:8501
echo.
streamlit run app.py
pause
