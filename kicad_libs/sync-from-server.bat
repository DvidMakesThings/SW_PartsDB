@echo off
REM DMTDB KiCad Library Sync via SSH
REM Double-click to sync libraries from your server.

setlocal
set "SCRIPT_DIR=%~dp0"

echo.
echo Syncing DMTDB libraries from server...
echo.

powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%sync-from-server.ps1"

echo.
pause
