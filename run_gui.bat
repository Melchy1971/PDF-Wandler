@echo off
setlocal
if not exist ".\.venv\Scripts\python.exe" (
  echo Kein venv gefunden. Bitte erst setup.ps1 ausfuehren.
  pause
  exit /b 1
)
.\.venv\Scripts\python.exe gui_app.py
