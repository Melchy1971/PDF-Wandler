$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Kein venv gefunden. Bitte erst setup.ps1 ausführen." -ForegroundColor Red
    exit 1
}

$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy gui_app.py
