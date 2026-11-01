@echo off
cd /d "%~dp0"
title CADASTRAR_PESSOA
".venv\Scripts\python.exe" "scripts\cadastrar_pessoa.py"
echo.
pause
