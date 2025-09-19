# Invoice Sorter – README

Ein kleines, modulares Tool zum Verarbeiten von PDF-Rechnungen (Text & Scans):
- Extrahiert **Rechnungsnummer**, **Lieferant**, **Rechnungsdatum**
- Bennent Dateien um: `YYYY-MM-DD_Lieferant_Re-<Nr>.pdf`
- Legt sie ab unter: `<output_dir>/<Jahr>/<Lieferant>/`
- Unklare Fälle → `unbekannt/`
- GUI mit OCR-Option (Tesseract), Poppler, optional Ollama-Fallback

## 1) Projektstruktur (empfohlen)
```
your-project/
├─ gui_app.py
├─ sorter.py
├─ requirements.txt
├─ config.yaml
├─ patterns.yaml
├─ setup.ps1
├─ run_gui.ps1
└─ run_gui.bat
```

## 2) Voraussetzungen
- **Python 3.10+**
- **Tesseract OCR** (Windows): Installiere und merke dir den Pfad zu `tesseract.exe`  
  (z. B. `C:\Program Files\Tesseract-OCR\tesseract.exe`)
- **Poppler** (Windows): Entpackter `bin`-Ordner (z. B. `C:\poppler-24.02.0\Library\bin`)

> Tipp: Setze beides später bequem in der GUI oder zuerst in `config.yaml`.

## 3) Installation (PowerShell)
Im Projektordner:
```
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```
Das Skript erstellt ein virtuelles Environment, installiert Abhängigkeiten und legt (falls fehlend) eine `config.yaml` mit lokalen Pfaden (`.\in`, `.\out`) an. Du kannst Pfade und Optionen jederzeit in der GUI oder in `config.yaml` anpassen.

Manuell (ohne Skript):
```
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 4) Start der GUI
Mit PowerShell:
```
powershell -ExecutionPolicy Bypass -File .\run_gui.ps1
```
oder mit Doppelklick auf **run_gui.bat**.

## 5) Wichtige Einstellungen (GUI / config.yaml)
- `input_dir`: Eingangsordner mit PDF-Dateien (default: `.\in`)
- `output_dir`: Zielablage (default: `.\out`)
- `unknown_dir_name`: Ordner für unklare Fälle (default: `unbekannt`)
- `tesseract_cmd`: Pfad zu `tesseract.exe` (leer lassen, wenn im PATH)
- `poppler_path`: Poppler `bin`-Pfad (für `pdf2image`)
- `tesseract_lang`: z. B. `deu` oder `deu+eng`
- `use_ocr`: `true` für Scans (empfohlen)
- `dry_run`: `true` = nur Vorschau, nichts verschieben
- `csv_log_path`: optionales CSV-Log

## 6) Patterns anpassen
In `patterns.yaml` kannst du Regexe und Lieferanten-Hinweise pflegen. Je genauer, desto weniger landet in `unbekannt`.

## 7) Troubleshooting
- **SyntaxError in GUI (f-String)**: Stelle sicher, dass jede Log-Zeile mit `\n` endet, z. B.  
  `self._log("INFO", f"Konfiguration geladen: {path}\n")`.  
  In den bereitgestellten Downloads ist das bereits korrigiert.
- **OCR findet keinen Text**: Prüfe `tesseract_cmd`, `poppler_path`, `tesseract_lang`.  
- **Leistung**: Bei vielen Scans OCI dauert – nutze testweise `dry_run: true` und schalte OCR erst später zu.
- **Stop-Button**: Stoppt nach der aktuellen Datei (sanfter Abbruch).

Viel Spaß beim Sortieren!
