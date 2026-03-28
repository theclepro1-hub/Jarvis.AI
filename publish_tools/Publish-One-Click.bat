@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

echo [publish-2.0] One-click release publish
powershell.exe -NoLogo -ExecutionPolicy Bypass -File "%SCRIPT_DIR%publish_one_click.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [publish-2.0] Failed with exit code %EXIT_CODE%.
) else (
  echo [publish-2.0] One-click publish completed.
)
pause
exit /b %EXIT_CODE%
