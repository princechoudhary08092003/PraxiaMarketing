@echo off
REM ============================================================
REM  Praxia Marketing + Growth Studio - portable launcher
REM  First run: creates its own venv and installs everything.
REM  Later runs: just starts the app and opens the browser.
REM ============================================================
setlocal
cd /d "%~dp0"

set "VENV=backend\.venv"
set "PY=%VENV%\Scripts\python.exe"

if not exist "backend\.env" (
    echo [setup] Creating backend\.env from template. Open it and add your keys!
    copy "backend\.env.example" "backend\.env" >nul
)

if not exist "%PY%" (
    echo [setup] First run: creating a virtual environment...
    python -m venv "%VENV%"
    echo [setup] Installing dependencies (this can take a few minutes)...
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r backend\requirements.txt
    echo [setup] Installing the headless browser for product screenshots...
    "%PY%" -m playwright install chromium
)

echo ============================================================
echo   Praxia Growth Studio
echo   Starting... a browser tab opens in a few seconds.
echo   Keep THIS window open while you use it. Close it to stop.
echo ============================================================

start "" /b cmd /c "timeout /t 6 >nul & start "" http://127.0.0.1:8020"

cd backend
"..\%VENV%\Scripts\python.exe" -m uvicorn app.main:app --port 8020 --host 127.0.0.1

endlocal
