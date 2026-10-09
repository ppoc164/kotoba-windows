@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe build_icon.py
if errorlevel 1 exit /b 1
if exist "dist-v6\Kotoba\data" (
    echo Existing user data found. Move data to a safe backup before rebuilding.
    exit /b 1
)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist-v6 Kotoba.spec
if errorlevel 1 pause
