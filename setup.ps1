Param(
    [string]$ProjectRoot = "."
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $ProjectRoot

# 1) Virtuelles Environment
if (-not (Test-Path ".\.venv")) {
    Write-Host "Erstelle venv..." -ForegroundColor Cyan
    python -m venv .venv
}
$venvPy = ".\.venv\Scripts\python.exe"
$venvPip = ".\.venv\Scripts\pip.exe"

# 2) pip aktualisieren + requirements
& $venvPy -m pip install --upgrade pip
if (Test-Path ".\requirements.txt") {
    & $venvPip install -r requirements.txt
} else {
    Write-Host "requirements.txt nicht gefunden – wird übersprungen." -ForegroundColor Yellow
}

# 3) Standard-Ordner anlegen
New-Item -ItemType Directory -Force -Path ".\in" | Out-Null
New-Item -ItemType Directory -Force -Path ".\out" | Out-Null
New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null

# 4) config.yaml erzeugen, falls nicht vorhanden
if (-not (Test-Path ".\config.yaml")) {
$config = @"
input_dir: "$(Resolve-Path .\in)"
output_dir: "$(Resolve-Path .\out)"
unknown_dir_name: "unbekannt"

# Tools (leer lassen, wenn im PATH)
tesseract_cmd: ""
poppler_path: ""

tesseract_lang: "deu+eng"
use_ocr: true
use_ollama: false
ollama:
  host: "http://localhost:11434"
  model: "llama3"
dry_run: true
csv_log_path: "logs/processed.csv"
"@
    $config | Set-Content -LiteralPath .\config.yaml -Encoding UTF8
    Write-Host "config.yaml erstellt. Bitte ggf. Tesseract/Poppler-Pfade setzen." -ForegroundColor Green
} else {
    Write-Host "config.yaml existiert bereits – unverändert." -ForegroundColor Yellow
}

Write-Host "`nSetup fertig. Starte GUI via 'run_gui.ps1' oder 'run_gui.bat'." -ForegroundColor Green
