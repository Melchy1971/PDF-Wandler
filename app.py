import os
import re
import json
import shutil
import threading
import queue
import subprocess
from pathlib import Path

import pdfplumber
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import dateparser
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

# ===============================================================
# Konfiguration / Config-Datei
# ===============================================================
APP_NAME = "Rechnungs-Assistent"
CONFIG_PATH = Path("config.json")
DEFAULT_CONFIG = {
    "input_dir": "input",
    "output_dir": "output",
    "unknown_dirname": "unbekannt",
    "max_pages_ocr": 3,
    "langs_ocr": "deu+eng",
    "use_ollama": False,
    "ollama_model": "llama3",
    "ollama_url": "http://localhost:11434/api/generate"
}

COMPANY_KEYWORDS = [
    "GmbH", "AG", "KG", "UG", "OHG", "e.K.", "GmbH & Co. KG", "Inc", "LLC", "Limited", "Ltd", "eG"
]

RE_DATE_HINTS = re.compile(r"(rechnungsdatum|ausgestellt\s*am|datum)\s*[:\-]?\s*(?P<date>\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{1,2}-\d{1,2})", re.IGNORECASE)
RE_DATE_FALLBACK = re.compile(r"(?P<date>\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{1,2}-\d{1,2})")
RE_INVOICE_NO = re.compile(r"(rechnungs(?:nummer|nr\.? )|rechnung\s*#?|invoice\s*(no\.|#)?)\s*[:\-]?\s*(?P<no>[A-Z0-9\-\/]{4,})", re.IGNORECASE)

# ----------------- Config-Helper -----------------

def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = DEFAULT_CONFIG.copy()
    else:
        cfg = DEFAULT_CONFIG.copy()
        save_config(cfg)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ===============================================================
# Extraktion & PDF-Handling
# ===============================================================

def extract_text_from_pdf(pdf_path: Path) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            texts = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    texts.append(t)
            return "\n".join(texts)
    except Exception:
        return ""


def ocr_pdf(pdf_path: Path, max_pages: int, langs_ocr: str) -> str:
    text_chunks = []
    try:
        images = convert_from_path(str(pdf_path), first_page=1, last_page=max_pages, dpi=300)
        for im in images:
            txt = pytesseract.image_to_string(im, lang=langs_ocr)
            if txt.strip():
                text_chunks.append(txt)
    except Exception:
        pass
    return "\n".join(text_chunks)


def guess_supplier(full_text: str):
    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    head = lines[:15]
    for ln in head:
        for kw in COMPANY_KEYWORDS:
            if kw.lower() in ln.lower():
                cand = re.split(r"[•\|,;/]{1}", ln)[0].strip()
                return cand[:80]
    before_invoice = []
    for ln in head:
        if re.search(r"\brechnung\b", ln, re.IGNORECASE):
            break
        before_invoice.append(ln)
    if before_invoice:
        cand = before_invoice[0]
        return re.sub(r"\s{2,}", " ", cand)[:80]
    return None


def parse_date(s):
    if not s:
        return None
    dt = dateparser.parse(s, settings={"DATE_ORDER": "DMY", "PREFER_DAY_OF_MONTH": "first"})
    return dt.date() if dt else None


def parse_invoice_fields(full_text: str) -> dict:
    data = {"supplier": None, "invoice_no": None, "invoice_date": None}

    m = RE_DATE_HINTS.search(full_text)
    if m:
        data["invoice_date"] = parse_date(m.group("date"))
    else:
        m2 = RE_DATE_FALLBACK.search(full_text)
        if m2:
            data["invoice_date"] = parse_date(m2.group("date"))

    m3 = RE_INVOICE_NO.search(full_text)
    if m3:
        raw = m3.group("no")
        raw = re.sub(r"[^\w\-\/]", "", raw)
        data["invoice_no"] = raw[:40]

    data["supplier"] = guess_supplier(full_text)
    return data


