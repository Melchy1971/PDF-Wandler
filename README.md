# Invoice Sorter – Bereinigtes Bundle (v3)

Dieses Paket enthält:
- **gui_app.py** (bereinigt): korrigierte Newlines/F-Strings, funktionierende Vorschau `(text, method)`, Regex-Tester mit ISO-Datum, Sprachliste via `tesseract --list-langs`.
- **sorter.py**: stabile Extraktion inkl. CSV-Log, Duplikaterkennung, Whitelist-/Datum-Validierung, PDF-Deckblatt.
- **patterns.yaml** + **patterns/suppliers/***: erweiterte Lieferanten-Profile/Whitelists.
- **config.yaml**, **run_sorter.py**, **requirements.txt**, **Dockerfile**.

## Start (GUI)
```bash
pip install -r requirements.txt
python gui_app.py
```

## CLI
```bash
python run_sorter.py config.yaml patterns.yaml
```

## Hinweise
- Poppler/Tesseract-Pfade unter Windows in der GUI/`config.yaml` setzen.
- Supplier-spezifische Regeln in `patterns/suppliers/*.yaml` anpassen.


### Neu in v4
- Lieferantenprofil **CT-Bauprofi** hinzugefügt (hints, Whitelist, Betragsmuster, Nummer & Datum).


### Neu in v5
- **Konfig-Schalter** `validation_max_days`: Datumsprüfung steuerbar.
  - `> 0` → Datum muss innerhalb der angegebenen Tage liegen (Standard: 370).
  - `0` oder negativ → **Archivmodus**: Datum wird **nicht** geprüft.
