@echo off
title Race Engineer
cd /d "%~dp0"
rem Одна кнопка: лаунчер сам поднимает инженера, ждёт его ответа и только
rem потом открывает оверлей. Раньше это были два .bat и правильный порядок.
python launcher.py --start
