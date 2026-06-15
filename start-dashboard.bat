@echo off
title Race Engineer - Race launcher
cd /d "%~dp0"
echo Starting dashboard (live iRacing)...
echo A server window will open. Browser opens automatically.
echo Get in the car and drive. Close the server window to stop.
start "Race Engineer (server)" cmd /k python run.py
timeout /t 4 /nobreak >nul
start "" http://localhost:8000
exit
