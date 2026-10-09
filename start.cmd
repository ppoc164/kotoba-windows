@echo off
cd /d "%~dp0"
if exist "dist-v6\Kotoba\Kotoba.exe" (
    start "" "dist-v6\Kotoba\Kotoba.exe"
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py
    exit /b
)
echo Please install Python 3.12, then run setup.cmd first.
pause
