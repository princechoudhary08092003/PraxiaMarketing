@echo off
REM ============================================================
REM  Praxia Marketing - local launcher (Windows)
REM  Reuses the Praxia Course Factory venv (fastapi/uvicorn/openai/dotenv).
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY=C:\Users\Prince.Choudhary\praxia-course-factory\backend\.venv\Scripts\python.exe"

if not exist "backend\.env" (
    echo [setup] Creating backend\.env from template. Add your keys!
    copy "backend\.env.example" "backend\.env" >nul
)

echo [start] Praxia Marketing -> http://127.0.0.1:8020
start "Praxia Marketing" cmd /k "cd /d %~dp0backend && "%PY%" -m uvicorn app.main:app --reload --port 8020"
echo.
echo Open http://127.0.0.1:8020 in your browser.
echo.
endlocal
