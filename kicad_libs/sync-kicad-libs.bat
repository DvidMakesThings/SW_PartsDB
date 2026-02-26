@echo off
REM ============================================================================
REM DMTDB KiCad Library Sync - Windows Launcher
REM 
REM Double-click this file to sync KiCad libraries from your DMTDB server.
REM The script will use the paths you configured in the DMTDB Client Setup page.
REM ============================================================================

setlocal

REM Default server URL - change this to your server address
set "SERVER_URL=http://192.168.0.25:5000"

REM Check for PowerShell
where powershell >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: PowerShell is required but not found.
    pause
    exit /b 1
)

REM Get the directory of this batch file
set "SCRIPT_DIR=%~dp0"

REM Run the PowerShell script
echo.
echo ============================================
echo   DMTDB KiCad Library Sync
echo ============================================
echo.
echo Server: %SERVER_URL%
echo.

REM Check if sync script exists
if not exist "%SCRIPT_DIR%sync-kicad-libs.ps1" (
    echo ERROR: sync-kicad-libs.ps1 not found in %SCRIPT_DIR%
    echo Please make sure the PowerShell script is in the same directory.
    pause
    exit /b 1
)

REM Execute PowerShell (uses paths from server Client Setup)
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%sync-kicad-libs.ps1" -ServerUrl "%SERVER_URL%"

echo.
echo Press any key to exit...
pause >nul
