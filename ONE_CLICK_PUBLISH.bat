@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "JARVIS_RELEASE_CHILD=1"
start "Jarvis AI 2.0 One-Click Publish" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -File "%SCRIPT_DIR%publish_tools\publish_one_click.ps1"
