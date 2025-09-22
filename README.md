 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/README.md b/README.md
index eb6846f998257d00751fe30d08f43c9fe7918f55..6f3c26ae6437dc04cec35307687a69e402326c16 100644
--- a/README.md
+++ b/README.md
@@ -1,33 +1,34 @@
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
-- Dateiname des Ausgabe-PDFs via `output_filename_format` steuern (Platzhalter wie `{date}`, `{supplier_safe}`, `{invoice_no_safe}`, `{hash_short}`, `{original_name_safe}`, `{target_subdir_safe}`).
+- Dateiname des Ausgabe-PDFs via `output_filename_format` steuern; mehrere Varianten können in `output_filename_formats` gepflegt und in der GUI per Dropdown ausgewählt werden (Platzhalter wie `{date}`, `{supplier_safe}`, `{invoice_no_safe}`, `{hash_short}`, `{original_name_safe}`, `{target_subdir_safe}`).
+- Rechts im Tool gibt es einen Bereich „System-Konfiguration“, in dem sich der Ollama-Status prüfen und – sofern noch nicht vorhanden – eine Installation direkt aus der GUI anstoßen lässt.
 
 
 ### Neu in v4
 - Lieferantenprofil **CT-Bauprofi** hinzugefügt (hints, Whitelist, Betragsmuster, Nummer & Datum).
 
 
 ### Neu in v5
 - **Konfig-Schalter** `validation_max_days`: Datumsprüfung steuerbar.
   - `> 0` → Datum muss innerhalb der angegebenen Tage liegen (Standard: 370).
   - `0` oder negativ → **Archivmodus**: Datum wird **nicht** geprüft.
 
EOF
)