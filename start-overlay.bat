@echo off
title Race Engineer Overlay
cd /d "%~dp0"
echo Overlay starting (needs dashboard run.py on :8000)...
echo A control panel opens: tick widgets to show them.
echo Drag widgets with mouse, resize by corner. Lock = clicks pass to game.
python overlay_app.py
