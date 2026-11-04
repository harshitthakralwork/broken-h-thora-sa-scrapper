@echo off
title Create Desktop Shortcut for SparkXFlow
cd /d "%~dp0"
echo Creating Desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine([System.Environment]::GetFolderPath('Desktop'), 'SparkXFlow Lead Engine.lnk')); $s.TargetPath = '%~dp0start_app.bat'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'SparkXFlow Lead Intelligence Engine'; $s.Save()"
echo.
echo [OK] Shortcut created on your Desktop as 'SparkXFlow Lead Engine'!
echo You can now simply double-click that icon on your Desktop anytime to launch the app.
echo.
pause

