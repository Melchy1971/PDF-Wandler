# Benutzerhandbuch – PDF Rechnung Changer

Version: CLEAN_START_v2 • Plattform: Windows, Linux, macOS

---

## 1. Zweck und Funktionsumfang

**PDF Rechnung Changer** ist ein lokales Werkzeug zum **Analysieren**, **Benennen** und **Verschieben** von PDF‑Rechnungen. Es bietet eine grafische Oberfläche (GUI), optionalen **Hotfolder‑Betrieb** und **OCR** (Texterkennung) über Tesseract + Poppler, falls ein PDF kaum eingebetteten Text enthält.

Kernfunktionen:
- Extraktion von Rechnungsdaten (Rechnungsnummer, Datum, Lieferant; optional Betrag, IBAN)
- Automatisches Umbenennen gemäß Muster (z. B. `{date}_{supplier}_{invoice_no}.pdf`)
- Fallback in einen „Unbekannt“-Ordner, wenn Pflichtfelder fehlen
- CSV‑Protokollierung (optional)
- Hotfolder‑Modus für unbeaufsichtigtes Verarbeiten
- Diagnose: Systemcheck, Sorter‑Diagnose, Systeminfo kopieren

---

## 2. Systemvoraussetzungen

- **Python** 3.x
- Python‑Pakete: `pyyaml`, `pymupdf`, `PyPDF2`, `pdf2image`, `pytesseract`, `pillow`  
  (installierbar via `requirements.txt`)
- **Tesseract OCR** (Binary `tesseract`)
- **Poppler** (Tools `pdftoppm`/`pdftocairo` für `pdf2image`)

> Hinweis: Der Systemcheck (Menü **Hilfe → Systemcheck**) prüft alle Abhängigkeiten und zeigt gefundene Versionen und Pfade.

---

## 3. Installation und Schnellstart

### 3.1 Windows (empfohlen mit Startskript)
1. ZIP `PDF-Wandler_CLEAN_START_v2.zip` entpacken.
2. `start_gui.bat` ausführen.  
   Das Skript erstellt (falls nötig) eine virtuelle Umgebung, installiert Abhängigkeiten und startet die GUI.
3. Optional: `start_hotfolder.bat` für den Hotfolder‑Betrieb.

### 3.2 Linux/macOS
```bash
chmod +x start_gui.sh start_hotfolder.sh
./start_gui.sh          # GUI
# oder
./start_hotfolder.sh    # Hotfolder
```

### 3.3 Manuelle Installation
```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
python gui_app.py
```

---

## 4. Erstinbetriebnahme

1. Beim ersten Start legt die Anwendung automatisch folgende Ordner an (falls nicht vorhanden):  
   `inbox/`, `processed/`, `processed/unbekannt/`, `error/`, `logs/`.
2. Öffnen Sie **Hilfe → Systemcheck**. Prüfen Sie, ob
   - Python‑Module vorhanden sind,
   - **Tesseract** gefunden wird (Version),
   - **Poppler** (`pdftoppm`/`pdftocairo`) erkannt wird.
3. Tragen Sie ggf. in der GUI oder in `config.yaml` die Pfade ein:
   - `tesseract_cmd` (Pfad zur `tesseract`‑Binary)
   - `poppler_path` (Ordner, der `pdftoppm`/`pdftocairo` enthält)
4. Speichern Sie die Konfiguration (**Strg+S**).

---

## 5. Bedienoberfläche

### 5.1 Hauptfenster
- **Eingang**: Ordner mit zu verarbeitenden PDFs (Standard: `inbox/`)
- **Ausgang**: Zielordner (Standard: `processed/`)
- **Optionen**:
  - OCR verwenden (empfohlen)
  - Dry‑Run (Simulation ohne Schreibzugriffe)
  - CSV aktiv + Pfad (z. B. `logs/processed.csv`)
