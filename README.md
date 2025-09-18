# KI‑Rechnungs‑Extractor (VS Code Setup)

Dieses Projekt extrahiert **Rechnungsnummer**, **Lieferant** und **Rechnungsdatum** aus PDFs/Bildern und benennt die Dateien nach Schema:
`YYYY-MM-DD_Lieferant_Re-YYYY-MM-DD.<ext>`

## Schnellstart (VS Code)
1. Öffne den Ordner `invoicex` in VS Code.
2. VS Code fragt nach dem Erstellen einer venv → akzeptieren, oder manuell:
   ```bash
   python -m venv .venv
   .venv/Scripts/activate   # Windows
   source .venv/bin/activate # macOS/Linux
   ```
3. Installiere Abhängigkeiten: `pip install -r requirements.txt`
4. Systemabhängigkeiten installieren:
   - **Tesseract OCR** (und deutsches Sprachpaket)
   - **Poppler** (für pdf2image, optional bei PyMuPDF nicht nötig)
5. Starte CLI:
   ```bash
   python -m app.cli ingest ./eingang ./ablage
   ```
6. GUI (Streamlit):
   ```bash
   streamlit run app/gui_streamlit.py
   ```

## Debuggen
- F5 in VS Code → CLI oder Streamlit starten (siehe `.vscode/launch.json`).

