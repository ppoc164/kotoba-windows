@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
call start.cmd
exit /b
:failed
echo Setup failed. Check Python 3.12 installation and network connection.
pause