def normalize_supplier_with_ollama(supplier: str, cfg: dict) -> str:
    if not supplier or not cfg.get("use_ollama"):
        return supplier
    try:
        import requests
        prompt = (
            "Extrahiere den reinen Firmennamen aus diesem Text, ohne Adresse oder Zusätze. "
            "Gib nur den Namen zurück:\n\n" + supplier
        )
        payload = {"model": cfg.get("ollama_model", "llama3"), "prompt": prompt, "stream": False}
        r = requests.post(cfg.get("ollama_url", "http://localhost:11434/api/generate"), json=payload, timeout=10)
        name = r.json().get("response", "").strip()
        name = re.sub(r"[\n\r\t]", " ", name)
        name = re.sub(r"\s{2,}", " ", name)
        return name[:80] if name else supplier
    except Exception:
        return supplier


def first_page_as_image(pdf_path: Path):
    try:
        images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=200)
        return images[0] if images else None
    except Exception:
        return None


def write_summary_pdf(dst_path: Path, fields: dict, source_pdf: Path, preview_image: Image.Image | None):
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    c = rl_canvas.Canvas(str(dst_path), pagesize=A4)
    width, height = A4
    margin = 20 * mm
    y = height - margin

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, "Rechnungs-Zusammenfassung")
    y -= 12 * mm

    def line(label, value):
        nonlocal y
        c.setFont("Helvetica", 11)
        c.drawString(margin, y, f"{label}: {value}")
        y -= 8 * mm

    dateval = fields.get("invoice_date").isoformat() if fields.get("invoice_date") else "—"
    line("Rechnungsdatum", dateval)
    line("Lieferant", fields.get("supplier") or "—")
    line("Rechnungsnummer", fields.get("invoice_no") or "—")
    line("Quelle", str(source_pdf.name))

    y -= 5 * mm
    c.line(margin, y, width - margin, y)
    y -= 5 * mm

    if preview_image is not None:
        max_w = width - 2*margin
        target_h = 120 * mm
        im_w, im_h = preview_image.size
        scale = min(max_w / im_w, target_h / im_h)
        new_size = (int(im_w * scale), int(im_h * scale))
        thumb = preview_image.resize(new_size)
        c.drawImage(ImageReader(thumb), margin, y - new_size[1], width=new_size[0], height=new_size[1], preserveAspectRatio=True, mask='auto')
        y -= new_size[1] + 5 * mm

    c.showPage()
    c.save()


def build_base_name(fields: dict, unknown_dirname: str, cfg: dict):
    date_part = fields.get("invoice_date")
    supplier = fields.get("supplier")
    inv_no = fields.get("invoice_no")

    if supplier:
        supplier = normalize_supplier_with_ollama(supplier, cfg)
        supplier = re.sub(r"[\\/:*?\"<>|]", "_", supplier)

    if date_part:
        year = str(date_part.year)
        date_str = date_part.isoformat()
    else:
        year = unknown_dirname
        date_str = "unknown-date"

    if not supplier:
        supplier = unknown_dirname
    if not inv_no:
        inv_no = "unknown-no"

    base_name = f"{date_str}_{supplier}_Re-{inv_no}"
    return year, supplier, base_name


def process_pdf(pdf_path: Path, cfg: dict, log=lambda msg: None):
    unknown_dirname = cfg.get("unknown_dirname", "unbekannt")
    output_dir = Path(cfg.get("output_dir", "output"))

    log(f"Verarbeite: {pdf_path.name}")

    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        text = ocr_pdf(pdf_path, cfg.get("max_pages_ocr", 3), cfg.get("langs_ocr", "deu+eng"))

    fields = parse_invoice_fields(text)

    if not any([fields.get("invoice_no"), fields.get("supplier"), fields.get("invoice_date")]):
        target_folder = output_dir / unknown_dirname
        target_folder.mkdir(parents=True, exist_ok=True)
        dst = target_folder / pdf_path.name
        shutil.copy2(pdf_path, dst)
        log(f"→ Keine Felder erkannt. Verschoben nach: {dst}")
        return

    year, supplier, base_name = build_base_name(fields, unknown_dirname, cfg)
    folder = output_dir / year / supplier
    folder.mkdir(parents=True, exist_ok=True)

    # 1) Original-PDF unter vorgegebenem Namen speichern
    dst_original = folder / f"{base_name}.pdf"
    shutil.copy2(pdf_path, dst_original)

    # 2) Zusammenfassung als separate Datei mit Suffix -summary
    preview = first_page_as_image(pdf_path)
    dst_summary = folder / f"{base_name}-summary.pdf"
    write_summary_pdf(dst_summary, fields, pdf_path, preview_image=preview)

    log(f"→ Original gespeichert: {dst_original}")
    log(f"→ Zusammenfassung gespeichert: {dst_summary}")


