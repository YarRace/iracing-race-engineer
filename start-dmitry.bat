@echo off
title Dmitry - voice assistant
cd /d "%~dp0"
echo Dmitry starting... (first run downloads Whisper model, wait a bit)
echo Press wheel button 20 to talk. Close this window to stop.
python dmitry.py
pause
