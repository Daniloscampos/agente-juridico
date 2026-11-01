@echo off
setlocal
cd /d "%~dp0"
title Agente Juridico - Painel atualizado
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto erro
)
".venv\Scripts\python.exe" -m pip install -r requirements-dashboard.lock
if errorlevel 1 goto erro
".venv\Scripts\python.exe" iniciar_local.py
if errorlevel 1 goto erro
pause
exit /b 0
:erro
echo.
echo Nao foi possivel iniciar. Confira a mensagem acima e envie somente o erro, sem senhas.
pause
exit /b 1
