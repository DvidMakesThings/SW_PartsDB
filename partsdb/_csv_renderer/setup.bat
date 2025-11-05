@echo off
echo Setting up PartsDB CSV Renderer Environment...

REM Check if Python 3 is installed
python3 --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Trying python instead...
    python --version >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo Python is not installed or not in PATH. Please install Python 3.8 or newer.
        pause
        exit /b 1
    )
    echo WARNING: Using 'python' command. If this is Python 2, the script may not work properly.
    set PYTHON_CMD=python
) else (
    set PYTHON_CMD=python3
)

REM Run the setup script
cd /d "%~dp0"
%PYTHON_CMD% setup_environment.py

echo Setup complete.
pause