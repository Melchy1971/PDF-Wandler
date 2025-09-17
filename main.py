import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import os
import logging
import shutil
import threading
import json
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from hashlib import sha256

# 3rd-party deps
import dateutil.parser  # pip install python-dateutil
from docx import Document  # pip install python-docx
from openpyxl import load_workbook  # pip install openpyxl

# local deps
from text_extraction import extract_text_from_pdf, extract_text_from_image

# -----------------------------
# Configuration & Logging
# -----------------------------
CONFIG_FILE = "config.json"
COMPANIES_FILE = "firmen.txt"
LOG_FILE = "app.log"

DEFAULT_CONFIG = {
    "DEFAULT_SOURCE_DIR": "",
    "BACKUP_DIR": "backup",
    "ALLOWED_EXTENSIONS": ["pdf", "png", "jpg", "jpeg", "docx", "xlsx", "eml"],
    "BATCH_SIZE": 10,
    "DATE_FORMATS": ["%Y.%m.%d", "%Y-%m-%d", "%d.%m.%Y"],
    "MAIN_TARGET_DIR": "",
    "LOG_LEVEL": "INFO",
    "FILENAME_PATTERN": "{date}_{company}_RE-{number}.{ext}",
    "DARK_MODE": False,
    "STRIP_LEGAL_SUFFIXES": True,
    "LEGAL_SUFFIXES": [
        "GmbH & Co. KG", "GmbH & Co KG", "GmbH & Co.KG",
        "UG (haftungsbeschränkt)", "UG", "GmbH", "AG", "KG", "OHG", "GbR", "e.K.", "e.V."
    ],
    "SUPPLIER_RULES": {
        "amazon": {
            "name": "Amazon",
            "match": r"\b(Amazon|AEU)\b",
            "invoice_pattern": r"AEU[\w-]+|\b\d{3}-\d{7}-\d{7}\b"
        },
        "telekom": {
            "name": "Telekom",
            "match": r"\b(Deutsche\s+Telekom|Telekom Deutschland|T-Mobile)\b",
            "invoice_pattern": r"\b[0-9]{12}\b"
        },
        "ikea": {
            "name": "IKEA",
            "match": r"\bIKEA\b",
            "invoice_pattern": r"\b[0-9]{9}\b"
        }
    }
}

# -----------------------------
# Config Manager
# -----------------------------
class ConfigManager:
    def __init__(self, path: str = CONFIG_FILE):
        self.path = path
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self.data.update({k: raw.get(k, v) for k, v in DEFAULT_CONFIG.items()})
            except Exception as e:
                logging.error("Konfiguration fehlerhaft – Standardwerte: %s", e)
        self.apply_logging()

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception as e:
            logging.error("Config konnte nicht gespeichert werden: %s", e)
            if os.path.exists(tmp):
                os.remove(tmp)

    def apply_logging(self):
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        # Korrigiert:
        level_name = self.data.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
                logging.StreamHandler()
            ],
        )

config = ConfigManager()

# -----------------------------
# Date parsing
# -----------------------------
GERMAN_MONTHS = {
    "Januar": "January", "Februar": "February", "März": "March", "April": "April",
    "Mai": "May", "Juni": "June", "Juli": "July", "August": "August",
    "September": "September", "Oktober": "October", "November": "November", "Dezember": "December",
    "Jan": "Jan", "Feb": "Feb", "Mär": "Mar", "Mar": "Mar", "Apr": "Apr", "Mai": "May",
    "May": "May", "Jun": "Jun", "Jul": "Jul", "Aug": "Aug", "Sep": "Sep", "Okt": "Oct",
    "Oct": "Oct", "Nov": "Nov", "Dez": "Dec", "Dec": "Dec",
}

DATE_PATTERNS = [
    (r"\b(\d{4})[-/.](\d{2})[-/.](\d{2})\b", "%Y-%m-%d"),
    (r"\b(\d{2})[-/.](\d{2})[-/.](\d{4})\b", "%d.%m.%Y"),
    (r"\b(\d{2})/(\d{2})/(\d{4})\b", "%m/%d/%Y"),
    (r"\b(\d{4})/(\d{2})/(\d{2})\b", "%Y/%m/%d"),
    (r"\b(\d{1,2})[.\s]?(Jan|Feb|Mär|Mar|Apr|Mai|May|Jun|Jul|Aug|Sep|Okt|Oct|Nov|Dez|Dec)[.]?\s?(\d{4})\b", "%d %b %Y"),
    (r"\b(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})\b", "%d %B %Y"),
    (r"\b(\d{8})\b", "%Y%m%d"),
    (r"\b(\d{1,2}) (Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember) (\d{4})\b", "%d %B %Y"),
]

