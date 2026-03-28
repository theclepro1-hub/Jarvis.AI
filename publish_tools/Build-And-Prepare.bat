@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "REPO_SLUG=theclepro1-hub/JarvisAI-2.0"

echo [publish-2.0] Build release and prepare GitHub bundle
powershell.exe -NoLogo -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build_and_prepare.ps1" -RepoSlug "%REPO_SLUG%"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [publish-2.0] Failed with exit code %EXIT_CODE%.
) else (
  echo [publish-2.0] Done.
)
pause
exit /b %EXIT_CODE%
