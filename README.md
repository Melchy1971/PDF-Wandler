# PDF Rechnung Changer (Bundle)

GUI + OCR-Verarbeitung + Hotfolder.

## Installation
```bash
python -m venv .venv
. .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Zusätzlich systemweit installieren:
- **Tesseract OCR**
- **Poppler** (pdf2image nutzt die `pdftoppm`/`pdftocairo` Tools)

Windows (Beispiel, mit Chocolatey):
```powershell
choco install tesseract
choco install poppler
```

## Konfiguration
- Bearbeite `config.yaml` (Pfad zu `tesseract_cmd`, `poppler_path`, Sprachcode z. B. `deu+eng`).
- Regex/Heuristiken in `patterns.yaml`.

## Start GUI
```bash
python gui_app.py
```

## Hotfolder starten
```bash
python hotfolder.py --in inbox --done processed --err error --config config.yaml --patterns patterns.yaml
```

## Hinweise
- Info-Dialog: Toolname *PDF Rechnung Changer*, Autor *Markus Dickscheit*, Lizenzhinweis.
- Fenster startet maximiert, `Beenden`-Button stoppt Jobs sauber.


## Startskripte
### Windows
- `start_gui.bat` — richtet (falls nötig) ein venv ein, installiert Pakete und startet die GUI.
- `start_hotfolder.bat` — legt `inbox/ processed/ error/` an und startet den Hotfolder.

### Linux/macOS
```bash
chmod +x start_gui.sh start_hotfolder.sh
./start_gui.sh
# oder
./start_hotfolder.sh
```
Die GUI legt beim Start Standardordner an (`inbox`, `processed`, `error`, `logs`). Pfade kannst du in der Oberfläche bzw. `config.yaml` anpassen.
