import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
import os
import logging
import shutil
import asyncio
import json
from datetime import datetime
from babel.support import Translations
from text_extraction import extract_text_from_pdf, extract_text_from_image
import re

# Funktion zum Laden der Übersetzungen
def load_translations(language):
    translations = Translations.load('translations', [language])
    return translations.gettext

# Initiale Sprachkonfiguration
current_language = 'de'
_ = load_translations(current_language)

FIRMEN_DATEI = "firmen.txt"
CONFIG_DATEI = "config.json"

# Definiere das Logging-Format
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Konfiguriere das Logging
logging.basicConfig(
    level=logging.DEBUG,
    format=log_format,
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler('app.log', 'w', 'utf-8'), logging.StreamHandler()]
)

# Berichtsvariablen
processed_files = []
errors = []
processing_start_time = None

# Standardkonfiguration
default_config = {
    "DEFAULT_SOURCE_DIR": "",
    "BACKUP_DIR": "backup",
    "ALLOWED_EXTENSIONS": ["pdf", "png", "jpg", "jpeg"],
    "BATCH_SIZE": 10,
    "DATE_FORMATS": ["%Y.%m.%d", "%Y-%m-%d", "%d.%m.%Y"]
}

config = default_config.copy()

def load_config():
    """
    Funktion zum Laden der Konfiguration.
    """
    global config
    if os.path.exists(CONFIG_DATEI):
        try:
            with open(CONFIG_DATEI, 'r') as config_file:
                loaded_config = json.load(config_file)
                config.update({key: loaded_config.get(key, default) for key, default in default_config.items()})
            logging.info("Konfiguration geladen")
        except Exception as e:
            logging.error(f"Fehler beim Laden der Konfiguration: {e}")

def save_config():
    """
    Funktion zum Speichern der Konfiguration.
    """
    try:
        with open(CONFIG_DATEI, 'w') as config_file:
            json.dump(config, config_file, indent=4)
        logging.info("Konfiguration gespeichert")
    except Exception as e:
        logging.error(f"Fehler beim Speichern der Konfiguration: {e}")

def load_firmennamen():
    """
    Funktion zum Laden der Firmennamen aus der Datei.
    """
    if os.path.exists(FIRMEN_DATEI):
        try:
            with open(FIRMEN_DATEI, 'r', encoding='utf-8') as file:
                return [line.strip() for line in file.readlines()]
        except Exception as e:
            logging.error(f"Fehler beim Laden der Firmennamen: {e}")
    return []

def save_firmennamen(firmennamen):
    """
    Funktion zum Speichern der Firmennamen in die Datei.
    """
    try:
        with open(FIRMEN_DATEI, 'w', encoding='utf-8') as file:
            file.write('\n'.join(firmennamen))
    except Exception as e:
        logging.error(f"Fehler beim Speichern der Firmennamen: {e}")

def open_firmenpflege():
    """
    Funktion zum Anzeigen des Firmenpflege-Fensters.
    """
    def add_firma():
        new_firma = simpledialog.askstring(_("Neue Firma"), _("Bitte geben Sie den Namen der neuen Firma ein:"))
        if new_firma:
            if not new_firma.strip():
                messagebox.showerror(_("Fehler"), _("Der Firmenname darf nicht leer sein."))
                return
            if any(char in new_firma for char in r'\/:*?"<>|'):
                messagebox.showerror(_("Fehler"), _("Der Firmenname darf keine ungültigen Zeichen enthalten."))
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
    pflege_window.title(_("Firmenpflege"))

    listbox = tk.Listbox(pflege_window)
    listbox.pack(fill=tk.BOTH, expand=True)

    for firma in firmennamen:
        listbox.insert(tk.END, firma)

    add_button = tk.Button(pflege_window, text=_("Firma hinzufügen"), command=add_firma)
    add_button.pack(side=tk.LEFT, padx=10, pady=10)

    remove_button = tk.Button(pflege_window, text=_("Firma entfernen"), command=remove_firma)
    remove_button.pack(side=tk.RIGHT, padx=10, pady=10)

