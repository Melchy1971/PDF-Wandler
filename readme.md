# PDF-Wandler

Ein Python-Tool zur automatisierten Umwandlung und Textextraktion aus PDF- und Bilddateien. Die extrahierten Inhalte werden analysiert, nach Firmen und Datum sortiert und als DOCX-Dateien gespeichert.

## Features

- **PDF- und Bild-Texterkennung** (OCR mit Tesseract)
- **Automatische Dateiumbenennung** nach Firma und Datum
- **Speicherung als DOCX**
- **Fehlerhandling**: Fehlerhafte Dateien werden separat abgelegt
- **GUI** für einfache Bedienung

## Voraussetzungen

- **Python 3.10+**
- Installierte Python-Pakete:
  - `python-docx`
  - `pytesseract`
  - `pymupdf`
  - `openpyxl`
  - `python-dateutil`
- **Tesseract OCR** (Systeminstallation erforderlich)

### Installation der Abhängigkeiten

```sh
pip install python-docx pytesseract pymupdf openpyxl python-dateutil
```

**Tesseract OCR:**  
[Download für Windows](https://github.com/tesseract-ocr/tesseract/wiki#windows)  
Nach der Installation ggf. den Pfad zu `tesseract.exe` in der Umgebungsvariable `PATH` ergänzen.

## Nutzung

1. **Projekt starten:**
   ```sh
   python main.py
   ```
2. **Dateien auswählen:**  
   Über die GUI können PDF- oder Bilddateien ausgewählt werden.
3. **Verarbeitung:**  
   Die Dateien werden analysiert, umbenannt und im Zielordner gespeichert.

## Konfiguration

- **config.json**: Enthält Einstellungen wie Logging-Level.
- **firmen.txt**: Liste der zu erkennenden Firmennamen (eine Firma pro Zeile).
- **toolinfo.json**: (Optional) Weitere Tool-Informationen.

## Fehlerbehandlung

- Fehlerhafte oder nicht verarbeitbare Dateien werden automatisch in den Ordner `errors` verschoben.

## Hinweise

- Das Tool benötigt Schreibrechte im Zielverzeichnis.
- Für beste OCR-Ergebnisse sollten die Eingabedateien gut lesbar sein.

---

**Autor:**  
Markus Dickscheit
**Lizenz:** MIT (oder eigene Lizenz angeben)