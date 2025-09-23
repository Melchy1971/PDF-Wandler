@echo off
setlocal
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  py -m venv .venv
)
call .venv\Scripts\activate
mkdir inbox 2>nul
mkdir processed 2>nul
mkdir error 2>nul
python -m pip install --upgrade pip
pip install -r requirements.txt
python hotfolder.py --in inbox --done processed --err error --config config.yaml --patterns patterns.yaml
