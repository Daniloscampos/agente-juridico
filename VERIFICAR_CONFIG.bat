@echo off
cd /d "%~dp0"
title VERIFICAR_CONFIG
".venv\Scripts\python.exe" "scripts\verificar_config.py"
echo.
pause