def open_config():
    """
    Funktion zum Anzeigen des Konfigurations-Fensters.
    """
    def save_changes():
        config["DEFAULT_SOURCE_DIR"] = default_source_dir.get()
        config["BACKUP_DIR"] = backup_dir.get()
        config["ALLOWED_EXTENSIONS"] = allowed_extensions.get().split(',')
        config["BATCH_SIZE"] = int(batch_size.get())
        config["DATE_FORMATS"] = date_formats.get().split(',')
        save_config()
        config_window.destroy()

    config_window = tk.Toplevel(root)
    config_window.title(_("Konfiguration"))

    tk.Label(config_window, text=_("Standard-Quellverzeichnis:")).grid(row=0, column=0, padx=10, pady=5, sticky='w')
    default_source_dir = tk.Entry(config_window, width=50)
    default_source_dir.grid(row=0, column=1, padx=10, pady=5, sticky='w')
    default_source_dir.insert(0, config["DEFAULT_SOURCE_DIR"])

    tk.Label(config_window, text=_("Backup-Verzeichnis:")).grid(row=1, column=0, padx=10, pady=5, sticky='w')
    backup_dir = tk.Entry(config_window, width=50)
    backup_dir.grid(row=1, column=1, padx=10, pady=5, sticky='w')
    backup_dir.insert(0, config["BACKUP_DIR"])

    tk.Label(config_window, text=_("Erlaubte Dateierweiterungen (kommagetrennt):")).grid(row=2, column=0, padx=10, pady=5, sticky='w')
    allowed_extensions = tk.Entry(config_window, width=50)
    allowed_extensions.grid(row=2, column=1, padx=10, pady=5, sticky='w')
    allowed_extensions.insert(0, ','.join(config["ALLOWED_EXTENSIONS"]))

    tk.Label(config_window, text=_("Batch-Größe:")).grid(row=3, column=0, padx=10, pady=5, sticky='w')
    batch_size = tk.Entry(config_window, width=50)
    batch_size.grid(row=3, column=1, padx=10, pady=5, sticky='w')
    batch_size.insert(0, config["BATCH_SIZE"])

    tk.Label(config_window, text=_("Datumsformate (kommagetrennt):")).grid(row=4, column=0, padx=10, pady=5, sticky='w')
    date_formats = tk.Entry(config_window, width=50)
    date_formats.grid(row=4, column=1, padx=10, pady=5, sticky='w')
    date_formats.insert(0, ','.join(config["DATE_FORMATS"]))

    save_button = tk.Button(config_window, text=_("Speichern"), command=save_changes)
    save_button.grid(row=5, column=0, columnspan=2, padx=10, pady=10)

def select_source_directory():
    """
    Funktion zum Auswählen des Quellverzeichnisses.
    """
    directory = filedialog.askdirectory()
    if directory:
        source_directory.set(directory)
        logging.info(f"Quellverzeichnis ausgewählt: {directory}")

def backup_file(filepath):
    """
    Funktion zum Erstellen einer Sicherungskopie der Datei.
    """
    try:
        backup_dir = os.path.join(os.path.dirname(filepath), config["BACKUP_DIR"])
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy(filepath, backup_dir)
        logging.info(f"Backup erstellt: {filepath} -> {backup_dir}")
    except Exception as e:
        logging.error(f"Fehler beim Erstellen des Backups: {e}")

def extract_text(filepath):
    """
    Funktion zum Extrahieren von Text basierend auf Dateityp.
    """
    ext = filepath.split('.')[-1].lower()
    try:
        if ext == 'pdf':
            return extract_text_from_pdf(filepath)
        elif ext in ['png', 'jpg', 'jpeg']:
            return extract_text_from_image(filepath)
        else:
            logging.error(f"Nicht unterstütztes Dateiformat: {ext}")
            return ""
    except Exception as e:
        logging.error(f"Fehler beim Extrahieren von Text: {e}")
        return ""

def analyze_text(text):
    """
    Funktion zur Analyse von Text und Extraktion von Informationen wie Firmenname, Datum und Rechnungsnummer.
    """
    info = {
        "company_name": "",
        "date": "",
        "number": ""
    }
    
    # Suchen nach Firmennamen
    company_keywords = ["GmbH", "GBr", "OHG", "AG", "KG", "UG", "e.K.", "e.V."]
    company_pattern = re.compile(r"(.*?)(?=\s+(?:{}))".format("|".join(company_keywords)), re.IGNORECASE)
    company_match = company_pattern.search(text)
    if company_match:
        info["company_name"] = company_match.group(1).strip()

    # Suchen nach Datum in verschiedenen Formaten
    for date_format in config["DATE_FORMATS"]:
        try:
            date_pattern = datetime.strptime(date_format.replace("%d", "\d{2}").replace("%m", "\d{2}").replace("%Y", "\d{4}"), date_format)
            date_match = date_pattern.search(text)
            if date_match:
                info["date"] = datetime.strptime(date_match.group(0), date_format).strftime("%Y.%m.%d")
                break
        except ValueError:
            continue

    # Suchen nach Rechnungsnummer in verschiedenen Formaten
    number_patterns = [
        re.compile(r"Rechnung\s*Nr\.?:?\s*(\w+-\w+-\w+-\w+-\w+)", re.IGNORECASE),
        re.compile(r"Rechnungsnummer[:\s]*(\w+-\w+-\w+-\w+-\w+)", re.IGNORECASE),
        re.compile(r"Rechnung\s*Nr\.?:?\s*(\d+)", re.IGNORECASE),
        re.compile(r"Rechnungsnummer[:\s]*(\d+)", re.IGNORECASE),
    ]
    
    for pattern in number_patterns:
        number_match = pattern.search(text)
        if number_match:
            info["number"] = number_match.group(1)
            break

    return info

