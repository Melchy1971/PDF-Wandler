@echo off
setlocal
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python gui_app.py
