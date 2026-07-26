@echo off
REM ============================================================
REM  Praxia Marketing + Growth Studio - double-click launcher
REM  Starts the app and opens it in your browser automatically.
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY=C:\Users\Prince.Choudhary\praxia-course-factory\backend\.venv\Scripts\python.exe"

if not exist "backend\.env" (
    echo [setup] Creating backend\.env from template. Add your keys!
    copy "backend\.env.example" "backend\.env" >nul
)

echo ============================================================
echo   Praxia Growth Studio
echo   Starting... a browser tab opens in a few seconds.
echo   Keep THIS window open while you use it. Close it to stop.
echo ============================================================
echo.

REM open the browser after the server has had a moment to start
start "" /b cmd /c "timeout /t 6 >nul & start "" http://127.0.0.1:8020"

cd backend
"%PY%" -m uvicorn app.main:app --port 8020 --host 127.0.0.1

endlocal
