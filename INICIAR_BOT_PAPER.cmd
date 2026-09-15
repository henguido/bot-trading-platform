@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo   BOT Trading Platform - Inicio PAPER

echo ==============================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch_paper_stack.ps1"
set EXIT_CODE=%ERRORLEVEL%
echo.
if not "%EXIT_CODE%"=="0" (
  echo El sistema no se inicio. Revisa el mensaje anterior.
) else (
  echo Puedes cerrar esta ventana. El backend y frontend siguen activos.
)
echo.
pause
exit /b %EXIT_CODE%
