@echo off
title Race Engineer
cd /d "%~dp0"
rem Одно приложение: инженер крутится фоновым потоком внутри окна.
rem Раньше это были два .bat и правильный порядок запуска.
python app.py