- **Buttons**:
  - **Verarbeiten starten** (Strg+R)
  - **Stop** (Esc)
  - **Info** (F1)
  - **Beenden** (Strg+Q)
- **Reiter**: Log (Fortschritt), Vorschau (PDF-Text), Fehler (Problemübersicht), **Rollen** (Rollenliste je Profil) und Regex-Tester.
- **Logfenster**: Laufende Protokoll‑ und Statusmeldungen

### 5.2 Menü
- **Datei**
  - *Konfig öffnen…* (Strg+O)
  - *Konfig speichern* (Strg+S)
  - *Verarbeiten starten* (Strg+R)
  - *Stop* (Esc)
  - *Beenden* (Strg+Q)
- **Hilfe**
  - *Systemcheck*
  - *Systeminfo kopieren*
  - *Sorter‑Diagnose*
  - *Info* (F1)

### 5.3 Tastenkürzel
- Strg+S / Strg+O / Strg+R / Strg+Q, Esc, F1  
- macOS: ⌘S / ⌘O / ⌘R / ⌘Q

---

## 6. Typischer Arbeitsablauf (GUI)

1. **Eingang/Ausgang** prüfen oder setzen.
2. **Patterns** in `patterns.yaml` ggf. anpassen (siehe Kapitel 8).
3. **Verarbeiten starten**. Im Log erscheinen Zeilen wie:
   - `[i/total] <Datei> -> ok` (vollständig erkannt) oder `needs_review` (unvollständig).
4. Ergebnis:
   - Umbenannte Dateien landen in `processed/`.
   - Unvollständige Dateien landen in `processed/unbekannt/`.
5. Optional: CSV‑Log prüfen (`logs/processed.csv`).

---

## 7. Konfiguration (`config.yaml`)

Beispielfile (mitgeliefert):
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

Parameter:
- **input_dir** / **output_dir**: Eingangs-/Zielverzeichnis
- **unknown_dir_name**: Unterordner in `output_dir` für unvollständige Datensätze
- **tesseract_cmd**: Pfad zur Tesseract‑Binary
- **poppler_path**: Ordner, der `pdftoppm`/`pdftocairo` enthält
- **tesseract_lang**: OCR‑Sprachen (z. B. `deu`, `eng`, `deu+eng`)
- **use_ocr**: Bei wenig/keinem eingebetteten Text automatisch OCR verwenden
- **dry_run**: Simulation
- **csv_log_path**: Pfad zur CSV‑Protokolldatei
- **roles**: Optionale Liste von Rollen je Profil für den Rollen-Reiter
- **output_filename_format**: Muster für Zieldateinamen

Platzhalter im Dateinamen‑Muster:
- `{date}` (normalisiert: `YYYY-MM-DD`)
- `{supplier}` (bereinigt)
- `{invoice_no}` (bereinigt)

---

## 8. Mustererkennung (`patterns.yaml`)

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

Hinweise:
- Regexe bei **invoice_number_patterns** und **date_patterns** müssen **jeweils genau eine Gruppe** für den relevanten Wert liefern.
- `supplier_hints` ist eine einfache Schlüsselwortliste pro Lieferant (case‑insensitive Vergleich).

---

## 9. Hotfolder‑Betrieb

Start (Beispiele):
```bash
# Windows
start_hotfolder.bat

# Linux/macOS
./start_hotfolder.sh
```
Direkt:
```bash
python hotfolder.py --in inbox --done processed --err error --config config.yaml --patterns patterns.yaml
```
Ablauf:
- Das Skript pollt den `--in`‑Ordner.
- Jede neue/ruhende PDF wird mit `sorter.process_pdf` verarbeitet.
- Erfolgreiche Dateien wandern nach `--done`, fehlerhafte nach `--err`.

---

## 10. CSV‑Protokoll

Wenn `csv_log_path` gesetzt ist, wird pro Datei protokolliert:
```
src;target;supplier;invoice_no;date;total;iban;status;method;ts
```
- **status**: `ok` oder `needs_review`
- **method**: z. B. `pymupdf` oder `pymupdf+ocr`
- **ts**: ISO‑Zeitstempel

