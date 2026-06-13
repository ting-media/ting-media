@echo off
REM Start WhatsApp + Gmail Agent on Windows

echo.
echo ========================================
echo WhatsApp + Gmail Agent
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if venv exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install requirements
echo Installing dependencies...
pip install -r requirements.txt -q

REM Check for .env
if not exist ".env" (
    echo.
    echo WARNING: .env file not found!
    echo Creating .env from .env.example...
    copy .env.example .env
    echo.
    echo Please edit .env with your API keys before continuing.
    pause
)

REM Run the app
echo.
echo Starting agent...
echo Dashboard: http://localhost:5000
echo.
python main.py

pause
