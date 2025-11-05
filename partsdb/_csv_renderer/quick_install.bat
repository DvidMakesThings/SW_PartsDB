@echo off
echo Installing PartsDB Dependencies...

REM Ensure we use Python 3
python3 --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python 3 not found. Please install Python 3.8 or newer.
    pause
    exit /b 1
)

REM Install required Python packages
echo Installing required Python packages...
python3 -m pip install pdf2image pytesseract pymupdf pdfminer.six requests python-dotenv

echo Python packages installed.
echo.

REM Check if Ollama is installed
powershell -Command "if (Test-Path 'C:\Program Files\Ollama\ollama.exe') { exit 0 } else { exit 1 }"
if %ERRORLEVEL% NEQ 0 (
    echo Installing Ollama...
    echo Downloading installer...
    powershell -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/Ollama-windows-latest.exe' -OutFile '%TEMP%\ollama_installer.exe'"
    echo Running installer...
    start /wait %TEMP%\ollama_installer.exe
    echo Ollama installation complete.
) else (
    echo Ollama is already installed.
)

echo.
echo Creating environment configuration...
echo OLLAMA_MODEL=llama3:8b> "%~dp0\.env"
echo OLLAMA_HOST=http://localhost:11434>> "%~dp0\.env"
echo Configuration saved.

echo.
echo Setup complete. You may need to:
echo 1. Start the Ollama service manually
echo 2. Pull a model by running: ollama pull llama3:8b
echo.
pause