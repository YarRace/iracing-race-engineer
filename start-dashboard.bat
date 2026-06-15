@echo off
chcp 65001 >nul
title Race Engineer - Гонка
cd /d "%~dp0"
echo ============================================
echo   Race Engineer - боевой режим (живой iRacing)
echo   Браузер откроется сам: http://localhost:8000
echo   Чтобы остановить - закрой это окно или Ctrl+C
echo ============================================
echo.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:8000"
python run.py
echo.
echo Дашборд остановлен.
pause