def generate_report():
    """
    Funktion zum Generieren eines Berichts.
    """
    processing_end_time = datetime.now()
    processing_duration = processing_end_time - processing_start_time
    report = _("Bericht über die Dateiverarbeitung\n")
    report += "==============================\n\n"
    report += f"{_('Datum und Uhrzeit')}: {processing_end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    report += f"{_('Gesamtverarbeitungszeit')}: {processing_duration}\n\n"
    report += f"{_('Verarbeitete Dateien')}:\n"
    report += "---------------------\n"
    for file_info in processed_files:
        report += f"{file_info}\n"
    report += f"\n{_('Fehler')}:\n"
    report += "-------\n"
    for error in errors:
        report += f"{error}\n"
    return report

def show_report():
    """
    Funktion zum Anzeigen des Berichts in einem neuen Fenster.
    """
    report = generate_report()
    report_window = tk.Toplevel(root)
    report_window.title(_("Bericht"))
    report_text = tk.Text(report_window, wrap='word')
    report_text.insert('1.0', report)
    report_text.config(state='disabled')  # Nur Lesen
    report_text.pack(expand=True, fill='both')
    logging.info("Bericht angezeigt")

async def rename_and_organize_files():
    """
    Asynchrone Funktion zum Umbennen und Organisieren von Dateien.
    """
    global processing_start_time
    processing_start_time = datetime.now()
    
    directory = source_directory.get()
    if not directory:
        messagebox.showerror(_("Fehler"), _("Bitte wählen Sie ein Quellverzeichnis aus."))
        logging.warning("Quellverzeichnis nicht ausgewählt.")
        return
    
    try:
        files = [f for f in os.listdir(directory) if f.split('.')[-1].lower() in config["ALLOWED_EXTENSIONS"]]
        progress['maximum'] = len(files)
        
        for i in range(0, len(files), config["BATCH_SIZE"]):
            batch = files[i:i + config["BATCH_SIZE"]]
            tasks = [process_file(directory, filename, i + idx + 1) for idx, filename in enumerate(batch)]
            await asyncio.gather(*tasks)
        
        messagebox.showinfo(_("Erfolg"), _("Dateien wurden erfolgreich umbenannt und organisiert."))
        logging.info("Dateien erfolgreich umbenannt und organisiert.")
    except FileNotFoundError as e:
        messagebox.showerror(_("Fehler"), _("Datei nicht gefunden: {e}"))
        logging.error(f"Datei nicht gefunden: {e}")
        errors.append(f"Datei nicht gefunden: {e}")
    except Exception as e:
        messagebox.showerror(_("Fehler"), _("Ein unbekannter Fehler ist aufgetreten: {e}"))
        logging.error(f"Unbekannter Fehler beim Umbennen und Organisieren der Dateien: {e}")
        errors.append(f"Unbekannter Fehler: {e}")

async def process_file(directory, filename, index):
    """
    Asynchrone Hilfsfunktion zum Verarbeiten einer einzelnen Datei.
    """
    old_path = os.path.join(directory, filename)
    try:
        backup_file(old_path)
        text = extract_text(old_path)
        info = analyze_text(text)
        
        # Sicherstellen, dass keine leeren oder unbekannten Werte verwendet werden
        date_parts = info["date"].split(".")
        year = date_parts[0] if len(date_parts) == 3 else "0000"
        company = info["company_name"] if info["company_name"] else _("Unbekannt")
        number = info["number"]
        
        new_filename = f"{info['date']} {company} {number}.{filename.split('.')[-1]}"
        new_dir = os.path.join(directory, year, company)
        os.makedirs(new_dir, exist_ok=True)
        
        new_path = os.path.join(new_dir, new_filename)
        
        # Überprüfen, ob die Zieldatei bereits existiert, und ggf. umbenennen
        if not os.path.exists(new_path):
            shutil.move(old_path, new_path)
            logging.info(f"Datei umbenannt und verschoben: {old_path} -> {new_path}")
        else:
            # Wenn die Datei existiert, fügen wir eine Nummer hinzu, um Konflikte zu vermeiden
            base, ext = os.path.splitext(new_path)
            counter = 1
            while os.path.exists(new_path):
                new_path = f"{base}_{counter}{ext}"
                counter += 1
            shutil.move(old_path, new_path)
            logging.info(f"Datei umbenannt und verschoben: {old_path} -> {new_path} (mit Nummerierung)")
        
        processed_files.append(f"{old_path} -> {new_path}")
    except Exception as e:
        error_msg = f"Fehler bei der Verarbeitung von {old_path}: {e}"
        logging.error(error_msg)
        errors.append(error_msg)
    
    progress['value'] = index
    root.update_idletasks()

