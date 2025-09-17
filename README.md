# Dateiumbenennungstool (Refined)

## Features
- Hintergrundverarbeitung (UI bleibt responsiv)
- Vorschau der Dateinamen (nutzt exakt das Muster aus der Config)
- Jahres-/Firmenordner (Rechtsform optional entfernt)
- Sicheres Backup & konfliktfreies Verschieben
- Bericht- und Log-Ansicht
- Dark Mode, konfigurierbares Dateimuster

## Installation
```bash
pip install -r requirements.txt
```
(ggf. weitere OCR/PDF-Pakete aktivieren)

## Start
```bash
python refactored_file_renamer.py
```

## Konfiguration
- `config.json` anpassen (Zielordner, Muster, LOG_LEVEL etc.).
- Firmenliste in `firmen.txt` pflegen (eine Zeile pro Firma).

## Hinweis zu Textextraktion
`text_extraction.py` enthält Platzhalter. Binde deine echte Extraktion ein:
- PDFs: z. B. pdfminer.six
- Bilder: z. B. pytesseract + pillow