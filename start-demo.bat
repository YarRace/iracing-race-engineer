@echo off
title Race Engineer - Demo launcher
cd /d "%~dp0"
echo Starting demo dashboard (no sim needed)...
echo A server window will open. Browser opens automatically.
start "Race Engineer (server)" cmd /k python spikes\demo_dashboard.py
timeout /t 4 /nobreak >nul
start "" http://localhost:8000
exit
