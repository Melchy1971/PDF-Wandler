# PDF Rechnung Changer

Ein lokales Tool zum **Analysieren**, **Benennen** und **Verschieben** von PDF‑Rechnungen – mit **OCR**‑Unterstützung (PyMuPDF + Tesseract). Es bringt eine komfortable **GUI**, einen einfachen **Hotfolder**‑Modus und hilfreiche **Diagnose**‑Werkzeuge mit.

> **Autor:** Markus Dickscheit  
> **Lizenz/Haftung:** Opensource zur freien Verwendung, **aber auf eigene Gefahr**.  
> **Variante:** CLEAN_START_v2 (mit OCR‑Sorter & Guards)

---

## Inhalt

- [Features](#features)
- [Systemvoraussetzungen](#systemvoraussetzungen)
- [Schnellstart](#schnellstart)
- [Installation](#installation)
- [GUI verwenden](#gui-verwenden)
- [Hotfolder verwenden](#hotfolder-verwenden)
- [Konfiguration (`config.yaml`)](#konfiguration-configyaml)
- [Patterns (`patterns.yaml`)](#patterns-patternsyaml)
- [Funktionsweise (Architektur)](#funktionsweise-architektur)
- [Shortcuts](#shortcuts)
- [CSV‑Logging](#csv-logging)
- [Diagnose/Support](#diagnosesupport)
- [Troubleshooting (FAQ)](#troubleshooting-faq)
- [Sicherheit & Datenschutz](#sicherheit--datenschutz)
- [Changelog](#changelog)
- [Lizenz & Danksagung](#lizenz--danksagung)

---

## Features

- **OCR‑fähig**: Text aus PDFs mit **PyMuPDF**; bei wenig/keinem Text automatische **OCR** über **pdf2image + Tesseract**.
- **Automatisches Benennen**: Dateinamen aus erkannten Feldern (Datum, Lieferant, Rechnungsnummer), Muster frei konfigurierbar.
- **Unknown‑Fallback**: Wenn Pflichtfelder fehlen, landet die PDF in `processed/unbekannt/` (keine Daten gehen verloren).
- **GUI**: Maximiert, mit Shortcuts, **Systemcheck**, **Systeminfo kopieren**, **Sorter‑Diagnose**, **Info/Beenden**.
- **Hotfolder**: Kleiner watcher‑ähnlicher Polling‑Modus zum unbeaufsichtigten Verarbeiten.
- **CSV‑Log**: Optionales Protokoll der Verarbeitung (Quelle, Ziel, Metadaten, Status).
- **Guards & Autocreate**: Legt fehlende Ordner (`inbox/`, `processed/`, `error/`, `logs/`) automatisch an; robuste Startprüfungen.
- **Portabel**: Keine Cloud, keine Telemetrie. Läuft lokal mit Python‑Umgebung.

---

## Systemvoraussetzungen

- **Python**: 3.x (getestet mit aktuellen 3.x‑Versionen)
- **Pakete** (per `requirements.txt`):  
  `pyyaml, pymupdf, PyPDF2, pdf2image, pytesseract, pillow`
- **Tesseract** (für OCR) – `tesseract` muss im PATH oder in `config.yaml` (`tesseract_cmd`) konfiguriert sein.
- **Poppler** (für `pdf2image`) – `pdftoppm`/`pdftocairo` im PATH oder `poppler_path` in `config.yaml` setzen.

> **Hinweis:** Der **Systemcheck** in der GUI zeigt sofort, ob Python‑Module, Tesseract und Poppler korrekt gefunden wurden.

---

## Schnellstart

### Windows
1. ZIP `PDF-Wandler_CLEAN_START_v2.zip` entpacken.
2. `start_gui.bat` doppelklicken (legt venv an, installiert Pakete, startet GUI).
3. Optional: `start_hotfolder.bat` für den Hotfolder‑Modus.

### Linux/macOS
```bash
chmod +x start_gui.sh start_hotfolder.sh
./start_gui.sh          # startet die GUI
# oder
./start_hotfolder.sh    # startet den Hotfolder
```

---

## Installation

Manuell (ohne Startskripte):
```bash
# in Projektordner wechseln
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
# Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python gui_app.py
```

**Tesseract & Poppler** installieren und deren Pfade in der GUI oder in `config.yaml` eintragen:
- `tesseract_cmd`: Pfad zur `tesseract`‑Binary (z. B. `C:\Program Files\Tesseract-OCR	esseract.exe`)
- `poppler_path`: Ordner mit `pdftoppm`/`pdftocairo` (z. B. `C:	ools\popplerin`)

---

## GUI verwenden

- **Eingang/Ausgang** wählen oder Standard belassen (`inbox/`, `processed/`).
- **Verarbeiten starten** (Strg+R). Der Log zeigt Fortschritt und Status (`ok`/`needs_review`).  
- **Stop** (Esc), **Beenden** (Strg+Q).
- **Systemcheck**: Prüft Python‑Module, Tesseract, Poppler; **Systeminfo kopieren** legt den Report in die Zwischenablage.
- **Sorter‑Diagnose**: Zeigt, welche Funktionen `sorter.py` bereitstellt und von wo sie geladen wurden.
- **Reiter**: Log, Vorschau, Fehler, **Rollen** (mit Bereich *Mitgliedsprofil bearbeiten* und eigenem Rollen-Reiter) und Regex-Tester.

**Info (F1)** zeigt:
- Toolname: *PDF Rechnung Changer*  
- Autor: *Markus Dickscheit*  
- Hinweis: *Opensource zur freien Verwendung aber auf eigene Gefahr*

---

## Hotfolder verwenden

Startskript:
```bash
# Windows
start_hotfolder.bat

# Linux/macOS
./start_hotfolder.sh
```

Direkt via Python:
```bash
python hotfolder.py --in inbox --done processed --err error --config config.yaml --patterns patterns.yaml
```

Der Hotfolder prüft regelmäßig `--in` auf neue PDFs, verarbeitet sie über `sorter.py` und verschiebt sie nach `--done` (bzw. bei Fehlern nach `--err`).

---

## Konfiguration (`config.yaml`)

Beispiel (mitgeliefert):
```yaml
input_dir: inbox
output_dir: processed
unknown_dir_name: unbekannt
tesseract_cmd: ""           # Pfad zu 'tesseract' oder leer, wenn im PATH
poppler_path: ""            # Pfad zu Poppler 'bin' oder leer, wenn im PATH
tesseract_lang: "deu+eng"   # OCR-Sprachen
use_ocr: true               # OCR aktivieren, wenn PDF wenig/keinen Text hat
dry_run: false              # nur simulieren (keine Dateien verschieben/umbenennen)
csv_log_path: "logs/processed.csv"
roles:
  - Administrator
  - Buchhaltung
output_filename_format: "{date}_{supplier}_{invoice_no}.pdf"
```

**Felder**:
- `input_dir` / `output_dir`: Eingangs‑/Zielordner
- `unknown_dir_name`: Zielordner (unter `output_dir`) für unvollständige Metadaten
- `tesseract_cmd` / `poppler_path`: Pfade für OCR‑Tools
- `tesseract_lang`: OCR‑Sprachen (z. B. `deu`, `eng`, `deu+eng`)
- `use_ocr`: wechselt bei wenig/keinem extrahierten Text automatisch zu OCR
- `dry_run`: nur Simulation (nichts wird geschrieben/verschoben)
- `csv_log_path`: optionaler Pfad für CSV‑Protokoll
- `roles`: optionale Liste von Rollenbezeichnungen für den Reiter "Rollen"
- `output_filename_format`: Formatstring für Zieldateinamen (Platzhalter siehe unten)

**Platzhalter** (in `output_filename_format`):
- `{date}` – normalisiertes Datum (z. B. `2025-03-01`)
- `{supplier}` – erkannter Lieferant (bereinigt)
- `{invoice_no}` – erkannte Rechnungsnummer (bereinigt)

---

## Patterns (`patterns.yaml`)

Beispiel (mitgeliefert):
```yaml
invoice_number_patterns:
  - "Rechnungs(?:nummer|nr\.?)\s*[:#]?\s*([A-Z0-9\-\/]+)"
  - "Invoice\s*(?:No\.?|Number)\s*[:#]?\s*([A-Z0-9\-\/]+)"
  - "Beleg(?:nummer|nr\.?)\s*[:#]?\s*([A-Z0-9\-\/]+)"
date_patterns:
  - "(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})"
  - "(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})"
supplier_hints:
  Deutsche Telekom: ["telekom", "t-mobile", "telekom deutschland"]
  Vodafone: ["vodafone"]
  Amazon: ["amazon services", "amazon eu", "amazon.de"]
  REWE: ["rewe markt", "rewe"]
  E.ON: ["e.on", "eon"]
  IKEA: ["ikea"]
  Deutsche Bahn: ["db fernverkehr", "deutsche bahn", "bahn.de"]
```

- **Rechnungsnummer**: Liste von Regexen, die **eine** Gruppe mit der Nummer enthalten müssen.
- **Datum**: Liste von Regexen, die **eine** Gruppe mit dem Datum liefern; es wird nach `YYYY-MM-DD` normalisiert.
- **Lieferant**: `supplier_hints` ist eine einfache Schlüsselwort‑Suche (Kleinbuchstaben‑Abgleich) über den Text.

---

## Funktionsweise (Architektur)

- `gui_app.py`
  - GUI (Tkinter), Start maximiert, Menüs & Shortcuts
  - Systemcheck, Systeminfo kopieren, Sorter‑Diagnose
  - **Fallback**: Wenn `sorter.process_all` fehlt → interner Lauf; wenn `sorter.process_pdf` fehlt → Move nach `processed/unbekannt`
  - CSV‑Log optional
- `sorter.py` (**OCR‑Variante**)
  - `extract_text_from_pdf(pdf)`: PyMuPDF‑Text; bei wenig Text OCR über `pdf2image + pytesseract`
  - `analyze_pdf(...)`: zieht Felder gemäß `patterns.yaml`
  - `process_pdf(...)`: erzeugt Dateiname, verschiebt PDF ins Ziel
  - `process_all(...)`: iteriert `input_dir`, ruft `progress_fn`, schreibt optional CSV
- `hotfolder.py`: Polling‑Hotfolder, nutzt `sorter.process_pdf`

---

## Shortcuts

- **Strg+S** – Konfiguration speichern
- **Strg+O** – Konfiguration öffnen
- **Strg+R** – Verarbeitung starten
- **Esc / F6** – Stop
- **Strg+Q** – Beenden
- **F1** – Info
- (macOS) **⌘S/⌘O/⌘R/⌘Q**

---

## CSV‑Logging

Wenn `csv_log_path` gesetzt ist, schreibt `sorter.process_all` pro Datei eine Zeile:
```
src;target;supplier;invoice_no;date;total;iban;status;method;ts
```

- `status`: `ok` oder `needs_review`
- `method`: z. B. `pymupdf` oder `pymupdf+ocr`
- `ts`: ISO‑Zeitstempel

---

## Diagnose/Support

- **Hilfe → Systemcheck**: Module (PyYAML, PyMuPDF, PyPDF2, pdf2image, pytesseract, Pillow), Tesseract, Poppler
- **Hilfe → Systeminfo kopieren**: legt den Check in die Zwischenablage
- **Hilfe → Sorter‑Diagnose**: zeigt Pfad und verfügbare Funktionen von `sorter.py`

---

## Troubleshooting (FAQ)

**„ModuleNotFoundError: No module named 'yaml'“**  
→ Pakete installieren: `pip install -r requirements.txt`

**Tesseract/Poppler wird nicht gefunden**  
→ Pfade in `config.yaml` setzen: `tesseract_cmd`, `poppler_path`  
→ Im Systemcheck prüfen, ob `tesseract`, `pdftoppm`, `pdftocairo` erkannt werden.

**OCR zu langsam**  
→ `tesseract_lang` möglichst schlank wählen (z. B. `deu` statt `deu+eng`).  
→ DPI in `pdf2image` nur bei Bedarf erhöhen (Standard im Code: 300 dpi).

**Datei wird nicht umbenannt**  
→ Felder fehlen → landet in `processed/unbekannt`.  
→ `patterns.yaml` anpassen und erneut versuchen.

**Beenden hängt**  
→ Mit **Esc** stoppen, dann **Strg+Q**. Hintergrundthreads werden beim Exit beendet; notfalls Fenster schließen.

**Lange Pfade unter Windows**  
→ System‑Einstellung „lange Dateinamen“ aktivieren oder kürzere Zielpfade wählen.

---

## Sicherheit & Datenschutz

- Das Tool arbeitet **offline** und lokal.
- Es werden keine Daten an Dritte übertragen.
- Prüfe Ordnerrechte und Backups, bevor du produktiv verarbeitest.

---

## Changelog

**CLEAN_START_v2**
- OCR‑fähiger `sorter.py` (PyMuPDF, pdf2image, pytesseract)
- Robustere Guards beim Start (Autocreate & fehlende Variablen)
- Systemcheck, Systeminfo kopieren, Sorter‑Diagnose
- Fallback‑Verarbeitung ohne Absturz
- Startskripte für Windows & Linux/macOS
- CSV‑Log optional

---

## Lizenz & Danksagung

- **Lizenz/Haftung**: Opensource zur freien Verwendung, aber **ohne Gewähr** und **auf eigene Gefahr**.  
- Danke an alle Maintainer von **Tesseract**, **Poppler**, **PyMuPDF**, **pdf2image**, **Pillow** und **PyYAML**.
