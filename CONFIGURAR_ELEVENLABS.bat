@echo off
cd /d "%~dp0"
title CONFIGURAR_ELEVENLABS
".venv\Scripts\python.exe" "scripts\configurar_elevenlabs.py"
echo.
pause
