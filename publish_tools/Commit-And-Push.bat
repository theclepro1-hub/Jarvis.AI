@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

set /p REMOTE_URL=GitHub remote URL (leave empty if origin is already configured): 
set /p COMMIT_MESSAGE=Commit message (leave empty for auto): 

powershell.exe -NoLogo -ExecutionPolicy Bypass -File "%SCRIPT_DIR%commit_and_push.ps1" -RemoteUrl "%REMOTE_URL%" -CommitMessage "%COMMIT_MESSAGE%" -Branch "main"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [publish] Failed with exit code %EXIT_CODE%.
) else (
  echo [publish] Push flow completed.
)
pause
exit /b %EXIT_CODE%