def process_all(cfg: dict, files=None, log=lambda msg: None, progress=lambda cur, total: None):
    input_dir = Path(cfg.get("input_dir", "input"))
    output_dir = Path(cfg.get("output_dir", "output"))
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    pdfs = files if files is not None else list(input_dir.glob("*.pdf"))
    total = len(pdfs)
    if total == 0:
        log("Keine PDFs gefunden. Lege Dateien in den Input-Ordner oder wähle einzelne aus.")
        progress(0, 1)
        return

    for idx, p in enumerate(pdfs, start=1):
        try:
            process_pdf(p, cfg, log=log)
        except Exception as e:
            unk = output_dir / cfg.get("unknown_dirname", "unbekannt")
            unk.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, unk / p.name)
            log(f"Fehler bei {p.name}: {e}\n→ Datei nach '{unk}' kopiert.")
        finally:
            progress(idx, total)


# ===============================================================
# GUI – Tkinter (mit Fortschrittsbalken, Ollama-Checkbox, Dateiliste)
# ===============================================================

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x680")
        self.minsize(880, 600)

        self.cfg = load_config()
        self.log_queue = queue.Queue()
        self.worker = None

        self.create_widgets()
        self.refresh_file_list()
        self.after(100, self.poll_log_queue)

    # ----------------- Widgets -----------------
    def create_widgets(self):
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        path_frame = ttk.LabelFrame(frm, text="Pfade & Einstellungen")
        path_frame.pack(fill=tk.X)

        ttk.Label(path_frame, text="Input-Ordner:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=6)
        self.var_input = tk.StringVar(value=self.cfg.get("input_dir"))
        ttk.Entry(path_frame, textvariable=self.var_input, width=60).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Button(path_frame, text="Wählen…", command=self.choose_input).grid(row=0, column=2, padx=6)

        ttk.Label(path_frame, text="Output-Ordner:").grid(row=1, column=0, sticky=tk.W, padx=6, pady=6)
        self.var_output = tk.StringVar(value=self.cfg.get("output_dir"))
        ttk.Entry(path_frame, textvariable=self.var_output, width=60).grid(row=1, column=1, sticky=tk.W, padx=6)
        ttk.Button(path_frame, text="Wählen…", command=self.choose_output).grid(row=1, column=2, padx=6)

        ttk.Label(path_frame, text="OCR-Seiten (max):").grid(row=2, column=0, sticky=tk.W, padx=6, pady=6)
        self.var_maxpages = tk.IntVar(value=int(self.cfg.get("max_pages_ocr", 3)))
        ttk.Spinbox(path_frame, from_=1, to=10, textvariable=self.var_maxpages, width=6).grid(row=2, column=1, sticky=tk.W, padx=6)

        ttk.Label(path_frame, text="Tesseract-Sprachen:").grid(row=2, column=1, sticky=tk.E, padx=(180,6))
        self.var_langs = tk.StringVar(value=self.cfg.get("langs_ocr", "deu+eng"))
        ttk.Entry(path_frame, textvariable=self.var_langs, width=12).grid(row=2, column=1, sticky=tk.W, padx=(310,6))

        self.var_use_ollama = tk.BooleanVar(value=bool(self.cfg.get("use_ollama", False)))
        ttk.Checkbutton(path_frame, text="Ollama verwenden (Lieferant normalisieren)", variable=self.var_use_ollama).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=6, pady=(0,6))

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill=tk.X, pady=8)
        ttk.Button(btn_frame, text="Verarbeiten (alle)", command=self.start_processing_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Nur ausgewählte verarbeiten", command=self.start_processing_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Liste aktualisieren", command=self.refresh_file_list).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Config öffnen", command=self.open_config).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Config speichern", command=self.save_current_config).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Beenden", command=self.exit_app).pack(side=tk.RIGHT, padx=4)

        center = ttk.Frame(frm)
        center.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(center, text="PDFs im Input-Ordner (Mehrfachauswahl möglich)")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,8))
        self.listbox = tk.Listbox(left, selectmode=tk.EXTENDED)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        right = ttk.LabelFrame(center, text="Protokoll")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.txt = tk.Text(right, height=18, wrap=tk.WORD)
        self.txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        bottom = ttk.Frame(frm)
        bottom.pack(fill=tk.X)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill=tk.X, padx=6, pady=6)

    # ----------------- Helper & Actions -----------------
    def choose_input(self):
        d = filedialog.askdirectory(initialdir=self.var_input.get() or ".")
        if d:
            self.var_input.set(d)
            self.refresh_file_list()

    def choose_output(self):
        d = filedialog.askdirectory(initialdir=self.var_output.get() or ".")
        if d:
            self.var_output.set(d)

    def log(self, msg: str):
        self.log_queue.put(("log", msg))

    def set_progress(self, cur, total):
        self.log_queue.put(("progress", cur, total))

    def poll_log_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item[0] == "log":
                    self.txt.insert('end', item[1] + "\n")
                    self.txt.see('end')
                elif item[0] == "progress":
                    cur, total = item[1], item[2]
                    self.progress.configure(maximum=total)
                    self.progress['value'] = cur
        except queue.Empty:
            pass
        self.after(100, self.poll_log_queue)

    def refresh_file_list(self):
        self.listbox.delete(0, 'end')
        input_dir = Path(self.var_input.get() or self.cfg.get("input_dir", "input"))
        input_dir.mkdir(exist_ok=True)
        for p in sorted(input_dir.glob("*.pdf")):
            self.listbox.insert('end', str(p))

    def _prepare_cfg_from_ui(self):
        self.cfg["input_dir"] = self.var_input.get()
        self.cfg["output_dir"] = self.var_output.get()
        self.cfg["max_pages_ocr"] = int(self.var_maxpages.get())
        self.cfg["langs_ocr"] = self.var_langs.get()
        self.cfg["use_ollama"] = bool(self.var_use_ollama.get())
        save_config(self.cfg)

    def _run_worker(self, files):
        self.txt.delete('1.0', 'end')
        self.progress['value'] = 0
        self.log("Starte Verarbeitung…")
        def work():
            try:
                process_all(self.cfg, files=files, log=self.log, progress=self.set_progress)
                self.log("Fertig.")
            except Exception as e:
                self.log(f"Fehler: {e}")
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def start_processing_all(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME, "Verarbeitung läuft bereits…")
            return
        self._prepare_cfg_from_ui()
        self._run_worker(files=None)

    def start_processing_selected(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME, "Verarbeitung läuft bereits…")
            return
        self._prepare_cfg_from_ui()
        sels = [self.listbox.get(i) for i in self.listbox.curselection()]
        if not sels:
            messagebox.showinfo(APP_NAME, "Bitte eine oder mehrere PDF-Dateien in der Liste markieren.")
            return
        files = [Path(s) for s in sels]
        self._run_worker(files=files)

    def open_config(self):
        if not CONFIG_PATH.exists():
            save_config(self.cfg)
        try:
            if os.name == "nt":
                os.startfile(CONFIG_PATH)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(CONFIG_PATH)])
            else:
                subprocess.Popen(["xdg-open", str(CONFIG_PATH)])
            self.log(f"Config geöffnet: {CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Konnte Config nicht öffnen: {e}")

    def save_current_config(self):
        self._prepare_cfg_from_ui()
        self.log("Config gespeichert.")

    def exit_app(self):
        self.destroy()


if __name__ == "__main__":
    try:
        App().mainloop()
    except KeyboardInterrupt:
        pass
