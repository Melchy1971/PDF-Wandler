
# Phase 3 – Ollama & PDF-Stempel

**Neu:** 
- LLM-Fallback via **Ollama** (lokal) für strukturierte Felder (JSON).
- **PDF-Stempel**: Deckblatt mit den extrahierten Daten + QR (JSON) vor das Original geheftet.

## Quickstart
```bash
pip install -r requirements.txt
python gui_app_phase3.py
```
- In der GUI `Ollama-Fallback` aktivieren, Host/Modell anpassen (z. B. `llama3`).
- `PDF stempeln` aktiviert: erzeugt Frontpage mit MD5 und QR.

## Trigger-Logik für Ollama
- `always`: immer.
- `on_low_conf`: wenn Confidence < `conf_threshold` oder Status != ok.
- `on_fail`: nur bei `fail`.

## CSV-Spalten
`source_file, target_file, invoice_no, supplier, date, method, hash_md5, confidence, validation_status, gross, net, tax, currency`

## Abhängigkeiten
- `pymupdf` (optional), `pdfminer.six`, `pdf2image`, `pytesseract`, `requests`, `reportlab`, `pypdf`
- Windows: **Poppler** installieren und den `bin`-Pfad setzen. Tesseract separat installieren.

## Hinweis
Wenn kein Ollama-Server läuft, wird er automatisch **nicht** genutzt.