def detect_date(text: str) -> str | None:
    if not text:
        return None
    norm = text
    for ger, eng in GERMAN_MONTHS.items():
        norm = re.sub(rf"\b{re.escape(ger)}\b", eng, norm, flags=re.IGNORECASE)
    for pattern, fmt in DATE_PATTERNS:
        m = re.search(pattern, norm, re.IGNORECASE)
        if m:
            try:
                val = " ".join(m.groups())
                return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    try:
        return dateutil.parser.parse(norm, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return None

# -----------------------------
# Plugins
# -----------------------------
class Plugin:
    extensions: tuple[str, ...] = ()
    def process_file(self, path: str) -> str:
        raise NotImplementedError

class PDFPlugin(Plugin):
    extensions = ("pdf",)
    def process_file(self, path: str) -> str:
        return extract_text_from_pdf(path)

class ImagePlugin(Plugin):
    extensions = ("png", "jpg", "jpeg")
    def process_file(self, path: str) -> str:
        return extract_text_from_image(path)

class EMLPlugin(Plugin):
    extensions = ("eml",)
    def process_file(self, path: str) -> str:
        import email
        from email import policy
        from email.parser import BytesParser
        with open(path, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)
        body = msg.get_body(preferencelist=("plain",))
        return body.get_content() if body else ""

class WordPlugin(Plugin):
    extensions = ("docx",)
    def process_file(self, path: str) -> str:
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)

class ExcelPlugin(Plugin):
    extensions = ("xlsx",)
    def process_file(self, path: str) -> str:
        wb = load_workbook(path, data_only=True, read_only=True)
        out: list[str] = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                out.append(" ".join(str(c) for c in row if c is not None))
        return "\n".join(out)

PLUGINS: list[Plugin] = [PDFPlugin(), ImagePlugin(), EMLPlugin(), WordPlugin(), ExcelPlugin()]
EXT_TO_PLUGIN: dict[str, Plugin] = {ext: plugin for plugin in PLUGINS for ext in plugin.extensions}

