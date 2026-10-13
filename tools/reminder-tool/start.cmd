@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist auth.json (
    .venv\Scripts\python.exe setup_auth.py
    if errorlevel 1 goto failed
)
set REMINDER_LOCAL_HTTP=1
echo Open http://127.0.0.1:8002/ in your browser.
.venv\Scripts\python.exe server.py
:failed
pause
