@echo off
title Stop SparkXFlow Server
color 0c
echo ============================================================
echo           STOPPING SPARKXFLOW LEAD ENGINE
echo ============================================================
echo.
set PORT=8005
if exist ".env" (
    for /f "tokens=1,* delims==" %%A in ('findstr /i "^PORT=" .env') do set PORT=%%B
)

echo Searching for processes running on port %PORT%...
set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%PORT% ^| findstr LISTENING') do (
    echo Stopping process PID: %%a...
    taskkill /F /PID %%a 2>nul
    set FOUND=1
)

if "%FOUND%"=="1" (
    echo [OK] SparkXFlow server has been stopped. Port %PORT% is now free.
) else (
    echo [i] No SparkXFlow server was running on port %PORT%.
)
echo.
pause

