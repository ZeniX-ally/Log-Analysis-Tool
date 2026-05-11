@echo off
cd /d %~dp0
echo ================================================
echo G4.9 FCT XML Dashboard / FCT Monitor
echo ================================================
echo Project Path: %cd%
echo.
python -m pip install -r requirements.txt
echo.
echo Starting Flask Server...
echo URL: http://127.0.0.1:5000/
echo.
python backend\app.py
pause