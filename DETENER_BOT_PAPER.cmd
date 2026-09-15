@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo   BOT Trading Platform - Detener PAPER

echo ==============================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_paper_stack.ps1"
set EXIT_CODE=%ERRORLEVEL%
echo.
pause
exit /b %EXIT_CODE%
