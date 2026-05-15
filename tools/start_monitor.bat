@echo off
title NEXUS FCT - Web Dashboard
cd /d "%~dp0.."

echo ==========================================
echo   NEXUS FCT - Web Server Monitor
echo ==========================================
echo.
echo   Make sure the main server is running on port 59488
echo   Press Ctrl+C to stop
echo.

python tools\server_dashboard.py --target-host localhost --target-port 59488 --port 54188

pause