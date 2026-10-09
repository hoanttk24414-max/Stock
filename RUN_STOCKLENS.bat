@echo off
setlocal
title StockLens
pushd "%~dp0"

echo ==========================================
echo          STOCKLENS - LOCAL RUN
echo ==========================================
echo.
echo Thu muc hien tai:
echo %CD%
echo.

REM Kiem tra app.py bang DUONG DAN TUYET DOI cua file BAT
if not exist "%~dp0app.py" (
    echo [LOI] Khong tim thay:
    echo "%~dp0app.py"
    echo.
    echo Hay dat RUN_STOCKLENS.bat cung thu muc voi app.py.
    pause
    popd
    exit /b 1
)
REM Uu tien Anaconda Python tren may cua ban
set "PYTHON_EXE=C:\Users\HP\anaconda3\python.exe"

if not exist "%PYTHON_EXE%" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [LOI] Khong tim thay Python.
        echo Hay cai Python 3.12 hoac Anaconda.
        pause
        popd
        exit /b 1
    )
    set "PYTHON_EXE=python"
)

echo [OK] Tim thay app.py
echo [OK] Python:
"%PYTHON_EXE%" --version
echo.

REM Chi cai requirements neu Streamlit chua co
"%PYTHON_EXE%" -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo Dang cai thu vien lan dau...
    "%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo.
        echo [LOI] Cai thu vien that bai.
        pause
        popd
        exit /b 1
    )
)

echo Dang mo StockLens...
echo.
"%PYTHON_EXE%" -m streamlit run "%~dp0app.py"

popd
pause
endlocal