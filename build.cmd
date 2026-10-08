@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe build_icon.py
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist-v5 Kotoba.spec
if errorlevel 1 pause