def on_drop(event):
    """
    Funktion zum Verarbeiten von Drag-and-Drop-Ereignissen.
    """
    files = root.tk.splitlist(event.data)
    if len(files) == 1 and os.path.isdir(files[0]):
        source_directory.set(files[0])
        logging.info(f"Quellverzeichnis durch Drag-and-Drop ausgewählt: {files[0]}")
    else:
        messagebox.showerror(_("Fehler"), _("Bitte ziehen Sie nur ein Verzeichnis."))

def show_help():
    """
    Hilfefunktion anzeigen.
    """
    help_text = (
        _("Anleitung zur Verwendung des Dateiumbenennungstools:") + "\n\n"
        "1. " + _("Wählen Sie das Quellverzeichnis aus, das die zu verarbeitenden Dateien enthält.") + "\n"
        "2. " + _("Klicken Sie auf 'Dateien umbenennen und organisieren', um den Umbenennungsprozess zu starten.") + "\n"
        "3. " + _("Die Dateien werden analysiert, um Informationen wie Rechnungsdatum, Firmenname und Rechnungsnummer zu extrahieren.") + "\n"
        "4. " + _("Die Dateien werden im Format 'YYYY.MM.DD Firma Nummer.ext' umbenannt und in entsprechende Unterordner verschoben.") + "\n"
        "5. " + _("Ein Fortschrittsbalken zeigt den Fortschritt des Prozesses an.") + "\n"
        "6. " + _("Erfolgsmeldungen und detaillierte Protokolle werden angezeigt, um den Status der Verarbeitung zu verfolgen.")
    )
    messagebox.showinfo(_("Hilfe"), help_text)

def main():
    """
    Hauptfunktion zum Erstellen des Formulars.
    """
    global source_directory, progress, root
    global source_label, button_source, button_rename, button_firmenpflege
    global button_help, button_report, button_exit

    load_config()
    
    root = TkinterDnD.Tk()
    root.title(_("Dateiumbenennungstool"))
    
    source_directory = tk.StringVar(value=config["DEFAULT_SOURCE_DIR"])
    
    source_label = tk.Label(root, text=_("Quellverzeichnis:"))
    source_label.grid(row=0, column=0, padx=10, pady=10, sticky='w')
    entry_source = tk.Entry(root, textvariable=source_directory, width=50)
    entry_source.grid(row=0, column=1, padx=10, pady=10, sticky='w')
    
    button_source = tk.Button(root, text=_("Quellverzeichnis auswählen"), command=select_source_directory)
    button_source.grid(row=0, column=2, padx=10, pady=10)
    
    button_rename = tk.Button(root, text=_("Dateien umbenennen und organisieren"), command=lambda: asyncio.run(rename_and_organize_files()))
    button_rename.grid(row=1, column=0, columnspan=3, padx=10, pady=10)
    
    # Button für Firmenpflege hinzufügen
    button_firmenpflege = tk.Button(root, text=_("Firmenpflege"), command=open_firmenpflege)
    button_firmenpflege.grid(row=2, column=0, columnspan=3, padx=10, pady=10)
    
    # Fortschrittsbalken hinzufügen
    progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
    progress.grid(row=3, column=0, columnspan=3, padx=10, pady=10)
    
    # Hilfefunktion hinzufügen
    button_help = tk.Button(root, text=_("Hilfe"), command=show_help)
    button_help.grid(row=4, column=0, columnspan=3, padx=10, pady=10)

    # Button zum Generieren des Berichts hinzufügen
    button_report = tk.Button(root, text=_("Bericht anzeigen"), command=show_report)
    button_report.grid(row=5, column=0, columnspan=3, padx=10, pady=10)
    
    button_exit = tk.Button(root, text=_("Beenden"), command=root.quit)
    button_exit.grid(row=6, column=0, columnspan=3, padx=10, pady=10)

    # Button für Konfiguration hinzufügen
    button_config = tk.Button(root, text=_("Konfiguration"), command=open_config)
    button_config.grid(row=7, column=0, columnspan=3, padx=10, pady=10)

    # Drag-and-Drop-Unterstützung
    root.drop_target_register(DND_FILES)
    root.dnd_bind('<<Drop>>', on_drop)
    
    root.mainloop()
    save_config()

if __name__ == "__main__":
    main()
