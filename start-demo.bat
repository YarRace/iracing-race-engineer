@echo off
title Race Engineer - Demo launcher
cd /d "%~dp0"
echo Closing any old dashboard server on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
echo Starting demo dashboard (no sim needed)...
echo A server window will open. Browser opens automatically.
start "Race Engineer (server)" cmd /k python spikes\demo_dashboard.py
timeout /t 4 /nobreak >nul
start "" http://localhost:8000
exit
