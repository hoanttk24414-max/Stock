@echo off
cd /d "%~dp0"
echo [StockLens] Khoi dong ung dung...
python -m streamlit run app.py
pause
