@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "JARVIS_RELEASE_CHILD=1"
start "Jarvis AI 2.0 Release Build" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build_release.ps1"
