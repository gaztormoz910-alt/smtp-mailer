@echo off
title CHARLY MAILER
echo ============================================
echo   CHARLY MAILER — Launcher
echo ============================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo Install Python from https://python.org
    echo Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo [*] Installing dependencies...
pip install -r requirements.txt --quiet
echo.

echo [*] Starting CHARLY MAILER...
python main.py

pause
