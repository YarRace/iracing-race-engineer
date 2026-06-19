@echo off
title Race Engineer Standings
cd /d "%~dp0"
echo Standings overlay starting (needs dashboard run.py on :8000)...
echo Drag with mouse to position. Esc to close.
python overlay_standings.py
