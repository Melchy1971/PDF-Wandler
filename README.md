
# Invoice Sorter – Phase 1

Enthaltene Features:
- Watch-Folder (alle 5s) – neuer Batch wird automatisch verarbeitet
- Confidence-Score & Review-Tab (unsichere/fehlende Felder)
- OCR/Text-Cache (MD5-basiert) für Geschwindigkeit
- Anonymisierung im Log (IBAN, E-Mail, Tel)
- CSV-Log `logs/processed.csv` (+ MD5, confidence, validation_status)
- Vorschau mit Regex-Overlay (Rechnungsnr., Datum, Lieferant-Hints)

## Start
```bash
pip install -r requirements.txt
python gui_app_phase1.py
```

## Struktur
- `gui_app_phase1.py` – Tkinter-GUI
- `sorter_phase1.py` – Verarbeitung
- `patterns.yaml` – Regex-/Hinweisregeln
- `config.yaml` – Pfade & Optionen
- `cache/` – OCR/Text- & JSON-Cache
- `logs/processed.csv` – CSV-Historie

## Hinweise
- Wenn `PyMuPDF` oder `pdfminer.six` nicht installiert sind, nutzt die OCR (Poppler+pytesseract) die Scans.
- Der Watch-Folder verarbeitet neue Dateien anhand des fehlenden JSON-Caches.
- Review-Tab zeigt alle Ergebnisse mit `needs_review`/`fail`.
