@echo off
cd /d "C:\Users\felip\Documents\Dev\Quittance Automation"
if not exist "logs" mkdir logs
echo. >> "logs\task_stderr.log"
echo ===== Task run: %DATE% %TIME% ===== >> "logs\task_stderr.log"
".venv\Scripts\python.exe" "C:\Users\felip\Documents\Dev\Quittance Automation\main.py" >> "logs\task_stderr.log" 2>&1
