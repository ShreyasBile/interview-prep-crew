@echo off
title Interview Prep Crew
rem Start Interview Prep Crew and open it in the browser (port 8010, or the next free one).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo First run: creating virtual environment and installing packages...
    py -3.13 -m venv .venv || python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :failed
)
if not exist .env copy .env.example .env >nul
.venv\Scripts\python.exe start.py %*
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Interview Prep Crew could not start. See the message above.
pause
exit /b 1
