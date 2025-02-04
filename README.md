PDF-Wandler

✨ Effiziente Dateiorganisation leicht gemacht ✨

Der PDF-Wandler hilft Ihnen, Dateien automatisch umzubenennen und zu organisieren, indem er wichtige Informationen wie Datum, Firmenname und Rechnungsnummer extrahiert.

🛠️ Installation

Stellen Sie sicher, dass die folgenden Python-Pakete installiert sind:

pip install python-dateutil requests

Erforderliche Pakete:

tkinter (GUI-Unterstützung)

dateutil (Datumserkennung)

requests (Netzwerkfunktionen)

🔧 Konfiguration

Die Einstellungen werden in der config.json Datei verwaltet. Standardwerte sind im main.py hinterlegt.

✨ Standardkonfiguration

{
    "DEFAULT_SOURCE_DIR": "",
    "BACKUP_DIR": "backup",
    "ALLOWED_EXTENSIONS": ["pdf", "png", "jpg", "jpeg", "docx", "xlsx", "eml"],
    "BATCH_SIZE": 10,
    "DATE_FORMATS": ["%Y.%m.%d", "%Y-%m-%d", "%d.%m.%Y"],
    "MAIN_TARGET_DIR": "",
    "LOG_LEVEL": "DEBUG",
    "FILENAME_PATTERN": "{date}_{company}_{number}.{ext}",
    "DARK_MODE": false
}

🔍 Verwendung

Starten Sie das Tool und wählen Sie das Quellverzeichnis.

Klicken Sie auf "Dateien umbenennen und organisieren" – die relevanten Informationen werden automatisch extrahiert.

Die Dateien werden analysiert und organisiert:

Umbenennung nach {date}_{company}_{number}.{ext}

Automatische Verschiebung in entsprechende Unterordner

Erweiterte Funktionen:

👥 Firmenpflege: Verwaltung der Firmennamen-Liste

⚙ Konfiguration: Anpassen der Standardeinstellungen

📊 Bericht anzeigen: Übersicht der verarbeiteten Dateien

🔍 Vorschau: Neue Dateinamen prüfen, bevor sie umbenannt werden

🎨 Dark Mode: Passen Sie die Benutzeroberfläche an

❓ Hilfe: Erklärungen zur Nutzung des Tools

📝 Protokollfenster: Detaillierte Logs zur Fehlerbehebung

🔄 Funktionen auf einen Blick

✔ Automatische Dateiumbenennung & Organisation

✔ Vorschau der neuen Dateinamen vor der Umbenennung

✔ Fehlerprotokolle & Berichte für bessere Nachverfolgung

✔ Konfigurierbare Dateiformate & -strukturen

✔ Dark Mode für eine angenehme Nutzung

🌐 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert und frei nutzbar.

Mit dem PDF-Wandler behalten Sie den Überblick über Ihre Dokumente – schnell, effizient und unkompliziert! 📂✨