---

## 11. Diagnosefunktionen

- **Hilfe → Systemcheck**: zeigt installierte Python‑Module, Tesseract/Poppler und Pfade.
- **Hilfe → Systeminfo kopieren**: legt die Ausgabe des Systemchecks in die Zwischenablage.
- **Hilfe → Sorter‑Diagnose**: zeigt Pfad der geladenen `sorter.py` sowie vorhandene Funktionen (`analyze_pdf`, `process_pdf`, `process_all`, `extract_text_from_pdf`).

---

## 12. Qualität & OCR‑Leistung

- Wählen Sie passende OCR‑Sprachen (`tesseract_lang`), z. B. `deu` oder `deu+eng`.
- Je höher die Scan‑Qualität (DPI, Kontrast), desto zuverlässiger die Ergebnisse.
- OCR wird nur genutzt, wenn PyMuPDF sehr wenig/keinen Text extrahieren konnte.

---

## 13. Fehlersuche (Troubleshooting)

**Kein `yaml`‑Modul / andere Module fehlen**  
- Installation: `pip install -r requirements.txt`  
- Systemcheck aufrufen und Hinweise beachten.

**Tesseract oder Poppler wird nicht gefunden**  
- Pfade in `config.yaml` setzen: `tesseract_cmd`, `poppler_path`  
- Systemcheck prüfen, ob `tesseract`, `pdftoppm`, `pdftocairo` erkannt werden.

**Datei wird nicht umbenannt**  
- Felder konnten nicht vollständig ermittelt werden. Datei wird nach `processed/unbekannt/` verschoben.  
- `patterns.yaml` erweitern/optimieren.

**Beenden reagiert nicht sofort**  
- Zunächst **Stop** (Esc), dann **Beenden** (Strg+Q).

**Hotfolder bewegt Dateien nicht**  
- Ordnerrechte prüfen, Datei ist ggf. „gesperrt“ (noch in Kopie).  
- Wartezeit erhöhen (`--interval`).

---

## 14. Best Practices

- `patterns.yaml` iterativ verbessern (Begriffe der häufigsten Lieferanten ergänzen).
- OCR‑Sprachen so schlank wie möglich halten (z. B. nur `deu`).
- Strukturierte Zielordner wählen und `output_filename_format` an Prozess anpassen.
- Regelmäßig CSV‑Log sichern/auswerten.

---

## 15. Verzeichnisstruktur (Standard)

```
/
├─ gui_app.py
├─ sorter.py
├─ hotfolder.py
├─ config.yaml
├─ patterns.yaml
├─ requirements.txt
├─ README.md
├─ start_gui.bat / start_gui.sh
├─ start_hotfolder.bat / start_hotfolder.sh
├─ inbox/
├─ processed/
│  └─ unbekannt/
├─ error/
└─ logs/
```

---

## 16. Lizenz & Haftung

- Lizenz: Opensource zur freien Verwendung
- Haftung: ohne Gewähr; Nutzung **auf eigene Gefahr**

**Autor:** Markus Dickscheit

---

## 17. Changelog (Auszug)

**CLEAN_START_v2**  
- OCR‑fähiger Sorter (PyMuPDF + pdf2image + pytesseract)
- Verbesserte Start‑Guards & Ordner‑Autocreate
- Systemcheck, Systeminfo kopieren, Sorter‑Diagnose
- CSV‑Protokoll optional
- Hotfolder‑Modus

---

## 18. Support‑Hinweise

- **Systemcheck** ausführen und **Systeminfo kopieren** für Supportanfragen beilegen.
- **Sorter‑Diagnose** ausführen und Log mit Pfad/Funktionsübersicht beilegen.
- Ggf. Beispiel‑PDF (ohne personenbezogene Daten) und Auszüge aus `patterns.yaml` bereitstellen.
