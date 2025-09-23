#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv || true
. .venv/bin/activate
mkdir -p inbox processed error
python -m pip install --upgrade pip
pip install -r requirements.txt
python hotfolder.py --in inbox --done processed --err error --config config.yaml --patterns patterns.yaml