@lru_cache(maxsize=512)
def extract_text_cached(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    plugin = EXT_TO_PLUGIN.get(ext)
    if not plugin:
        logging.warning("Nicht unterstützte Erweiterung: %s", ext)
        return ""
    try:
        return plugin.process_file(path)
    except Exception as e:
        logging.error("Textextraktion fehlgeschlagen (%s): %s", path, e)
        return ""

# -----------------------------
# Text analysis
# -----------------------------
@dataclass
class ExtractedInfo:
    company_name: str = "Unbekannt"
    date: str = ""
    number: str = ""

@lru_cache(maxsize=1024)
def analyze_text(text: str, known_companies: tuple[str, ...] = ()) -> ExtractedInfo:
    info = ExtractedInfo()
    try:
        rules = config.data.get("SUPPLIER_RULES", {})
        for _, rule in rules.items():
            if re.search(rule.get("match", ""), text, flags=re.IGNORECASE):
                info.company_name = rule.get("name", info.company_name)
                inv_pat = rule.get("invoice_pattern")
                if inv_pat:
                    msp = re.search(inv_pat, text, flags=re.IGNORECASE)
                    if msp:
                        info.number = msp.group(0)
                        return info
        company_keywords = ["GmbH", "GbR", "OHG", "AG", "KG", "UG", "e.K.", "e.V."]
        for c in sorted(known_companies, key=len, reverse=True):
            if re.search(rf"\b{re.escape(c)}\b", text):
                info.company_name = c
                break
        else:
            m = re.search(rf"([\wÄÖÜäöüß&.,\- ]+)\s+(?:{'|'.join(map(re.escape, company_keywords))})", text)
            if m:
                info.company_name = m.group(1).strip()
        date_matches = re.findall(r"\b\d{2}\.\d{2}\.\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{8}\b", text)
        for d in date_matches:
            detected = detect_date(d)
            if detected:
                info.date = detected
                break
        if not info.date:
            detected = detect_date(text)
            if detected:
                info.date = detected
        patterns = [
            r"Rechnung\s*Nr\.?\s*[:#-]?\s*([A-Za-z0-9\-_/]+)",
            r"Rechnungsnummer\s*[:#-]?\s*([A-Za-z0-9\-_/]+)",
        ]
        for p in patterns:
            m = re.search(p, text, flags=re.IGNORECASE)
            if m:
                info.number = m.group(1).strip()
                break
    except Exception as e:
        logging.error("Analyse fehlgeschlagen: %s", e)
    return info

def format_filename(info: ExtractedInfo, ext: str) -> str:
    safe_company = re.sub(r"[\\/:*?\"<>|]", "_", info.company_name).strip() or "Unbekannt"
    safe_number = re.sub(r"\s+", "_", info.number)
    date = info.date or "0000-00-00"
    return config.data["FILENAME_PATTERN"].format(
        date=date, company=safe_company, number=safe_number, ext=ext
    )

# -----------------------------
# File operations
# -----------------------------
@dataclass
class ProcessResult:
    src: str
    dst: str | None
    error: str | None

def ensure_backup(path: str):
    try:
        backup_dir = os.path.join(os.path.dirname(path), config.data["BACKUP_DIR"])
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(path, backup_dir)
    except Exception as e:
        logging.warning("Backup fehlgeschlagen (%s): %s", path, e)

def file_hash_sha256(path: str, chunk_size: int = 1 << 20) -> str:
    h = sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def move_unique(src: str, dst: str) -> str:
    base, ext = os.path.splitext(dst)
    candidate = dst
    n = 1
    while os.path.exists(candidate):
        if file_hash_sha256(src) == file_hash_sha256(candidate):
            logging.info("Duplikat erkannt, überspringe: %s", src)
            return candidate
        candidate = f"{base}_{n}{ext}"
        n += 1
    shutil.move(src, candidate)
    return candidate

def process_one_file(path: str, known_companies: tuple[str, ...]) -> ProcessResult:
    try:
        ensure_backup(path)
        text = extract_text_cached(path)
        info = analyze_text(text, known_companies)
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        year = (info.date or "0000-00-00").split("-")[0]
        root_target = config.data.get("MAIN_TARGET_DIR") or os.path.dirname(path)
        year_dir = os.path.join(root_target, year)
        company_dir = os.path.join(year_dir, re.sub(r"[\\/:*?\"<>|]", "_", info.company_name) or "Unbekannt")
        os.makedirs(company_dir, exist_ok=True)
        new_name = format_filename(info, ext)
        dst = os.path.join(company_dir, new_name)
        dst = move_unique(path, dst)
        return ProcessResult(src=path, dst=dst, error=None)
    except Exception as e:
        try:
            err_dir = os.path.join(os.path.dirname(path), "errors")
            os.makedirs(err_dir, exist_ok=True)
            shutil.move(path, os.path.join(err_dir, os.path.basename(path)))
        except Exception:
            pass
        return ProcessResult(src=path, dst=None, error=str(e))

# -----------------------------
# GUI
# -----------------------------
def run_gui():
    root = tk.Tk()
    root.title("Dateiumbenennungstool")

    src_dir = tk.StringVar(value=config.data.get("DEFAULT_SOURCE_DIR", ""))

    def select_dir():
        d = filedialog.askdirectory()
        if d:
            src_dir.set(d)

    def start_process():
        directory = src_dir.get()
        if not directory or not os.path.isdir(directory):
            messagebox.showerror("Fehler", "Bitte gültiges Quellverzeichnis wählen.")
            return
        files = [os.path.join(directory, f) for f in os.listdir(directory)
                 if f.split(".")[-1].lower() in config.data["ALLOWED_EXTENSIONS"]]
        if not files:
            messagebox.showinfo("Info", "Keine passenden Dateien gefunden.")
            return
        known = tuple(load_companies())
        results = []
        for f in files:
            r = process_one_file(f, known)
            results.append(r)
        ok = [r for r in results if not r.error]
        err = [r for r in results if r.error]
        messagebox.showinfo("Fertig",
                            f"{len(ok)} Dateien verarbeitet, {len(err)} Fehler.")

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10, fill="x")

    tk.Label(frame, text="Quellverzeichnis:").grid(row=0, column=0, sticky="w")
    tk.Entry(frame, textvariable=src_dir, width=50).grid(row=0, column=1)
    tk.Button(frame, text="Wählen", command=select_dir).grid(row=0, column=2)

    tk.Button(root, text="Dateien umbenennen und organisieren", command=start_process)\
        .pack(pady=10)

    root.mainloop()

# -----------------------------
# Utilities
# -----------------------------
def load_companies() -> list[str]:
    if os.path.exists(COMPANIES_FILE):
        with open(COMPANIES_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return []

if __name__ == "__main__":
    run_gui()
