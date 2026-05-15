@echo off
title NEXUS FCT - Local Test Environment
cd /d "%~dp0.."

echo ==========================================
echo   NEXUS FCT - Windows Local Test Launcher
echo ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8+
    echo         Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install dependencies
echo [1/4] Installing Python dependencies...
pip install flask rich psutil -q
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed
    pause
    exit /b 1
)
echo   OK

:: Generate test data
echo [2/4] Generating test data...
python tools\generate_test_data.py 30
if %errorlevel% neq 0 (
    echo [WARN] Test data generation failed, continuing...
)
echo   OK

:: Start server
echo [3/4] Starting Flask server (port 59488)...
echo.
echo ==========================================
echo   Server is starting...
echo   Open browser: http://localhost:59488
echo   Press Ctrl+C to stop
echo ==========================================
echo.

python backend\app.py

echo.
echo [INFO] Server stopped
pause