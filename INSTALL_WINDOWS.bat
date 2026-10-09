@echo off
cd /d "%~dp0"
echo [StockLens] Dang cai thu vien...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Cai thu vien that bai. Hay kiem tra Python va ket noi Internet.
  pause
  exit /b 1
)
echo.
echo Cai dat hoan tat.
pause
