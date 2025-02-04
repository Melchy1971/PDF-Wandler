import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES  # Import TkinterDnD for drag & drop support
import os
import logging
import shutil
import asyncio
import json
from datetime import datetime
from text_extraction import extract_text_from_pdf, extract_text_from_image
import re
import dateutil.parser  # Ensure the python-dateutil package is installed
import requests  # Ensure the requests package is installed

# Mapping für deutsche Monatsnamen
GERMAN_MONTHS = {
    "Januar": "January", "Februar": "February", "März": "March", "April": "April",
    "Mai": "May", "Juni": "June", "Juli": "July", "August": "August",
    "September": "September", "Oktober": "October", "November": "November", "Dezember": "December",
    "Jan": "Jan", "Feb": "Feb", "Mär": "Mar", "Mar": "Mar", "Apr": "Apr", "Mai": "May",
    "May": "May", "Jun": "Jun", "Jul": "Jul", "Aug": "Aug", "Sep": "Sep", "Okt": "Oct",
    "Oct": "Oct", "Nov": "Nov", "Dez": "Dec", "Dec": "Dec"
}

# Verbesserte reguläre Ausdrücke für verschiedene Datumsformate
DATE_PATTERNS = [
    (r"\b(\d{4})[-/.](\d{2})[-/.](\d{2})\b", "%Y-%m-%d"),  # ISO 8601 (2024-02-03)
    (r"\b(\d{2})[-/.](\d{2})[-/.](\d{4})\b", "%d.%m.%Y"),  # EU (03.02.2024)
    (r"\b(\d{2})/(\d{2})/(\d{4})\b", "%m/%d/%Y"),  # USA (02/03/2024)
    (r"\b(\d{4})/(\d{2})/(\d{2})\b", "%Y/%m/%d"),  # Asien (2024/02/03)
    (r"\b(\d{1,2})[.\s]?(Jan|Feb|Mär|Mar|Apr|Mai|May|Jun|Jul|Aug|Sep|Okt|Oct|Nov|Dez|Dec)[.]?\s?(\d{4})\b", "%d %b %Y"),  # Deutsche Monatsnamen
    (r"\b(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})\b", "%d %B %Y"),  # Englische Monatsnamen
    (r"\b(\d{8})\b", "%Y%m%d"),  # Kompaktformat (20240203)
    (r"\b(\d{1,2}) (Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember) (\d{4})\b", "%d %B %Y"),  # Deutsche Monatsnamen (17 Juli 2018)
]

def detect_date(text):
    """Erkennt ein Datum und gibt es im Format YYYY-MM-DD zurück."""
    try:
        if not text:
            return None

        # Ersetze deutsche Monatsnamen mit englischen (falls nötig)
        for ger, eng in GERMAN_MONTHS.items():
            text = re.sub(rf"\b{ger}\b", eng, text, flags=re.IGNORECASE)

        # Versuche bekannte Formate zu erkennen
        for pattern, date_format in DATE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    extracted_date = datetime.strptime(" ".join(match.groups()), date_format).strftime("%Y-%m-%d")
                    return extracted_date
                except ValueError:
                    continue
        
        # Falls kein direktes Muster erkannt wurde, nutze `dateutil.parser`
        return dateutil.parser.parse(text, dayfirst=True).strftime("%Y-%m-%d")

    except (ValueError, TypeError, Exception) as e:
        logging.error(f"Fehler bei der Datumserkennung: {e}")
        return None

# Initiale Sprachkonfiguration
current_language = 'de'

FIRMEN_DATEI = "firmen.txt"
CONFIG_DATEI = "config.json"

# Definiere das Logging-Format
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Konfiguriere das Logging
logging.basicConfig(
    level=logging.DEBUG,
    format=log_format,  # Corrected format string
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler('app.log', 'w', 'utf-8'), logging.StreamHandler()]
)

logging.info("Programm gestartet. Warte auf Benutzereingaben...")

# Berichtsvariablen
processed_files = []
errors = []
processing_start_time = None

# Standardkonfiguration
default_config = {
    "DEFAULT_SOURCE_DIR": "",
    "BACKUP_DIR": "backup",
    "ALLOWED_EXTENSIONS": ["pdf", "png", "jpg", "jpeg", "docx", "xlsx", "eml"],
    "BATCH_SIZE": 10,
    "DATE_FORMATS": ["%Y.%m.%d", "%Y-%m-%d", "%d.%m.%Y"],
    "MAIN_TARGET_DIR": "",  # Hinzufügen
    "LOG_LEVEL": "DEBUG",  # Hinzufügen
    "FILENAME_PATTERN": "{date}_{company}_{number}.{ext}",  # Hinzufügen
    "DARK_MODE": False  # Hinzufügen
}

config = default_config.copy()

