@echo off
title SparkXFlow Lead Intelligence Engine
color 0b
echo ============================================================
echo       SPARKXFLOW LEAD INTELLIGENCE ENGINE (Windows 11)
echo ============================================================
echo.

cd /d "%~dp0"

:: 1. Verify virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Creating .venv...
    python -m venv .venv
    echo [*] Installing requirements...
    call .venv\Scripts\pip.exe install -r backend\requirements.txt
)

:: 2. Verify .env file
if not exist ".env" (
    echo [!] .env file not found. Creating from .env.example...
    copy .env.example .env
)

:: 3. Read ADMIN_TOKEN and PORT from .env
for /f "tokens=1,* delims==" %%A in ('findstr /i "^ADMIN_TOKEN=" .env') do set ADMIN_TOKEN=%%B
set PORT=8005
for /f "tokens=1,* delims==" %%A in ('findstr /i "^PORT=" .env') do set PORT=%%B

echo [*] Database: SQLite (sparkxflow.db)
echo [*] Target Market: India
echo [*] Server Address: http://127.0.0.1:%PORT%
echo.
echo ============================================================
echo YOUR DASHBOARD LOGIN TOKEN:
echo %ADMIN_TOKEN%
echo ============================================================
echo.
echo [!] Opening dashboard in your default browser...
start http://127.0.0.1:%PORT%

echo.
echo [*] Starting SparkXFlow Engine...
echo [*] Keep this window open while using the application!
echo [*] Press Ctrl+C in this window to stop the server.
echo.
".venv\Scripts\python.exe" backend\run_local.py
pause

