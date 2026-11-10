@echo off
setlocal EnableExtensions
title NeuroGenUI (port 8200)
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
echo Starting NeuroGenUI on http://localhost:8200  (close this window to stop)
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://localhost:8200'"
cd backend
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8200
pause