def set_log_level(level):
    """
    Setzt das Log-Level.

    Args:
        level (str): Das Log-Level (z.B. DEBUG, INFO, WARNING, ERROR).
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')
    logging.getLogger().setLevel(numeric_level)
    logging.info(f"Log-Level gesetzt auf: {level}")

def setup_logging():
    """
    Konfiguriert das Logging-Setup.
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, config.get("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG),
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler('app.log', mode='w', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def load_config():
    """
    Funktion zum Laden der Konfiguration.
    """
    global config
    if os.path.exists(CONFIG_DATEI):
        try:
            with open(CONFIG_DATEI, 'r', encoding='utf-8') as config_file:
                loaded_config = json.load(config_file)
                if isinstance(loaded_config, dict):
                    config.update({key: loaded_config.get(key, default) for key, default in default_config.items()})
                    logging.debug(f"Aktuelle Konfiguration: {json.dumps(config, indent=2)}")
                else:
                    logging.error("Config-Datei ist beschädigt. Standardwerte werden verwendet.")
        except json.JSONDecodeError as e:
            logging.error(f"Config-Datei ist beschädigt oder enthält ungültiges JSON: {e}. Standardwerte werden verwendet.")
        except IOError as e:
            logging.error(f"Fehler beim Lesen der Config-Datei: {e}. Standardwerte werden verwendet.")
        except Exception as e:
            logging.error(f"Unbekannter Fehler beim Laden der Konfiguration: {e}. Standardwerte werden verwendet.")
            config = default_config.copy()
    set_log_level(config.get("LOG_LEVEL", "DEBUG"))
    setup_logging()

def save_config():
    """
    Funktion zum Speichern der Konfiguration.
    """
    temp_config_file = CONFIG_DATEI + ".tmp"
    try:
        with open(temp_config_file, 'w', encoding='utf-8') as config_file:
            json.dump(config, config_file, indent=4)
        os.replace(temp_config_file, CONFIG_DATEI)
        logging.info("Konfiguration erfolgreich gespeichert.")
    except IOError as e:
        logging.error(f"Fehler beim Schreiben der Config-Datei: {e}")
        if os.path.exists(temp_config_file):
            os.remove(temp_config_file)
    except Exception as e:
        logging.error(f"Unbekannter Fehler beim Speichern der Konfiguration: {e}")
        if os.path.exists(temp_config_file):
            os.remove(temp_config_file)

def load_firmennamen():
    """
    Funktion zum Laden der Firmennamen aus der Datei.

    Returns:
        list: Eine Liste der geladenen Firmennamen.
    """
    if os.path.exists(FIRMEN_DATEI):
        try:
            with open(FIRMEN_DATEI, 'r', encoding='utf-8-sig') as file:
                firmennamen = [line.strip() for line in file.readlines()]
                logging.info(f"{len(firmennamen)} Firmennamen erfolgreich geladen.")
                return firmennamen
        except UnicodeDecodeError as e:
            logging.error(f"Fehler: Kodierungsproblem mit {FIRMEN_DATEI}: {e}")
        except IOError as e:
            logging.error(f"Fehler beim Lesen der Datei {FIRMEN_DATEI}: {e}")
        except Exception as e:
            logging.error(f"Unbekannter Fehler beim Laden der Firmennamen: {e}")
    return []

def save_firmennamen(firmennamen):
    """
    Funktion zum Speichern der Firmennamen in die Datei.

    Args:
        firmennamen (list): Eine Liste der Firmennamen, die gespeichert werden sollen.
    """
    try:
        with open(FIRMEN_DATEI, 'w', encoding='utf-8') as file:
            file.write('\n'.join(firmennamen))
        logging.info(f"{len(firmennamen)} Firmennamen erfolgreich gespeichert.")
    except IOError as e:
        logging.error(f"Fehler beim Schreiben der Datei {FIRMEN_DATEI}: {e}")
    except Exception as e:
        logging.error(f"Unbekannter Fehler beim Speichern der Firmennamen: {e}")

def open_firmenpflege(root):
    """
    Funktion zum Anzeigen des Firmenpflege-Fensters.

    Args:
        root (tk.Tk): Das Hauptfenster der Anwendung.
    """
    try:
        def add_firma():
            new_firma = simpledialog.askstring("Neue Firma", "Bitte geben Sie den Namen der neuen Firma ein:")
            if new_firma:
                if not new_firma.strip():
                    messagebox.showerror("Fehler", "Der Firmenname darf nicht leer sein.")
                    return
                if any(char in new_firma for char in r'\/:*?"<>|'):
                    messagebox.showerror("Fehler", "Der Firmenname darf keine ungültigen Zeichen enthalten.")
                    return
                firmennamen.append(new_firma)
                listbox.insert(tk.END, new_firma)
                save_firmennamen(firmennamen)

        def remove_firma():
            selected = listbox.curselection()
            if selected:
                firmennamen.pop(selected[0])
                listbox.delete(selected)
                save_firmennamen(firmennamen)

        firmennamen = load_firmennamen()

        pflege_window = tk.Toplevel(root)
        pflege_window.title("Firmenpflege")

        listbox = tk.Listbox(pflege_window)
        listbox.pack(fill=tk.BOTH, expand=True)

        for firma in firmennamen:
            listbox.insert(tk.END, firma)

        add_button = tk.Button(pflege_window, text="Firma hinzufügen", command=add_firma)
        add_button.pack(side=tk.LEFT, padx=10, pady=10)

        remove_button = tk.Button(pflege_window, text="Firma entfernen", command=remove_firma)
        remove_button.pack(side=tk.RIGHT, padx=10, pady=10)
    except Exception as e:
        logging.error(f"Fehler beim Öffnen der Firmenpflege: {e}")
        messagebox.showerror("Fehler", "Fehler beim Öffnen der Firmenpflege.")

def open_config(root):
    """
    Funktion zum Anzeigen des Konfigurations-Fensters.

    Args:
        root (tk.Tk): Das Hauptfenster der Anwendung.
    """
    try:
        def save_changes():
            config["DEFAULT_SOURCE_DIR"] = default_source_dir.get()
            config["BACKUP_DIR"] = backup_dir.get()
            config["ALLOWED_EXTENSIONS"] = allowed_extensions.get().split(',')
            config["BATCH_SIZE"] = int(batch_size.get())
            config["DATE_FORMATS"] = date_formats.get().split(',')
            config["MAIN_TARGET_DIR"] = main_target_dir.get()
            config["LOG_LEVEL"] = log_level.get()
            config["FILENAME_PATTERN"] = filename_pattern.get()
            config["DARK_MODE"] = dark_mode_var.get()
            save_config()
            set_log_level(config["LOG_LEVEL"])
            if config["DARK_MODE"]:
                apply_dark_mode(root)
            config_window.destroy()

        config_window = tk.Toplevel(root)
        config_window.title("Konfiguration")

        tk.Label(config_window, text="Standard-Quellverzeichnis:").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        default_source_dir = tk.Entry(config_window, width=50)
        default_source_dir.grid(row=0, column=1, padx=10, pady=5, sticky='w')
        default_source_dir.insert(0, config["DEFAULT_SOURCE_DIR"])

        tk.Label(config_window, text="Backup-Verzeichnis:").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        backup_dir = tk.Entry(config_window, width=50)
        backup_dir.grid(row=1, column=1, padx=10, pady=5, sticky='w')
        backup_dir.insert(0, config["BACKUP_DIR"])

        tk.Label(config_window, text="Erlaubte Dateierweiterungen (kommagetrennt):").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        allowed_extensions = tk.Entry(config_window, width=50)
        allowed_extensions.grid(row=2, column=1, padx=10, pady=5, sticky='w')
        allowed_extensions.insert(0, ','.join(config["ALLOWED_EXTENSIONS"]))

        tk.Label(config_window, text="Batch-Größe:").grid(row=3, column=0, padx=10, pady=5, sticky='w')
        batch_size = tk.Entry(config_window, width=50)
        batch_size.grid(row=3, column=1, padx=10, pady=5, sticky='w')
        batch_size.insert(0, config["BATCH_SIZE"])

        tk.Label(config_window, text="Datumsformate (kommagetrennt):").grid(row=4, column=0, padx=10, pady=5, sticky='w')
        date_formats = tk.Entry(config_window, width=50)
        date_formats.grid(row=4, column=1, padx=10, pady=5, sticky='w')
        date_formats.insert(0, ','.join(config["DATE_FORMATS"]))

        tk.Label(config_window, text="Hauptzielordner:").grid(row=5, column=0, padx=10, pady=5, sticky='w')
        main_target_dir = tk.Entry(config_window, width=50)
        main_target_dir.grid(row=5, column=1, padx=10, pady=5, sticky='w')
        main_target_dir.insert(0, config.get("MAIN_TARGET_DIR", ""))

        tk.Label(config_window, text="Log-Level:").grid(row=6, column=0, padx=10, pady=5, sticky='w')
        log_level = ttk.Combobox(config_window, values=["DEBUG", "INFO", "WARNING", "ERROR"])
        log_level.grid(row=6, column=1, padx=10, pady=5, sticky='w')
        log_level.set(config.get("LOG_LEVEL", "DEBUG"))

        tk.Label(config_window, text="Dateinamenmuster:").grid(row=7, column=0, padx=10, pady=5, sticky='w')
        filename_pattern = tk.Entry(config_window, width=50)
        filename_pattern.grid(row=7, column=1, padx=10, pady=5, sticky='w')
        filename_pattern.insert(0, config.get("FILENAME_PATTERN", "{date}_{company}_{number}.{ext}"))

        tk.Label(config_window, text="Dark Mode:").grid(row=8, column=0, padx=10, pady=5, sticky='w')
        dark_mode_var = tk.BooleanVar(value=config.get("DARK_MODE", False))
        dark_mode_check = tk.Checkbutton(config_window, variable=dark_mode_var)
        dark_mode_check.grid(row=8, column=1, padx=10, pady=5, sticky='w')

        save_button = tk.Button(config_window, text="Speichern", command=save_changes)
        save_button.grid(row=9, column=0, columnspan=2, padx=10, pady=10)
    except Exception as e:
        logging.error(f"Fehler beim Öffnen der Konfiguration: {e}")
        messagebox.showerror("Fehler", "Fehler beim Öffnen der Konfiguration.")

def select_source_directory():
    """
    Funktion zum Auswählen des Quellverzeichnisses.
    """
    try:
        directory = filedialog.askdirectory()
        if directory:
            if os.path.exists(directory):
                source_directory.set(directory)
                logging.info(f"Quellverzeichnis ausgewählt: {directory}")
            else:
                messagebox.showerror("Fehler", "Das ausgewählte Verzeichnis existiert nicht.")
    except Exception as e:
        logging.error(f"Fehler beim Auswählen des Quellverzeichnisses: {e}")
        messagebox.showerror("Fehler", "Fehler beim Auswählen des Quellverzeichnisses. Bitte versuchen Sie es erneut.")

def backup_file(filepath):
    """
    Funktion zum Erstellen einer Sicherungskopie der Datei.

    Args:
        filepath (str): Der Pfad zur Datei, die gesichert werden soll.
    """
    try:
        backup_dir = os.path.join(os.path.dirname(filepath), config["BACKUP_DIR"])
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy(filepath, backup_dir)
        logging.info(f"Backup erstellt: {filepath} -> {backup_dir}")
    except FileNotFoundError as e:
        logging.error(f"Datei nicht gefunden: {e}")
    except PermissionError as e:
        logging.error(f"Zugriffsfehler: {e}")
    except OSError as e:
        logging.error(f"OS-Fehler: {e}")
    except Exception as e:
        logging.error(f"Unbekannter Fehler beim Erstellen des Backups: {e}")

# Cache für extrahierte Texte
text_cache = {}

class Plugin:
    def process_file(self, filepath):
        raise NotImplementedError

class PDFPlugin(Plugin):
    def process_file(self, filepath):
        return extract_text_from_pdf(filepath)

class ImagePlugin(Plugin):
    def process_file(self, filepath):
        return extract_text_from_image(filepath)

class DOCXPlugin(Plugin):
    def process_file(self, filepath):
        import docx
        doc = docx.Document(filepath)
        return "\n".join([para.text for para in doc.paragraphs])

class XLSXPlugin(Plugin):
    def process_file(self, filepath):
        import openpyxl
        wb = openpyxl.load_workbook(filepath)
        text = []
        for sheet in wb:
            for row in sheet.iter_rows(values_only=True):
                text.append(" ".join([str(cell) for cell in row if cell is not None]))
        return "\n".join(text)

class EMLPlugin(Plugin):
    def process_file(self, filepath):
        import email
        from email import policy
        from email.parser import BytesParser
        with open(filepath, 'rb') as f:
            msg = BytesParser(policy=policy.default).parse(f)
        return msg.get_body(preferencelist=('plain')).get_content()

# Register plugins
plugins = [PDFPlugin(), ImagePlugin(), DOCXPlugin(), XLSXPlugin(), EMLPlugin()]

def extract_text(filepath):
    """
    Funktion zum Extrahieren von Text basierend auf Dateityp.

    Args:
        filepath (str): Der Pfad zur Datei, aus der der Text extrahiert werden soll.

    Returns:
        str: Der extrahierte Text oder ein leerer String, wenn ein Fehler auftritt.
    """
    try:
        if filepath in text_cache:
            logging.info(f"Text aus Cache geladen: {filepath}")
            return text_cache[filepath]

        ext = filepath.split('.')[-1].lower()
        for plugin in plugins:
            if plugin.__class__.__name__.lower().startswith(ext):
                text = plugin.process_file(filepath)
                text_cache[filepath] = text
                return text

        logging.error(f"Nicht unterstütztes Dateiformat: {ext}")
        return ""
    except FileNotFoundError as e:
        logging.error(f"Datei nicht gefunden: {e}")
    except PermissionError as e:
        logging.error(f"Zugriffsfehler: {e}")
    except OSError as e:
        logging.error(f"OS-Fehler: {e}")
    except Exception as e:
        logging.error(f"Unbekannter Fehler beim Extrahieren von Text: {e}")
    return ""

def format_filename(info, ext):
    """
    Formatiert den Dateinamen basierend auf den extrahierten Informationen und der Dateierweiterung.

    Args:
        info (dict): Ein Dictionary mit den extrahierten Informationen.
        ext (str): Die Dateierweiterung.

    Returns:
        str: Der formatierte Dateiname.
    """
    return config["FILENAME_PATTERN"].format(
        date=info["date"],
        company=info["company_name"],
        number=info["number"],
        ext=ext
    )

def analyze_text(text):
    """
    Extrahiert relevante Informationen wie Firma, Datum und Rechnungsnummer.
    """
    if text in text_cache:
        logging.info("Textanalyse aus Cache geladen.")
        return text_cache[text]

    info = {
        "company_name": "Unbekannt",
        "date": "",
        "number": ""
    }

    try:
        # Firmennamen suchen
        company_keywords = ["GmbH", "GBr", "OHG", "AG", "KG", "UG", "e.K.", "e.V."]
        company_pattern = re.compile(rf"(.*?)\s+(?:{'|'.join(map(re.escape, company_keywords))})", re.IGNORECASE)
        match = company_pattern.search(text)
        if match:
            info["company_name"] = match.group(1).strip()

        # Datum extrahieren
        for date_match in re.findall(r"\b\d{2}\.\d{2}\.\d{4}\b|\b\d{4}-\d{2}-\d{2}\b", text):
            detected_date = detect_date(date_match)
            if detected_date:
                info["date"] = detected_date
                break

        # Rechnungsnummer extrahieren
        for pattern in [
            r"Rechnung\s*Nr\.?:?\s*(\w+-\w+-\w+-\w+-\w+)",
            r"Rechnungsnummer[:\s]*(\w+-\w+-\w+-\w+-\w+)",
            r"Rechnung\s*Nr\.?:?\s*(\d+)",
            r"Rechnungsnummer[:\s]*(\d+)"
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info["number"] = match.group(1)
                if info["number"].startswith("AEU"):
                    info["company_name"] = "Amazon"
                break

        text_cache[text] = info
    except Exception as e:
        logging.error(f"Fehler bei der Analyse des Textes: {e}")

    return info

def generate_report():
    """
    Funktion zum Generieren eines Berichts.
    """
    try:
        processing_end_time = datetime.now()
        processing_duration = processing_end_time - processing_start_time
        report = "Bericht über die Dateiverarbeitung\n"
        report += "==============================\n\n"
        report += f"Datum und Uhrzeit: {processing_end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"Gesamtverarbeitungszeit: {processing_duration}\n\n"
        report += f"Verarbeitete Dateien:\n"
        report += "---------------------\n"
        for file_info in processed_files:
            report += f"{file_info}\n"
        report += f"\nFehler:\n"
        report += "-------\n"
        for error in errors:
            report += f"{error}\n"
        return report
    except Exception as e:
        logging.error(f"Fehler beim Generieren des Berichts: {e}")
        return "Fehler beim Generieren des Berichts."

def show_report(root):
    """
    Funktion zum Anzeigen des Berichts in einem neuen Fenster.

    Args:
        root (tk.Tk): Das Hauptfenster der Anwendung.
    """
    try:
        report = generate_report()
        
        def copy_to_clipboard():
            root.clipboard_clear()
            root.clipboard_append(report)
            root.update()  # Keep the clipboard content
        
        report_window = tk.Toplevel(root)
        report_window.title("Bericht")
        
        report_text = tk.Text(report_window, wrap='word')
        report_text.insert('1.0', report)
        report_text.config(state='disabled')  # Nur Lesen
        report_text.pack(expand=True, fill='both')
        
        copy_button = tk.Button(report_window, text="In Zwischenablage kopieren", command=copy_to_clipboard)
        copy_button.pack(pady=10)
        
        logging.info("Bericht angezeigt")
    except Exception as e:
        logging.error(f"Fehler beim Anzeigen des Berichts: {e}")
        messagebox.showerror("Fehler", "Fehler beim Anzeigen des Berichts.")

def show_log(root):
    """
    Funktion zum Anzeigen des Protokollfensters.

    Args:
        root (tk.Tk): Das Hauptfenster der Anwendung.
    """
    try:
        log_window = tk.Toplevel(root)
        log_window.title("Protokoll")
        
        log_text = tk.Text(log_window, wrap='word')
        log_text.pack(expand=True, fill='both')
        
        with open('app.log', 'r', encoding='utf-8') as log_file:
            log_text.insert('1.0', log_file.read())
        
        log_text.config(state='disabled')  # Nur Lesen
    except FileNotFoundError:
        logging.error("Die Protokolldatei 'app.log' wurde nicht gefunden.")
        messagebox.showerror("Fehler", "Die Protokolldatei 'app.log' wurde nicht gefunden.")
    except Exception as e:
        logging.error(f"Fehler beim Anzeigen des Protokolls: {e}")
        messagebox.showerror("Fehler", "Fehler beim Anzeigen des Protokolls.")

def update_progress(index, total, root):
    """
    Aktualisiert die Fortschrittsanzeige.

    Args:
        index (int): Der aktuelle Index der verarbeiteten Datei.
        total (int): Die Gesamtanzahl der zu verarbeitenden Dateien.
        root (tk.Tk): Das Hauptfenster der Anwendung.
    """
    progress['value'] = (index / total) * 100
    root.update_idletasks()

async def rename_and_organize_files(root):
    """
    Asynchrones Umbenennen und Organisieren von Dateien.
    """
    global processing_start_time
    processing_start_time = datetime.now()

    directory = source_directory.get()
    if not directory:
        messagebox.showwarning("Warnung", "Quellverzeichnis nicht ausgewählt.")
        return

    try:
        files = [f for f in os.listdir(directory) if f.split('.')[-1].lower() in config["ALLOWED_EXTENSIONS"]]
        if not files:
            messagebox.showwarning("Warnung", "Keine verarbeitbaren Dateien gefunden.")
            return

        progress['maximum'] = len(files)
        tasks = [process_file(directory, filename, i + 1, root) for i, filename in enumerate(files)]
        await asyncio.gather(*tasks)  # Parallelisierung

        logging.info("Alle Dateien erfolgreich verarbeitet.")
        messagebox.showinfo("Erfolg", "Alle Dateien erfolgreich umbenannt und organisiert.")
    except Exception as e:
        logging.error(f"Fehler: {e}")
        messagebox.showerror("Fehler", f"Ein Fehler ist aufgetreten: {e}")

async def process_file(directory, filename, index, root):
    """
    Asynchrone Hilfsfunktion zum Verarbeiten einer einzelnen Datei.

    Args:
        directory (str): Das Quellverzeichnis.
        filename (str): Der Name der zu verarbeitenden Datei.
        index (int): Der Index der Datei in der Verarbeitungsreihenfolge.
        root (tk.Tk): Das Hauptfenster der Anwendung.
    """
    old_path = os.path.join(directory, filename)
    try:
        logging.debug(f"Verarbeite Datei: {old_path}")
        backup_file(old_path)
        text = extract_text(old_path)
        info = analyze_text(text)
        
        logging.debug(f"Extrahierte Informationen: {info}")
        
        # Sicherstellen, dass keine leeren oder unbekannten Werte verwendet werden
        date_parts = info["date"].split("-")
        year = date_parts[0] if len(date_parts) == 3 else "0000"
        company = info["company_name"] if info["company_name"] else "Unbekannt"
        number = info["number"]
        
        new_filename = format_filename(info, filename.split('.')[-1])
        main_target_dir = config.get("MAIN_TARGET_DIR", directory)
        
        # Create year folder and company subfolder within the year folder
        year_dir = os.path.join(main_target_dir, year)
        new_dir = os.path.join(year_dir, company)
        os.makedirs(new_dir, exist_ok=True)
        
        new_path = os.path.join(new_dir, new_filename)
        
        # Überprüfen, ob die Zieldatei bereits existiert, und ggf. umbenennen
        if not os.path.exists(new_path):
            shutil.copy(old_path, new_path)
            os.remove(old_path)
            logging.info(f"Datei umbenannt und verschoben: {old_path} -> {new_path}")
        else:
            # Wenn die Datei existiert, fügen wir eine Nummer hinzu, um Konflikte zu vermeiden
            base, ext = os.path.splitext(new_path)
            counter = 1
            while os.path.exists(new_path):
                new_path = f"{base}_{counter}{ext}"
                counter += 1
            shutil.copy(old_path, new_path)
            os.remove(old_path)
            logging.info(f"Datei umbenannt und verschoben: {old_path} -> {new_path} (mit Nummerierung)")
        
        # Überprüfen, ob die Zieldatei erfolgreich erstellt wurde
        if os.path.exists(new_path):
            processed_files.append(f"{old_path} -> {new_path}")
        else:
            raise FileNotFoundError(f"Zieldatei wurde nicht erstellt: {new_path}")
    except OSError as e:
        error_msg = f"Fehler bei der Verarbeitung von {old_path}: {e}"
        logging.error(error_msg)
        errors.append(error_msg)
        
        # Verschiebe fehlerhafte Datei in separaten Ordner
        error_dir = os.path.join(directory, "errors")
        os.makedirs(error_dir, exist_ok=True)
        error_path = os.path.join(error_dir, filename)
        shutil.move(old_path, error_path)
        logging.info(f"Fehlerhafte Datei verschoben: {old_path} -> {error_path}")
    except Exception as e:
        error_msg = f"Unbekannter Fehler bei der Verarbeitung von {old_path}: {e}"
        logging.error(error_msg)
        errors.append(error_msg)
    
    progress['value'] = index  # Update progress bar directly
    root.update_idletasks()  # Ensure the progress bar is visually updated

def show_help():
    """
    Hilfefunktion anzeigen.
    """
    try:
        help_text = (
            "Anleitung zur Verwendung des Dateiumbenennungstools:\n\n"
            "1. Wählen Sie das Quellverzeichnis aus, das die zu verarbeitenden Dateien enthält.\n"
            "2. Klicken Sie auf 'Dateien umbenennen und organisieren', um den Umbenennungsprozess zu starten.\n"
            "3. Die Dateien werden analysiert, um Informationen wie Rechnungsdatum, Firmenname und Rechnungsnummer zu extrahieren.\n"
            "4. Die Dateien werden im Format 'YYYY.MM.DD Firma Nummer.ext' umbenannt und in entsprechende Unterordner verschoben.\n"
            "5. Ein Fortschrittsbalken zeigt den Fortschritt des Prozesses an.\n"
            "6. Erfolgsmeldungen und detaillierte Protokolle werden angezeigt, um den Status der Verarbeitung zu verfolgen.\n"
            "7. Verwenden Sie die 'Firmenpflege'-Option, um die Liste der Firmennamen zu verwalten.\n"
            "8. Über die 'Konfiguration'-Option können Sie die Standardeinstellungen anpassen.\n"
            "9. Der 'Bericht anzeigen'-Button zeigt eine Zusammenfassung der verarbeiteten Dateien und Fehler an.\n"
            "10. Das Protokollfenster zeigt detaillierte Log-Einträge zur Fehlerbehebung.\n"
            "11. Über die 'Hilfe'-Option erhalten Sie diese Anleitung.\n"
            "12. Mit der 'Info'-Option erhalten Sie Informationen über das Tool.\n"
            "13. Verwenden Sie die Sprachauswahl, um die Sprache der Benutzeroberfläche zu ändern.\n"
            "14. Die Dateien werden in Jahres- und Firmenordner organisiert.\n"
            "15. Automatische Sicherungskopien der Dateien werden erstellt.\n"
            "16. Fehlerhafte Dateien werden in einen separaten Ordner verschoben.\n"
        )
        messagebox.showinfo("Hilfe", help_text)
    except Exception as e:
        logging.error(f"Fehler beim Anzeigen der Hilfe: {e}")
        messagebox.showerror("Fehler", "Fehler beim Anzeigen der Hilfe.")

def show_info():
    """
    Funktion zum Anzeigen der Tool-Informationen.
    """
    try:
        with open('toolinfo.json', 'r', encoding='utf-8') as info_file:
            info_data = json.load(info_file)
            info_text = (
                f"Name: {info_data['name']}\n"
                f"Version: {info_data['version']}\n"
                f"Autor: {info_data['author']}\n"
                f"Beschreibung: {info_data['description']}\n"
                f"Homepage: {info_data['homepage']}\n"
                f"Kategorien: {', '.join(info_data['categories'])}\n"
                f"Features: {', '.join(info_data['features'])}\n"
                f"Abhängigkeiten: {', '.join(info_data['dependencies'])}\n"
                f"Installation: {info_data['installation']['requirements']}\n"
                f"Verwendung: {info_data['installation']['usage']}\n"
            )
            messagebox.showinfo("Info", info_text)
    except FileNotFoundError:
        logging.error("Die Datei 'toolinfo.json' wurde nicht gefunden.")
        messagebox.showerror("Fehler", "Die Datei 'toolinfo.json' wurde nicht gefunden.")
    except json.JSONDecodeError:
        logging.error("Die Datei 'toolinfo.json' ist beschädigt oder enthält ungültiges JSON.")
        messagebox.showerror("Fehler", "Die Datei 'toolinfo.json' ist beschädigt oder enthält ungültiges JSON.")
    except Exception as e:
        logging.error(f"Fehler beim Laden der Info-Datei: {e}")
        messagebox.showerror("Fehler", f"Fehler beim Laden der Info-Datei: {e}")

def rename_files(root):
    """
    Funktion zum Starten des Umbenennungsprozesses.

    Args:
        root (tk.Tk): Das Hauptfenster der Anwendung.
    """
    try:
        logging.info("Starte den Umbenennungsprozess...")
        asyncio.run(rename_and_organize_files(root))
        logging.info("Umbenennungsprozess gestartet.")
    except asyncio.CancelledError:
        logging.error("Umbenennungsprozess abgebrochen.")
    except Exception as e:
        logging.error(f"Fehler beim Umbenennungsprozess: {e}")
        messagebox.showerror("Fehler", f"Fehler beim Umbenennungsprozess: {e}")

def change_language(event):
    """
    Funktion zum Ändern der Sprache zur Laufzeit.

    Args:
        event (tk.Event): Das Ereignis, das die Sprachänderung auslöst.
    """
    try:
        global current_language
        selected_language = language_var.get()
        current_language = selected_language
        logging.info(f"Sprache geändert zu: {current_language}")
        # Aktualisiere die GUI-Texte
        update_gui_texts()
    except Exception as e:
        logging.error(f"Fehler beim Ändern der Sprache: {e}")
        messagebox.showerror("Fehler", "Fehler beim Ändern der Sprache.")

# Mehrsprachige Texte
LANGUAGES = {
    'de': {
        'source_label': 'Quellverzeichnis:',
        'button_source': 'Quellverzeichnis auswählen',
        'button_rename': 'Dateien umbenennen und organisieren',
        'button_firmenpflege': 'Firmenpflege',
        'button_help': 'Hilfe',
        'button_report': 'Bericht anzeigen',
        'button_exit': 'Beenden',
        'button_config': 'Konfiguration',
        'button_log': 'Protokoll anzeigen',
        'button_info': 'Info',
        'tooltip_source': 'Wählen Sie das Verzeichnis aus, das die zu verarbeitenden Dateien enthält.',
        'tooltip_rename': 'Klicken Sie hier, um den Umbenennungsprozess zu starten.',
        'tooltip_preview': 'Klicken Sie hier, um eine Vorschau der neuen Dateinamen anzuzeigen.',
        'tooltip_firmenpflege': 'Klicken Sie hier, um die Liste der Firmennamen zu bearbeiten.',
        'tooltip_config': 'Klicken Sie hier, um die Standardeinstellungen anzupassen.',
        'tooltip_report': 'Klicken Sie hier, um eine Zusammenfassung der verarbeiteten Dateien und Fehler anzuzeigen.',
        'tooltip_log': 'Klicken Sie hier, um detaillierte Log-Einträge zur Fehlerbehebung anzuzeigen.',
        'tooltip_help': 'Klicken Sie hier, um die Anleitung zur Verwendung des Tools anzuzeigen.',
        'tooltip_exit': 'Klicken Sie hier, um das Programm zu beenden.',
        'tooltip_info': 'Klicken Sie hier, um Informationen über das Tool anzuzeigen.',
        'tooltip_language': 'Wählen Sie die Sprache der Benutzeroberfläche aus.',
        # Weitere Übersetzungen...
    },
    'en': {
        'source_label': 'Source Directory:',
        'button_source': 'Select Source Directory',
        'button_rename': 'Rename and Organize Files',
        'button_firmenpflege': 'Manage Companies',
        'button_help': 'Help',
        'button_report': 'Show Report',
        'button_exit': 'Exit',
        'button_config': 'Configuration',
        'button_log': 'Show Log',
        'button_info': 'Info',
        # Weitere Übersetzungen...
    }
}

def update_gui_texts():
    """
    Funktion zum Aktualisieren der GUI-Texte nach einer Sprachänderung.
    """
    try:
        language = language_var.get()
        texts = LANGUAGES.get(language, LANGUAGES['de'])
        source_label.config(text=texts['source_label'])
        button_source.config(text=texts['button_source'])
        button_rename.config(text=texts['button_rename'])
        button_firmenpflege.config(text=texts['button_firmenpflege'])
        button_help.config(text=texts['button_help'])
        button_report.config(text=texts['button_report'])
        button_exit.config(text=texts['button_exit'])
        button_config.config(text=texts['button_config'])
        button_log.config(text=texts['button_log'])
        button_info.config(text=texts['button_info'])
        update_tooltips()
        # Weitere GUI-Elemente aktualisieren...
    except Exception as e:
        logging.error(f"Fehler beim Aktualisieren der GUI-Texte: {e}")
        messagebox.showerror("Fehler", "Fehler beim Aktualisieren der GUI-Texte.")

def on_drop(event):
    """
    Funktion zum Verarbeiten von Drag & Drop-Ereignissen.
    """
    try:
        files = root.tk.splitlist(event.data)
        for file in files:
            if os.path.isdir(file):
                source_directory.set(file)
                logging.info(f"Quellverzeichnis durch Drag & Drop ausgewählt: {file}")
            else:
                messagebox.showwarning("Warnung", "Bitte ziehen Sie einen Ordner, keine Datei.")
    except Exception as e:
        logging.error(f"Fehler beim Verarbeiten von Drag & Drop: {e}")
        messagebox.showerror("Fehler", "Fehler beim Verarbeiten von Drag & Drop. Bitte versuchen Sie es erneut.")

def preview_renaming(root):
    """
    Funktion zum Anzeigen einer Vorschau der neuen Dateinamen.
    """
    try:
        directory = source_directory.get()
        if not directory:
            logging.warning("Quellverzeichnis nicht ausgewählt.")
            messagebox.showwarning("Warnung", "Quellverzeichnis nicht ausgewählt. Bitte wählen Sie ein Verzeichnis aus.")
            return
        
        files = [f for f in os.listdir(directory) if f.split('.')[-1].lower() in config["ALLOWED_EXTENSIONS"]]
        if not files:
            logging.warning("Keine Dateien zum Verarbeiten gefunden.")
            messagebox.showwarning("Warnung", "Das ausgewählte Verzeichnis enthält keine unterstützten Dateien.")
            return
        
        preview_window = tk.Toplevel(root)
        preview_window.title("Vorschau der Dateibenennung")
        
        preview_listbox = tk.Listbox(preview_window, width=80, height=20)
        preview_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        for filename in files:
            old_path = os.path.join(directory, filename)
            text = extract_text(old_path)
            info = analyze_text(text)
            
            date_parts = info["date"].split("-")
            year = date_parts[0] if len(date_parts) == 3 else "0000"
            company = info["company_name"] if info["company_name"] else "Unbekannt"
            number = info["number"]
            
            new_filename = f"{info['date']} {company} {number}.{filename.split('.')[-1]}"
            preview_listbox.insert(tk.END, f"{filename} -> {new_filename}")
        
        close_button = tk.Button(preview_window, text="Schließen", command=preview_window.destroy)
        close_button.pack(pady=10)
        
        logging.info("Vorschau der Dateibenennung angezeigt")
    except Exception as e:
        logging.error(f"Fehler beim Anzeigen der Vorschau: {e}")
        messagebox.showerror("Fehler", "Fehler beim Anzeigen der Vorschau.")
def apply_dark_mode(root):
    """
    Funktion zum Anwenden des Dark Mode auf die GUI.
    """
    try:
        style = ttk.Style()
        if config.get("DARK_MODE", False):
            root.tk.call("source", "azure.tcl")
            root.tk.call("set_theme", "dark")
        else:
            root.tk.call("set_theme", "light")
    except Exception as e:
        logging.error(f"Fehler beim Anwenden des Dark Mode: {e}")

def add_tooltip(widget, text):
    """
    Fügt einem Widget einen Tooltip hinzu.

    Args:
        widget (tk.Widget): Das Widget, dem der Tooltip hinzugefügt werden soll.
        text (str): Der Text des Tooltips.
    """
    tooltip = tk.Toplevel(widget)
    tooltip.withdraw()
    tooltip.overrideredirect(True)
    tooltip_label = tk.Label(tooltip, text=text, background="yellow", relief="solid", borderwidth=1)
    tooltip_label.pack()

    def show_tooltip(event):
        tooltip.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
        tooltip.deiconify()

    def hide_tooltip(event):
        tooltip.withdraw()

    widget.bind("<Enter>", show_tooltip)
    widget.bind("<Leave>", hide_tooltip)

def update_tooltips():
    """
    Aktualisiert die Tooltips basierend auf der aktuellen Sprache.
    """
    try:
        language = language_var.get()
        texts = LANGUAGES.get(language, LANGUAGES['de'])
        add_tooltip(button_source, texts['tooltip_source'])
        add_tooltip(button_rename, texts['tooltip_rename'])
        add_tooltip(button_preview, texts['tooltip_preview'])
        add_tooltip(button_firmenpflege, texts['tooltip_firmenpflege'])
        add_tooltip(button_config, texts['tooltip_config'])
        add_tooltip(button_report, texts['tooltip_report'])
        add_tooltip(button_log, texts['tooltip_log'])
        add_tooltip(button_help, texts['tooltip_help'])
        add_tooltip(button_exit, texts['tooltip_exit'])
        add_tooltip(button_info, texts['tooltip_info'])
        add_tooltip(language_menu, texts['tooltip_language'])
    except Exception as e:
        logging.error(f"Fehler beim Aktualisieren der Tooltips: {e}")
        messagebox.showerror("Fehler", "Fehler beim Aktualisieren der Tooltips.")

def main():
    """
    Hauptfunktion zum Erstellen des Formulars.
    """
    global source_directory, progress, file_listbox, language_var, source_label, button_source, button_rename, button_firmenpflege, button_help, button_report, button_exit, button_config, button_log, button_info, button_preview, root, language_menu
    try:
        load_config()
        
        root = TkinterDnD.Tk()  # Use TkinterDnD for drag & drop support
        root.title("Dateiumbenennungstool")
        
        source_directory = tk.StringVar(value=config["DEFAULT_SOURCE_DIR"])
        
        # Verzeichnisse
        verzeichnisse_frame = tk.LabelFrame(root, text="Verzeichnisse", padx=10, pady=10)
        verzeichnisse_frame.grid(row=0, column=0, padx=10, pady=10, sticky='ew')

        source_label = tk.Label(verzeichnisse_frame, text="Quellverzeichnis:")
        source_label.grid(row=0, column=0, padx=10, pady=10, sticky='w')
        entry_source = tk.Entry(verzeichnisse_frame, textvariable=source_directory, width=50)
        entry_source.grid(row=0, column=1, padx=10, pady=10, sticky='w')
        
        button_source = tk.Button(verzeichnisse_frame, text="Quellverzeichnis auswählen", command=select_source_directory)
        button_source.grid(row=0, column=2, padx=10, pady=10)
        
        button_rename = tk.Button(verzeichnisse_frame, text="Dateien umbenennen und organisieren", command=lambda: rename_files(root))
        button_rename.grid(row=1, column=0, columnspan=3, padx=10, pady=10)
        
        button_preview = tk.Button(verzeichnisse_frame, text="Vorschau der Dateibenennung", command=lambda: preview_renaming(root))
        button_preview.grid(row=2, column=0, columnspan=3, padx=10, pady=10)
        
        # Konfiguration
        konfiguration_frame = tk.LabelFrame(root, text="Konfiguration", padx=10, pady=10)
        konfiguration_frame.grid(row=1, column=0, padx=10, pady=10, sticky='ew')

        button_firmenpflege = tk.Button(konfiguration_frame, text="Firmenpflege", command=lambda: open_firmenpflege(root))
        button_firmenpflege.grid(row=0, column=0, padx=10, pady=10)
        
        button_config = tk.Button(konfiguration_frame, text="Konfiguration", command=lambda: open_config(root))
        button_config.grid(row=0, column=1, padx=10, pady=10)
        
        # Berichte
        berichte_frame = tk.LabelFrame(root, text="Berichte", padx=10, pady=10)
        berichte_frame.grid(row=2, column=0, padx=10, pady=10, sticky='ew')

        button_report = tk.Button(berichte_frame, text="Bericht anzeigen", command=lambda: show_report(root))
        button_report.grid(row=0, column=0, padx=10, pady=10)
        
        button_log = tk.Button(berichte_frame, text="Protokoll anzeigen", command=lambda: show_log(root))
        button_log.grid(row=0, column=1, padx=10, pady=10)
        
        # Sonstige
        sonstige_frame = tk.LabelFrame(root, text="Sonstige", padx=10, pady=10)
        sonstige_frame.grid(row=3, column=0, padx=10, pady=10, sticky='ew')

        button_help = tk.Button(sonstige_frame, text="Hilfe", command=show_help)
        button_help.grid(row=0, column=0, padx=10, pady=10)
        
        button_exit = tk.Button(sonstige_frame, text="Beenden", command=root.quit)
        button_exit.grid(row=0, column=1, padx=10, pady=10)
        
        # Add Info button
        button_info = tk.Button(sonstige_frame, text="Info", command=show_info)
        button_info.grid(row=0, column=2, padx=10, pady=10)
        
        # Fortschrittsbalken hinzufügen
        progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
        progress.grid(row=4, column=0, padx=10, pady=10, sticky='ew')
        
        # Listbox für Dateien hinzufügen
        file_listbox = tk.Listbox(root, width=80, height=10)
        file_listbox.grid(row=5, column=0, padx=10, pady=10, sticky='ew')
        
        # Dropdown-Liste für Sprachauswahl hinzufügen
        language_var = tk.StringVar(value=current_language)
        languages = ['de', 'en']  # Beispielsprachen
        language_menu = ttk.Combobox(root, textvariable=language_var, values=languages)
        language_menu.grid(row=6, column=0, padx=10, pady=10, sticky='ew')
        language_menu.bind("<<ComboboxSelected>>", change_language)
        
        # Register Drag & Drop
        root.drop_target_register(DND_FILES)
        root.dnd_bind('<<Drop>>', on_drop)
        
        update_tooltips()
        root.mainloop()
        save_config()
    except Exception as e:
        logging.error(f"Fehler in der Hauptfunktion: {e}")
        messagebox.showerror("Fehler", "Ein schwerwiegender Fehler ist aufgetreten. Das Programm wird beendet.")

if __name__ == "__main__":
    load_config()
    main()
