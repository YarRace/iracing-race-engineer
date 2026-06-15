@echo off
chcp 65001 >nul
title Race Engineer - Демо
cd /d "%~dp0"
echo ============================================
echo   Race Engineer - демо (без iRacing)
echo   Данные реального заезда. Браузер откроется сам.
echo   Чтобы остановить - закрой это окно или Ctrl+C
echo ============================================
echo.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:8000"
python spikes\demo_dashboard.py
echo.
echo Демо остановлено.
pause
