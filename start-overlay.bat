@echo off
title Race Engineer Overlay
cd /d "%~dp0"
echo Overlay starting (needs dashboard run.py on :8000)...
echo Drag with mouse to position. Esc to close.
python overlay.py
