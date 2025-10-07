# -------- Abhängigkeits-Check (freundliche Meldung) --------
def _ensure_dependencies_or_die():
    missing = []
    try:
        import yaml  # PyYAML
    except Exception:
        missing.append("pyyaml")
    # Die folgenden sind optional für OCR/Preview; wir prüfen sie und geben Tipps aus
    opt_missing = []
    for mod, pipname in [("fitz", "pymupdf"), ("PyPDF2", "PyPDF2"), ("pytesseract", "pytesseract"), ("pdf2image", "pdf2image"), ("PIL", "pillow")]:
        try:
            __import__(mod)
        except Exception:
            opt_missing.append(pipname)
    if missing or opt_missing:
        msg = ["Es fehlen Python-Pakete:", ""]
        if missing:
            msg.append("Pflicht: " + ", ".join(sorted(set(missing))))
        if opt_missing:
            msg.append("Optional (für OCR/Vorschau): " + ", ".join(sorted(set(opt_missing))))
        msg.append("")
        msg.append("Installation (Konsole):")
        msg.append("  python -m pip install --upgrade pip")
        if missing or opt_missing:
            all_pkgs = sorted(set((missing or []) + (opt_missing or [])))
            msg.append("  pip install " + " ".join(all_pkgs))
        full = "\n".join(msg)
        try:
            import tkinter as _tk
            from tkinter import messagebox as _msg
            root = _tk.Tk(); root.withdraw()
            _msg.showerror("Fehlende Abhängigkeiten", full)
            root.destroy()
        except Exception:
            print(full)
        import sys
        sys.exit(1)
# Vor dem Start prüfen
_ensure_dependencies_or_die()
# -----------------------------------------------------------
import os
import sys
import io
import csv
import re
import shutil
import threading
import queue
import subprocess
import tkinter as tk
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from tkinter import filedialog, messagebox, ttk
import yaml

from roles_utils import normalize_roles
# Importiere die vorhandene Logik aus sorter.py (erweiterte Version mit Callbacks)
try:
    import sorter  # benötigt process_all(..., stop_fn, progress_fn) und Extraktions-Helpers
except Exception as e:
    sorter = None
APP_TITLE = "Invoice Sorter – GUI"
DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_PATTERNS_PATH = "patterns.yaml"


def _sanitize_folder_name(name) -> str:
    if not name:
        return ""
    text = str(name).strip()
    if not text:
        return ""
    text = re.sub(r"[\\/:*?\"<>|]", "_", text)
    return text or ""


def _normalize_analysis(data) -> dict:
    if data is None:
        return {}
    if isinstance(data, dict):
        return dict(data)
    try:
        return dict(vars(data))
    except Exception:
        return {"result": data}


def _fallback_process_all(cfg_like, patterns_path, stop_fn=None, progress_fn=None, log_csv_path=None):
    cfg_like = cfg_like or {}
    input_dir = Path(cfg_like.get("input_dir") or "inbox")
    output_dir = Path(cfg_like.get("output_dir") or "processed")
    unknown_dir_name = cfg_like.get("unknown_dir_name") or "unbekannt"
    dry_run = bool(cfg_like.get("dry_run", False))

    def _load_patterns_once(path_like):
        patterns_dict = {}
        if sorter and hasattr(sorter, "load_patterns"):
            try:
                loaded = sorter.load_patterns(path_like)
                if isinstance(loaded, dict):
                    patterns_dict = dict(loaded)
            except Exception as exc:  # pragma: no cover - GUI fallback logging
                print(f"[Fallback] Konnte Muster nicht laden: {exc}", file=sys.stderr)
        if not patterns_dict and path_like:
            try:
                raw = yaml.safe_load(Path(path_like).read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    patterns_dict = dict(raw)
            except FileNotFoundError:
                pass
            except Exception as exc:  # pragma: no cover - GUI fallback logging
                print(f"[Fallback] Muster-Datei konnte nicht gelesen werden: {exc}", file=sys.stderr)
        return patterns_dict

    patterns_dict = _load_patterns_once(patterns_path)
    invoice_patterns = list(patterns_dict.get("invoice_number_patterns") or [])
    date_patterns = list(patterns_dict.get("date_patterns") or [])
    supplier_hints = patterns_dict.get("supplier_hints") or {}

    use_ocr = bool(cfg_like.get("use_ocr", True))
    poppler_path = cfg_like.get("poppler_path") or ""
    tesseract_cmd = cfg_like.get("tesseract_cmd") or ""
    tesseract_lang = cfg_like.get("tesseract_lang") or "deu+eng"

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / unknown_dir_name).mkdir(parents=True, exist_ok=True)

    csv_file = None
    csv_writer = None
    if log_csv_path:
        csv_path = Path(log_csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        existing = csv_path.exists() and csv_path.stat().st_size > 0
        csv_file = csv_path.open("a", encoding="utf-8", newline="")
        csv_writer = csv.writer(csv_file, delimiter=";")
        if not existing:
            csv_writer.writerow([
                "timestamp",
                "source",
                "destination",
                "invoice_no",
                "supplier",
                "invoice_date",
                "status",
            ])
            csv_file.flush()

    files = sorted(
        p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"
    )
    total = len(files)
    print(f"[Fallback] {total} PDF-Datei(en) in {input_dir} gefunden.")

    def _manual_analyze(pdf_path: Path):
        data = {"source": str(pdf_path)}
        text = ""
        method = "unavailable"
        if sorter and hasattr(sorter, "extract_text_from_pdf"):
            try:
                text, method = sorter.extract_text_from_pdf(
                    str(pdf_path),
                    use_ocr=use_ocr,
                    poppler_path=poppler_path or None,
                    tesseract_cmd=tesseract_cmd or None,
                    tesseract_lang=tesseract_lang or "deu+eng",
                )
            except Exception as exc:  # pragma: no cover - GUI fallback logging
                method = "error"
                data.setdefault("error", str(exc))
        data.setdefault("text_method", method)
        data.setdefault("text_length", len(text))
        if text:
            if sorter and hasattr(sorter, "extract_invoice_no"):
                try:
                    data["invoice_no"] = sorter.extract_invoice_no(text, invoice_patterns)
                except Exception as exc:  # pragma: no cover - GUI fallback logging
                    data.setdefault("error", str(exc))
                    data.setdefault("invoice_no", None)
            if sorter and hasattr(sorter, "extract_date"):
                try:
                    data["invoice_date"] = sorter.extract_date(text, date_patterns)
                except Exception as exc:  # pragma: no cover - GUI fallback logging
                    data.setdefault("error", str(exc))
                    data.setdefault("invoice_date", None)
            if sorter and hasattr(sorter, "detect_supplier"):
                try:
                    data["supplier"] = sorter.detect_supplier(text, supplier_hints)
                except Exception as exc:  # pragma: no cover - GUI fallback logging
                    data.setdefault("error", str(exc))
                    data.setdefault("supplier", None)
        data.setdefault("invoice_no", None)
        data.setdefault("invoice_date", None)
        data.setdefault("supplier", None)
        return data

    try:
        for idx, pdf in enumerate(files, start=1):
            if stop_fn and stop_fn():
                print("[Fallback] Stop angefordert – Abbruch.")
                break

            analysis_dict = {}
            try:
                if sorter and hasattr(sorter, "analyze_pdf"):
                    analysis_dict = _normalize_analysis(
                        sorter.analyze_pdf(
                            str(pdf),
                            config=cfg_like,
                            patterns=patterns_dict,
                        )
                    )
                else:
                    analysis_dict = {}
            except Exception as exc:
                print(
                    f"[Fallback] Analyse fehlgeschlagen für {pdf.name}: {exc}",
                    file=sys.stderr,
                )
                analysis_dict = {"error": str(exc), "validation_status": "fail"}

            if not analysis_dict:
                manual = _manual_analyze(pdf)
                analysis_dict = manual
            else:
                if (not analysis_dict.get("invoice_no")) and (not analysis_dict.get("invoice_date")) and (
                    not analysis_dict.get("supplier")
                ):
                    manual = _manual_analyze(pdf)
                    for key, value in manual.items():
                        if key not in analysis_dict or not analysis_dict.get(key):
                            analysis_dict[key] = value

            analysis_dict.setdefault("text_method", "unavailable")
            analysis_dict.setdefault("text_length", 0)
            analysis_dict.setdefault("source", str(pdf))

            raw_supplier = analysis_dict.get("supplier")
            supplier_value = raw_supplier if raw_supplier else unknown_dir_name
            supplier_value = str(supplier_value)
            supplier_folder = _sanitize_folder_name(supplier_value) or unknown_dir_name
            target_dir = output_dir / supplier_folder
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / pdf.name

            status = analysis_dict.get("validation_status")
            moved_path = str(target_path)
            move_failed = False

            if dry_run:
                print(f"[Fallback] (Dry-Run) {pdf.name} -> {target_path}")
            else:
                try:
                    shutil.move(str(pdf), moved_path)
                    print(f"[Fallback] {pdf.name} -> {target_path}")
                except Exception as exc:
                    move_failed = True
                    moved_path = str(pdf)
                    status = "fail"
                    print(
                        f"[Fallback] Verschieben fehlgeschlagen für {pdf.name}: {exc}",
                        file=sys.stderr,
                    )

            invoice_no_val = analysis_dict.get("invoice_no")
            invoice_date_val = analysis_dict.get("invoice_date")
            supplier_known = bool(raw_supplier) and str(raw_supplier).lower() != str(unknown_dir_name).lower()

            if move_failed:
                status = "fail"
            else:
                if not status:
                    if invoice_no_val and invoice_date_val and supplier_known:
                        status = "ok"
                    else:
                        status = "needs_review"
            analysis_dict["supplier"] = supplier_value

            analysis_dict.setdefault("invoice_no", None)
            analysis_dict.setdefault("invoice_date", None)
            analysis_dict["validation_status"] = status
            analysis_dict["status"] = status
            analysis_dict.setdefault("destination", moved_path)
            analysis_dict.setdefault("target_path", moved_path)
            analysis_dict.setdefault("target", moved_path)
            analysis_dict.setdefault("output_path", moved_path)
            analysis_dict.setdefault("dest", moved_path)
            analysis_dict.setdefault("destination_path", moved_path)
            analysis_dict.setdefault("resolved_path", moved_path)
            analysis_dict.setdefault("moved_path", moved_path)
            analysis_dict.setdefault("original_filename", pdf.name)
            analysis_dict["simulate"] = dry_run
            analysis_dict["moved"] = not move_failed and not dry_run

            data_ns = SimpleNamespace(**analysis_dict)
            if progress_fn:
                try:
                    progress_fn(idx, total, str(pdf), data_ns)
                except Exception as exc:
                    print(f"[Fallback] progress_fn-Fehler: {exc}", file=sys.stderr)

            if csv_writer:
                csv_writer.writerow(
                    [
                        datetime.now().isoformat(timespec="seconds"),
                        str(pdf),
                        moved_path,
                        analysis_dict.get("invoice_no"),
                        supplier_value,
                        analysis_dict.get("invoice_date"),
                        status,
                    ]
                )
                csv_file.flush()
    finally:
        if csv_file:
            csv_file.close()
class TextQueueWriter(io.TextIOBase):
    """Leitet stdout/stderr-Text in eine Queue, damit das GUI Logs anzeigen kann."""
    def __init__(self, q: queue.Queue, tag: str = "INFO"):
        super().__init__()
        # Maximiert starten (best effort)
        try:
            self.state('zoomed')
        except Exception:
            pass
        try:
            self.attributes('-zoomed', True)
        except Exception:
            pass
        self.q = q
        self.tag = tag
    def write(self, s):
        if s and s.strip() != "":
            self.q.put((self.tag, s))
        return len(s)
    def flush(self):
        pass
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x760")
        self.minsize(980, 680)
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                pass
        self.queue = queue.Queue()
        self.worker_thread = None
        self.stop_flag = threading.Event()
        self.cfg = {}
        self.config_path = DEFAULT_CONFIG_PATH
        self.patterns_path = DEFAULT_PATTERNS_PATH
        self.var_inbox = tk.StringVar()
        self.var_done = tk.StringVar()
        self.var_err = tk.StringVar()
        self.default_filename_label = "Datum_Lieferant_Rechnungsnummer.pdf"
        self.filename_presets = [
            (self.default_filename_label, "{date}_{supplier}_{invoice_no}.pdf"),
            ("Lieferant_Rechnungsnummer.pdf", "{supplier}_{invoice_no}.pdf"),
            ("Rechnungsnummer_Lieferant.pdf", "{invoice_no}_{supplier}.pdf"),
            ("Datum_Lieferant.pdf", "{date}_{supplier}.pdf"),
            ("Originalname.pdf", "{original_name}.pdf"),
        ]
        self.filename_preset_map = dict(self.filename_presets)
        self.filename_preset_inverse = {fmt: label for label, fmt in self.filename_presets}
        self.var_filename_pattern = tk.StringVar(value=self.default_filename_label)
        self._manual_window = None

        # für Fehlerliste
        self.error_rows = []  # List[dict]
        self._build_ui()
        self._build_menubar()
        self._load_config_silent(self.config_path)
        self._ensure_dirs()
        self._log_sorter_diagnostics()
        self._poll_queue()        # Shortcuts
        # Datei
        self.bind_all("<Control-s>", lambda e: self._save_config())
        self.bind_all("<Control-S>", lambda e: self._save_config())
        self.bind_all("<Control-o>", lambda e: self._choose_config())
        self.bind_all("<Control-O>", lambda e: self._choose_config())
        self.bind_all("<Control-r>", lambda e: self._run_worker())
        self.bind_all("<Control-R>", lambda e: self._run_worker())
        self.bind_all("<Control-q>", lambda e: self._exit_app())
        self.bind_all("<Control-Q>", lambda e: self._exit_app())
        self.bind_all("<Command-s>", lambda e: self._save_config())  # macOS
        self.bind_all("<Command-S>", lambda e: self._save_config())  # macOS
        self.bind_all("<Command-o>", lambda e: self._choose_config())  # macOS
        self.bind_all("<Command-O>", lambda e: self._choose_config())  # macOS
        self.bind_all("<Command-r>", lambda e: self._run_worker())  # macOS
        self.bind_all("<Command-R>", lambda e: self._run_worker())  # macOS
        self.bind_all("<Command-q>", lambda e: self._exit_app())  # macOS
        self.bind_all("<Command-Q>", lambda e: self._exit_app())  # macOS
        # Vorschau
        self.bind_all("<Control-p>", lambda e: self._preview_any_pdf())
        self.bind_all("<Control-P>", lambda e: self._preview_any_pdf())
        self.bind_all("<Command-p>", lambda e: self._preview_any_pdf())  # macOS
        self.bind_all("<Command-P>", lambda e: self._preview_any_pdf())  # macOS
        # Start/Stop
        self.bind_all("<F5>", lambda e: self._run_worker())
        self.bind_all("<F6>", lambda e: self._stop_worker())
        self.bind_all("<Escape>", lambda e: self._stop_worker())
        # Toggle-Optionen
        self.bind_all("<Control-d>", lambda e: self._toggle_dry())
        self.bind_all("<Control-D>", lambda e: self._toggle_dry())
        self.bind_all("<Control-k>", lambda e: self._toggle_ocr())
        self.bind_all("<Control-K>", lambda e: self._toggle_ocr())
        # Pfad-Dialoge
        self.bind_all("<Control-i>", lambda e: self._choose_input())
        self.bind_all("<Control-I>", lambda e: self._choose_input())
        self.bind_all("<Control-u>", lambda e: self._choose_output())
        self.bind_all("<Control-U>", lambda e: self._choose_output())
        self.bind_all("<Control-t>", lambda e: self._choose_tesseract())
        self.bind_all("<Control-T>", lambda e: self._choose_tesseract())
        self.bind_all("<Control-b>", lambda e: self._choose_poppler())
        self.bind_all("<Control-B>", lambda e: self._choose_poppler())
        self.bind_all("<Control-Shift-p>", lambda e: self._choose_patterns())
        # Tester/Tools
        self.bind_all("<Control-Shift-r>", lambda e: self._load_patterns_for_tester())
        self.bind_all("<F9>", lambda e: self._refresh_tess_langs())
        # Aufräumen
        self.bind_all("<Control-Shift-l>", lambda e: self._log_clear())
        self.bind_all("<Control-Shift-e>", lambda e: self._errors_clear())
        # Tabs wechseln (Alt+1..5)
        self.bind_all("<Alt-1>", lambda e: self._select_tab(0))
        self.bind_all("<Alt-2>", lambda e: self._select_tab(1))
        self.bind_all("<Alt-3>", lambda e: self._select_tab(2))
        self.bind_all("<Alt-4>", lambda e: self._select_tab(3))
        self.bind_all("<Alt-5>", lambda e: self._select_tab(4))
        # Hilfe
        self.bind_all("<F1>", lambda e: self._show_info())
        self.bind_all("<Escape>", lambda e: self._stop_worker())
        self.bind_all("<Control-p>", lambda e: self._preview_any_pdf())
        self.bind_all("<Control-P>", lambda e: self._preview_any_pdf())
        self.bind_all("<Command-p>", lambda e: self._preview_any_pdf())  # macOS
        self.bind_all("<Command-P>", lambda e: self._preview_any_pdf())  # macOS
    # --------------------------
    # UI Aufbau
    # --------------------------
    def _build_ui(self):
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        # Konfiguration
        cfg_frame = ttk.LabelFrame(root, text="Konfiguration")
        cfg_frame.pack(fill=tk.X, padx=0, pady=(0, 10))
        # Zeile 1: input/output
        self.var_input = tk.StringVar()
        self.var_output = tk.StringVar()
        self.var_unknown = tk.StringVar(value="unbekannt")
        row1 = ttk.Frame(cfg_frame)
        row1.pack(fill=tk.X, pady=6)
        ttk.Label(row1, text="Eingangsordner:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(row1, textvariable=self.var_input, width=70).grid(row=0, column=1, sticky=tk.W)
        ttk.Button(row1, text="Wählen", command=self._choose_input).grid(row=0, column=2, padx=6)
        ttk.Label(row1, text="Ausgangsordner:").grid(row=1, column=0, sticky=tk.W, pady=(6,0))
        ttk.Entry(row1, textvariable=self.var_output, width=70).grid(row=1, column=1, sticky=tk.W, pady=(6,0))
        ttk.Button(row1, text="Wählen", command=self._choose_output).grid(row=1, column=2, padx=6, pady=(6,0))
        ttk.Label(row1, text="Ordner für Unbekannt:").grid(row=2, column=0, sticky=tk.W, pady=(6,0))
        ttk.Entry(row1, textvariable=self.var_unknown, width=30).grid(row=2, column=1, sticky=tk.W, pady=(6,0))
        # Zeile 1b: Dateinamen-Format
        row1b = ttk.Frame(cfg_frame)
        row1b.pack(fill=tk.X, pady=6)
        row1b.columnconfigure(1, weight=1)
        ttk.Label(row1b, text="Dateiname-Format:").grid(row=0, column=0, sticky=tk.W)
        self.cmb_filename_format = ttk.Combobox(
            row1b,
            textvariable=self.var_filename_pattern,
            values=[label for label, _ in self.filename_presets],
            width=40,
            state="normal",
        )


        self.cmb_filename_format.grid(row=0, column=1, sticky=(tk.W, tk.E))
        self.cmb_filename_format.bind("<<ComboboxSelected>>", lambda _e: self._update_filename_example())
        self.var_filename_example = tk.StringVar()
        ttk.Label(row1b, textvariable=self.var_filename_example).grid(
            row=1, column=1, sticky=tk.W, pady=(4, 0)
        )
        ttk.Label(
            row1b,
            text="Verfügbare Platzhalter: {date}, {supplier}, {invoice_no}, {original_name}",
        ).grid(row=2, column=1, sticky=tk.W, pady=(2, 0))
        self.var_filename_pattern.trace_add("write", lambda *_: self._update_filename_example())
        self._update_filename_example()
        # Zeile 2: OCR / Poppler / Tesseract / Sprache
        row2 = ttk.Frame(cfg_frame)
        row2.pack(fill=tk.X, pady=6)
        self.var_use_ocr = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="OCR verwenden (Scans)", variable=self.var_use_ocr).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(row2, text="Tesseract Pfad (tesseract.exe):").grid(row=1, column=0, sticky=tk.W, pady=(6,0))
        self.var_tesseract = tk.StringVar()
        ttk.Entry(row2, textvariable=self.var_tesseract, width=70).grid(row=1, column=1, sticky=tk.W, pady=(6,0))
        ttk.Button(row2, text="Suchen", command=self._choose_tesseract).grid(row=1, column=2, padx=6, pady=(6,0))
        ttk.Label(row2, text="Poppler bin Pfad:").grid(row=2, column=0, sticky=tk.W, pady=(6,0))
        self.var_poppler = tk.StringVar()
        ttk.Entry(row2, textvariable=self.var_poppler, width=70).grid(row=2, column=1, sticky=tk.W, pady=(6,0))
        ttk.Button(row2, text="Wählen", command=self._choose_poppler).grid(row=2, column=2, padx=6, pady=(6,0))
        ttk.Label(row2, text="Tesseract Sprache (deu/deu+eng):").grid(row=3, column=0, sticky=tk.W, pady=(6,0))
        # Dropdown mit häufigen Sprachen + manuelle Eingabe möglich
        self.var_tess_lang = tk.StringVar(value="deu+eng")
        tess_langs = ["deu", "deu+eng"]
        self.cmb_tess_lang = ttk.Combobox(row2, textvariable=self.var_tess_lang, values=tess_langs, width=28, state="normal")
        self.cmb_tess_lang.grid(row=3, column=1, sticky=tk.W, pady=(6,0))
        ttk.Button(row2, text="Aktualisieren", command=self._refresh_tess_langs).grid(row=3, column=2, padx=6, pady=(6,0))
        # Zeile 3: Ollama
        row3 = ttk.Frame(cfg_frame)
        row3.pack(fill=tk.X, pady=6)
        self.var_use_ollama = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="Ollama-Fallback verwenden", variable=self.var_use_ollama).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(row3, text="Ollama Host:").grid(row=1, column=0, sticky=tk.W, pady=(6,0))
        self.var_ollama_host = tk.StringVar(value="http://localhost:11434")
        ttk.Entry(row3, textvariable=self.var_ollama_host, width=40).grid(row=1, column=1, sticky=tk.W, pady=(6,0))
        ttk.Label(row3, text="Ollama Modell:").grid(row=1, column=2, sticky=tk.W, pady=(6,0))
        self.var_ollama_model = tk.StringVar(value="llama3")
        ttk.Entry(row3, textvariable=self.var_ollama_model, width=20).grid(row=1, column=3, sticky=tk.W, pady=(6,0))
        # Zeile 4: Dry-Run, CSV
        row4 = ttk.Frame(cfg_frame)
        row4.pack(fill=tk.X, pady=6)
        self.var_dry = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="Dry-Run (nichts verschieben)", variable=self.var_dry).grid(row=0, column=0, sticky=tk.W)
        self.var_csv = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="CSV-Log aktivieren", variable=self.var_csv).grid(row=0, column=1, sticky=tk.W, padx=(12,0))
        ttk.Label(row4, text="CSV-Pfad:").grid(row=0, column=2, sticky=tk.E)
        self.var_csv_path = tk.StringVar(value="logs/processed.csv")
        ttk.Entry(row4, textvariable=self.var_csv_path, width=32).grid(row=0, column=3, sticky=tk.W)
        ttk.Label(row4, text="config.yaml:").grid(row=1, column=0, sticky=tk.W, pady=(6,0))
        self.var_config_path = tk.StringVar(value=self.config_path)
        ttk.Entry(row4, textvariable=self.var_config_path, width=52).grid(row=1, column=1, sticky=tk.W, pady=(6,0))
        ttk.Button(row4, text="Laden", command=self._choose_config).grid(row=1, column=2, padx=6, pady=(6,0))
        ttk.Label(row4, text="patterns.yaml:").grid(row=2, column=0, sticky=tk.W, pady=(6,0))
        self.var_patterns_path = tk.StringVar(value=self.patterns_path)
        ttk.Entry(row4, textvariable=self.var_patterns_path, width=52).grid(row=2, column=1, sticky=tk.W, pady=(6,0))
        ttk.Button(row4, text="Laden", command=self._choose_patterns).grid(row=2, column=2, padx=6, pady=(6,0))
        # Aktionen
        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, pady=(0,10))
        try:
            self.btn_info = ttk.Button(actions, text="Info", command=self._show_info)
            self.btn_exit = ttk.Button(actions, text="Beenden", command=self._exit_app)
            self.btn_info.pack(side=tk.LEFT, padx=6)
            self.btn_exit.pack(side=tk.LEFT, padx=6)
        except Exception:
            pass
        self.btn_save = ttk.Button(actions, text="Konfig speichern", command=self._save_config)
        self.btn_run = ttk.Button(actions, text="Verarbeiten starten", command=self._run_worker)
        self.btn_stop = ttk.Button(actions, text="Stop", command=self._stop_worker, state=tk.DISABLED)
        self.btn_open_inbox = ttk.Button(actions, text="Ordner öffnen", command=self._open_inbox)
        self.btn_preview = ttk.Button(actions, text="Vorschau laden…", command=self._preview_any_pdf)
        self.btn_save.pack(side=tk.LEFT)
        self.btn_run.pack(side=tk.LEFT, padx=8)
        self.btn_stop.pack(side=tk.LEFT)
        self.btn_open_inbox.pack(side=tk.LEFT, padx=(12, 0))
        self.btn_preview.pack(side=tk.RIGHT)
        # Notebook mit Tabs: Log, Vorschau, Fehler, Rollen, Regex-Tester
        nb = ttk.Notebook(root)
        nb.pack(fill=tk.BOTH, expand=True)
        self.nb = nb
        # Tab: Log
        tab_log = ttk.Frame(nb)
        nb.add(tab_log, text="Log")
        self.progress = ttk.Progressbar(tab_log, mode="determinate", maximum=100, value=0)
        self.progress.pack(fill=tk.X, padx=8, pady=8)
        self.txt = tk.Text(tab_log, wrap="word", height=20)
        self.txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        self.txt.configure(state=tk.DISABLED)
        # Tab: Vorschau
        tab_prev = ttk.Frame(nb)
        nb.add(tab_prev, text="Vorschau")
        prev_top = ttk.Frame(tab_prev)
        prev_top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(prev_top, text="Vorschau-Quelle:").pack(side=tk.LEFT)
        self.var_preview_path = tk.StringVar()
        ttk.Entry(prev_top, textvariable=self.var_preview_path, width=80).pack(side=tk.LEFT, padx=6)
        ttk.Button(prev_top, text="…", command=self._preview_any_pdf).pack(side=tk.LEFT)
        self.preview_txt = tk.Text(tab_prev, wrap="word")
        self.preview_txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.preview_txt.configure(state=tk.NORMAL)
        # Tab: Fehler
        tab_err = ttk.Frame(nb)
        nb.add(tab_err, text="Fehler")
        err_top = ttk.Frame(tab_err)
        err_top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(err_top, text="Liste leeren", command=self._errors_clear).pack(side=tk.RIGHT)
        self.err_tree = ttk.Treeview(tab_err, columns=("file","msg"), show="headings")
        self.err_tree.heading("file", text="Datei")
        self.err_tree.heading("msg", text="Meldung")
        self.err_tree.column("file", width=320)
        self.err_tree.column("msg", width=560)
        self.err_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        # Tab: Rollen
        tab_roles = ttk.Frame(nb)
        nb.add(tab_roles, text="Rollen")
        roles_top = ttk.Frame(tab_roles)
        roles_top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(roles_top, text="Rollen (eine pro Zeile):").pack(side=tk.LEFT)
        btns = ttk.Frame(roles_top)
        btns.pack(side=tk.RIGHT)
        ttk.Button(btns, text="Neu laden", command=self._reload_roles_from_cfg).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Leeren", command=self._clear_roles).pack(side=tk.RIGHT, padx=(0,6))
        roles_body = ttk.Frame(tab_roles)
        roles_body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.roles_text = tk.Text(roles_body, wrap="word")
        self.roles_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        roles_scroll = ttk.Scrollbar(roles_body, orient=tk.VERTICAL, command=self.roles_text.yview)
        roles_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.roles_text.configure(yscrollcommand=roles_scroll.set)
        ttk.Label(
            tab_roles,
            text="Hinweis: Rollen werden beim Speichern in die Konfiguration übernommen.",
        ).pack(anchor=tk.W, padx=8, pady=(0, 8))
        # Tab: Regex-Tester
        tab_rx = ttk.Frame(nb)
        nb.add(tab_rx, text="Regex-Tester")
        rx_top = ttk.Frame(tab_rx)
        rx_top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(rx_top, text="patterns.yaml laden", command=self._load_patterns_for_tester).pack(side=tk.LEFT)
        ttk.Button(rx_top, text="Test ausführen", command=self._run_regex_test).pack(side=tk.LEFT, padx=6)
        self.rx_info = tk.StringVar(value="– noch keine Patterns geladen –")
        ttk.Label(rx_top, textvariable=self.rx_info).pack(side=tk.LEFT, padx=12)
        self.rx_text = tk.Text(tab_rx, wrap="word", height=12)
        self.rx_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        self.rx_result = tk.Text(tab_rx, wrap="word", height=8)
        self.rx_result.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        self.loaded_patterns = None  # cache für Tester

    def _build_menubar(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Konfiguration speichern", command=self._save_config, accelerator="Strg+S")
        file_menu.add_command(label="Konfiguration laden…", command=self._choose_config, accelerator="Strg+O")
        file_menu.add_separator()
        file_menu.add_command(label="Beenden", command=self._exit_app, accelerator="Strg+Q")
        menubar.add_cascade(label="Datei", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Systemcheck", command=self._system_check)
        help_menu.add_command(label="Systeminfo kopieren", command=self._copy_system_info)
        help_menu.add_command(label="Benutzerhandbuch öffnen", command=self._open_user_manual)
        help_menu.add_separator()
        help_menu.add_command(label="Sorter-Diagnose protokollieren", command=self._log_sorter_diagnostics)
        help_menu.add_command(label="Info", command=self._show_info, accelerator="F1")
        menubar.add_cascade(label="Hilfe", menu=help_menu)

        self.config(menu=menubar)
        self.menubar = menubar
    # --------------------------
    # Datei-/Pfad-Dialoge
    # --------------------------
    def _choose_input(self):
        d = filedialog.askdirectory(title="Eingangsordner wählen")
        if d:
            self.var_input.set(d)
    def _choose_output(self):
        d = filedialog.askdirectory(title="Ausgangsordner wählen")
        if d:
            self.var_output.set(d)
    def _choose_tesseract(self):
        f = filedialog.askopenfilename(title="tesseract.exe wählen",
                                       filetypes=[("Programme", "*.exe"), ("Alle Dateien", "*.*")])
        if f:
            self.var_tesseract.set(f)
    def _choose_poppler(self):
        d = filedialog.askdirectory(title="Poppler bin-Ordner wählen")
        if d:
            self.var_poppler.set(d)
    def _choose_config(self):
        f = filedialog.askopenfilename(title="config.yaml wählen",
                                       filetypes=[("YAML", "*.yaml;*.yml"), ("Alle Dateien", "*.*")])
        if f:
            self.var_config_path.set(f)
            self._load_config_silent(f)
    def _choose_patterns(self):
        f = filedialog.askopenfilename(title="patterns.yaml wählen",
                                       filetypes=[("YAML", "*.yaml;*.yml"), ("Alle Dateien", "*.*")])
        if f:
            self.var_patterns_path.set(f)

    def _open_user_manual(self):
        manual_paths = [
            Path(__file__).resolve().parent / "docs" / "benutzerhandbuch.md",
            Path(__file__).resolve().parent / "docs" / "nutzerhandbuch.md",
        ]
        manual_path = next((p for p in manual_paths if p.exists()), None)
        if not manual_path:
            messagebox.showerror("Benutzerhandbuch", "Benutzerhandbuch wurde nicht gefunden.")
            return

        try:
            manual_text = manual_path.read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Benutzerhandbuch", f"Datei konnte nicht gelesen werden: {exc}")
            return

        try:
            self._show_manual_window(manual_path, manual_text)
        except Exception as exc:
            messagebox.showerror("Benutzerhandbuch", f"Fenster konnte nicht geöffnet werden: {exc}")
            return
        self._log("INFO", f"Benutzerhandbuch geöffnet: {manual_path}\n")

    def _show_manual_window(self, manual_path, manual_text):
        if self._manual_window and self._manual_window.winfo_exists():
            try:
                self._manual_window.destroy()
            except Exception:
                pass
            self._manual_window = None

        window = tk.Toplevel(self)
        window.title(f"Benutzerhandbuch – {manual_path.name}")
        window.geometry("900x720")
        window.minsize(600, 400)
        window.transient(self)
        window.lift()
        window.focus_set()
        container = ttk.Frame(window, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text="Benutzerhandbuch", font=("TkDefaultFont", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(
            header,
            text="Extern öffnen",
            command=lambda p=manual_path: self._open_manual_external(p),
        ).pack(side=tk.RIGHT)

        location = ttk.Label(container, text=f"Quelle: {manual_path}")
        location.pack(fill=tk.X, anchor=tk.W, pady=(0, 8))

        ttk.Separator(container).pack(fill=tk.X, pady=(0, 8))

        text_frame = ttk.Frame(container)
        text_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL)
        text_widget = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
        scrollbar.config(command=text_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        text_widget.insert("1.0", manual_text.replace("\r\n", "\n"))
        text_widget.configure(state=tk.DISABLED)

        def _close_manual():
            try:
                window.destroy()
            finally:
                if self._manual_window is window:
                    self._manual_window = None

        window.protocol("WM_DELETE_WINDOW", _close_manual)
        self._manual_window = window

    def _open_manual_external(self, manual_path):
        if not manual_path.exists():
            messagebox.showerror("Benutzerhandbuch", "Datei wurde nicht gefunden.")
            return

        try:

            if sys.platform.startswith("win"):
                os.startfile(str(manual_path))
                result_code = 0
            else:
                cmd = ["open", str(manual_path)] if sys.platform == "darwin" else ["xdg-open", str(manual_path)]
                completed = subprocess.run(cmd, check=False)
                result_code = completed.returncode
            if result_code not in (0, None):
                raise RuntimeError(f"Rückgabecode {result_code}")
            self._log("INFO", f"Benutzerhandbuch geöffnet: {manual_path}\n")
        except Exception as exc:
            messagebox.showerror("Benutzerhandbuch", f"Datei konnte nicht geöffnet werden: {exc}")

    def _open_inbox(self):
        path_value = (self.var_input.get() or "").strip()
        if not path_value:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Eingangsordner konfigurieren.")
            return

        folder = Path(path_value).expanduser()
        if not folder.is_absolute():
            folder = Path.cwd() / folder

        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror("Fehler", f"Eingangsordner konnte nicht erstellt werden: {exc}")
            return

        folder_str = str(folder.resolve())

        try:
            if sys.platform.startswith("win"):
                os.startfile(folder_str)
                result_code = 0
            else:
                cmd = ["open", folder_str] if sys.platform == "darwin" else ["xdg-open", folder_str]
                completed = subprocess.run(cmd, check=False)
                result_code = completed.returncode
            if result_code not in (0, None):
                raise RuntimeError(f"Rückgabecode {result_code}")
            self._log("INFO", f"Eingangsordner geöffnet: {folder_str}\n")
        except Exception as exc:
            messagebox.showerror("Fehler", f"Ordner konnte nicht geöffnet werden: {exc}")
    # --------------------------
    # Tesseract-Sprachen ermitteln
    # --------------------------
    def _refresh_tess_langs(self):
        cmd = (self.var_tesseract.get() or "").strip() or "tesseract"
        langs = ["deu", "eng", "deu+eng"]
        try:
            p = subprocess.run([cmd, "--list-langs"], capture_output=True, text=True, timeout=8)
            if p.returncode == 0:
                found = []
                for line in p.stdout.splitlines():
                    t = line.strip()
                    if not t or "list of available languages" in t.lower():
                        continue
                    found.append(t)
                if "deu" in found and "eng" in found and "deu+eng" not in found:
                    found.append("deu+eng")
                if found:
                    langs = sorted(set(found), key=str.lower)
        except Exception:
            pass
        self.cmb_tess_lang.configure(values=langs)
        if self.var_tess_lang.get() not in langs:
            self.var_tess_lang.set(langs[0])
        self._log("INFO", f"Sprachen aktualisiert: {', '.join(langs)}\\n")
    # --------------------------
    # Config laden/speichern
    # --------------------------
    def _load_config_silent(self, path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            self.cfg = cfg
            self._cfg_to_vars(cfg)
            self._log("INFO", f"Konfiguration geladen: {path}\\n")
        except Exception as e:
            self._log("WARN", f"Konnte Konfiguration nicht laden: {e}\\n")
    def _cfg_to_vars(self, cfg):
        self.var_input.set(cfg.get("input_dir", ""))
        self.var_output.set(cfg.get("output_dir", ""))
        self.var_unknown.set(cfg.get("unknown_dir_name", "unbekannt"))
        self.var_tesseract.set(cfg.get("tesseract_cmd", ""))
        self.var_poppler.set(cfg.get("poppler_path", ""))
        self.var_use_ocr.set(bool(cfg.get("use_ocr", True)))
        self.var_use_ollama.set(bool(cfg.get("use_ollama", False)))
        self.var_tess_lang.set(cfg.get("tesseract_lang", "deu+eng"))
        oll = cfg.get("ollama", {}) or {}
        self.var_ollama_host.set(oll.get("host", "http://localhost:11434"))
        self.var_ollama_model.set(oll.get("model", "llama3"))
        self.var_dry.set(bool(cfg.get("dry_run", False)))
        if cfg.get("csv_log_path"):
            self.var_csv.set(True)
            self.var_csv_path.set(cfg.get("csv_log_path"))
        self._set_roles_text(cfg.get("roles"))
        fmt = str(
            cfg.get("output_filename_format")
            or self.filename_preset_map[self.default_filename_label]
        )
        label = self.filename_preset_inverse.get(fmt)
        if label:
            self.var_filename_pattern.set(label)
        else:
            self.var_filename_pattern.set(fmt)
        self._update_filename_example()
    def _vars_to_cfg(self):
        cfg = {
            "input_dir": self.var_input.get(),
            "output_dir": self.var_output.get(),
            "unknown_dir_name": self.var_unknown.get() or "unbekannt",
            "tesseract_cmd": self.var_tesseract.get(),
            "poppler_path": self.var_poppler.get(),
            "tesseract_lang": self.var_tess_lang.get() or "deu+eng",
            "use_ocr": bool(self.var_use_ocr.get()),
            "use_ollama": bool(self.var_use_ollama.get()),
            "ollama": {
                "host": self.var_ollama_host.get(),
                "model": self.var_ollama_model.get(),
            },
            "dry_run": bool(self.var_dry.get()),
        }
        fmt = self._resolve_filename_format()
        if fmt:
            cfg["output_filename_format"] = fmt
        if self.var_csv.get():
            cfg["csv_log_path"] = self.var_csv_path.get()
        roles = self._get_roles_from_widget()
        if roles:
            cfg["roles"] = roles
        return cfg

    def _set_roles_text(self, roles):
        if not hasattr(self, "roles_text"):
            return
        self.roles_text.configure(state=tk.NORMAL)
        self.roles_text.delete("1.0", tk.END)
        cleaned = normalize_roles(roles)
        if cleaned:
            self.roles_text.insert("1.0", "\n".join(cleaned) + "\n")
        self.roles_text.edit_modified(False)

    def _get_roles_from_widget(self):
        if not hasattr(self, "roles_text"):
            return []
        content = self.roles_text.get("1.0", tk.END)
        return normalize_roles(content.splitlines())
    def _resolve_filename_format(self):
        selected = (self.var_filename_pattern.get() or "").strip()
        if not selected:
            return self.filename_preset_map.get(self.default_filename_label, "")
        return self.filename_preset_map.get(selected, selected)
    def _update_filename_example(self):
        fmt = self._resolve_filename_format() or self.filename_preset_map.get(
            self.default_filename_label, ""
        )
        try:
            sample = fmt.format(
                date=datetime.now().strftime("%Y-%m-%d"),
                supplier="Lieferant",
                invoice_no="RE-12345",
                original_name="Originaldatei",
            )
        except Exception:
            sample = fmt
        self.var_filename_example.set(f"Beispiel: {sample}")
    def _save_config(self):
        cfg = self._vars_to_cfg()
        path = self.var_config_path.get() or DEFAULT_CONFIG_PATH
        try:
            self.cfg = dict(cfg)
            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
            self._log("INFO", f"Konfiguration gespeichert: {path}\\n")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konfiguration konnte nicht gespeichert werden: {e}")
    # --------------------------
    # Worker-Thread steuern
    # --------------------------
    def _run_worker(self):
        if sorter is None:
            messagebox.showerror("Fehlende Abhängigkeit", "sorter.py konnte nicht importiert werden.")
            return
        if self.worker_thread and self.worker_thread.is_alive():
            return
        # Vor dem Start Config speichern
        self._save_config()
        self.stop_flag.clear()
        self.progress.config(mode="determinate", maximum=100, value=0)
        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        # Streams umleiten
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = TextQueueWriter(self.queue, tag="OUT")
        sys.stderr = TextQueueWriter(self.queue, tag="ERR")
        def stop_fn():
            return self.stop_flag.is_set()
        def progress_fn(i, n, filename, data):
            # an GUI-Thread melden
            self.queue.put(("PROG", (i, n, filename, data)))
        def work():
            try:
                cfg_like = self._vars_to_cfg()
                log_csv = cfg_like.get("csv_log_path")
                used = "fallback"
                if sorter is not None and hasattr(sorter, "process_all"):
                    try:
                        sorter.process_all(self.var_config_path.get(), self.var_patterns_path.get(),
                                           stop_fn=stop_fn, progress_fn=progress_fn)
                        used = "sorter.process_all"
                    except AttributeError:
                        _fallback_process_all(cfg_like, self.var_patterns_path.get(), stop_fn, progress_fn, log_csv)
                        used = "fallback_after_attrerror"
                else:
                    _fallback_process_all(cfg_like, self.var_patterns_path.get(), stop_fn, progress_fn, log_csv)
                    used = "fallback_no_attr"
                self.queue.put(("LOG", ("INFO", f"Verarbeitung beendet (Modus: {used}).\n")))
            except Exception as e:
                self.queue.put(("LOG", ("ERR", f"Laufzeitfehler: {e}\n")))
            finally:
                sys.stdout = self._orig_stdout
                sys.stderr = self._orig_stderr
                self.queue.put(("INFO", "\nVerarbeitung beendet.\n"))
                self.after(0, self._on_worker_done)
        self.worker_thread = threading.Thread(target=work, daemon=True)
        self.worker_thread.start()
    def _stop_worker(self):
        self.stop_flag.set()
        self._log("INFO", "Stop angefordert – wird nach aktueller Datei beendet.\\n")
    def _on_worker_done(self):
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
    def _select_tab(self, index):
        try:
            self.nb.select(index)
        except Exception:
            pass
    def _reload_roles_from_cfg(self):
        roles = []
        if isinstance(self.cfg, dict):
            roles = normalize_roles(self.cfg.get("roles") or [])
        self._set_roles_text(roles)
        self._log("INFO", "Rollen aus Konfiguration übernommen.\\n")
    def _clear_roles(self):
        if hasattr(self, "roles_text"):
            self.roles_text.delete("1.0", tk.END)
            self.roles_text.edit_modified(False)
    # --------------------------
    # Log & Tabs
    # --------------------------
    def _log(self, tag, msg):
        self.txt.configure(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt.insert(tk.END, f"[{timestamp}] {tag}: {msg}")
        self.txt.see(tk.END)
        self.txt.configure(state=tk.DISABLED)
    def _poll_queue(self):
        try:
            while True:
                tag, payload = self.queue.get_nowait()
                if tag == "PROG":
                    i, n, filename, data = payload
                    pct = int(i / max(n, 1) * 100)
                    self.progress.config(value=pct, maximum=100)
                    # robuste Prüfung: data kann None sein
                    inv = getattr(data, "invoice_no", None) if data else None
                    sup = getattr(data, "supplier", None) if data else None
                    dt  = getattr(data, "invoice_date", None) if data else None
                    status = getattr(data, "validation_status", None) if data else None
                    if (data is None) or (not inv or not sup or not dt) or (status in ("fail", "needs_review")):
                        self._errors_add(filename, "Unvollständige Daten oder Validierungsproblem.")
                elif tag == "LOG":
                    level, message = payload
                    self._log(level, message)
                    if level in ("ERR",) and isinstance(message, str):
                        self._errors_add("(unbekannt)", message.strip())
                else:
                    # normale Log-Zeile
                    self._log(tag, payload)
                    # Erkenne Fehlerzeilen und füge sie hinzu
                    if tag in ("ERR",) and isinstance(payload, str):
                        self._errors_add("(unbekannt)", payload.strip())
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)
    # --------------------------
    # Vorschau
    # --------------------------
    def _preview_any_pdf(self):
        if sorter is None:
            messagebox.showerror("Fehlende Abhängigkeit", "sorter.py konnte nicht importiert werden.")
            return
        path = filedialog.askopenfilename(title="PDF für Vorschau wählen",
                                          filetypes=[("PDF", "*.pdf"), ("Alle Dateien", "*.*")])
        if not path:
            return
        self.var_preview_path.set(path)
        text = ""
        try:
            cfg_like = self._vars_to_cfg()
            # benutze die Extraktionsfunktion aus sorter (liefert (text, method))
            text, _method = sorter.extract_text_from_pdf(
                path,
                use_ocr=cfg_like.get("use_ocr", True),
                poppler_path=cfg_like.get("poppler_path"),
                tesseract_cmd=cfg_like.get("tesseract_cmd"),
                tesseract_lang=cfg_like.get("tesseract_lang", "deu+eng"),
            )
        except Exception as e:
            text = f"[Fehler bei Vorschau] {e}"
        self.preview_txt.configure(state=tk.NORMAL)
        self.preview_txt.delete("1.0", tk.END)
        self.preview_txt.insert(tk.END, text[:10000])
        self.preview_txt.see("1.0")
    # --------------------------
    # Fehlerliste
    # --------------------------
    def _errors_add(self, filename: str, msg: str):
        self.error_rows.append({"file": filename, "msg": msg})
        self.err_tree.insert("", tk.END, values=(filename, msg))
    def _errors_clear(self):
        self.error_rows.clear()
        for i in self.err_tree.get_children():
            self.err_tree.delete(i)
    # --------------------------
    # Regex-Tester
    # --------------------------
    def _load_patterns_for_tester(self):
        try:
            with open(self.var_patterns_path.get(), "r", encoding="utf-8") as fh:
                pats = yaml.safe_load(fh) or {}
            self.loaded_patterns = pats
            invn = len(pats.get("invoice_number_patterns", []))
            datn = len(pats.get("date_patterns", []))
            supp = len(pats.get("supplier_hints", {}) or {})
            self.rx_info.set(f"Geladen – Rechnungsnr: {invn}, Datumsregex: {datn}, Lieferanten: {supp}")
            self._log("INFO", "Regex-Patterns für Tester geladen.\\n")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte patterns.yaml nicht laden: {e}")
    def _run_regex_test(self):
        if sorter is None:
            messagebox.showerror("Fehlende Abhängigkeit", "sorter.py konnte nicht importiert werden.")
            return
        sample = self.rx_text.get("1.0", tk.END)
        if not sample.strip():
            messagebox.showinfo("Hinweis", "Bitte Beispieltext in das obere Feld einfügen.")
            return
        if not getattr(self, "loaded_patterns", None):
            self._load_patterns_for_tester()
            if not getattr(self, "loaded_patterns", None):
                return
        try:
            pats = self.loaded_patterns
            inv = sorter.extract_invoice_no(sample, pats.get("invoice_number_patterns", []))
            dt_iso = sorter.extract_date(sample, pats.get("date_patterns", []))  # ISO-String oder None
            sup = sorter.detect_supplier(sample, pats.get("supplier_hints", {}))
            res = []
            res.append(f"Rechnungsnummer: {inv}")
            res.append(f"Datum: {dt_iso if dt_iso else None}")
            res.append(f"Lieferant: {sup}")
            self.rx_result.delete("1.0", tk.END)
            self.rx_result.insert(tk.END, "\\n".join(res))
        except Exception as e:
            self.rx_result.delete("1.0", tk.END)
            self.rx_result.insert(tk.END, f"Fehler beim Test: {e}")
    # --------------------------
    # Systemcheck (Hilfe-Menü)
    # --------------------------
    def _system_check(self):
        import sys, shutil, platform, subprocess, os
        lines = []
        def add(k, v):
            lines.append(f"{k}: {v}")
        def try_import(mod, pipname=None):
            try:
                m = __import__(mod)
                ver = getattr(m, "__version__", None)
                return True, ver
            except Exception as e:
                return False, str(e)
        add("Python", sys.version.split()[0])
        add("Interpreter", sys.executable)
        # Module prüfen
        mods = [
            ("yaml", "pyyaml"),
            ("fitz", "pymupdf"),
            ("PyPDF2", "PyPDF2"),
            ("pdf2image", "pdf2image"),
            ("pytesseract", "pytesseract"),
            ("PIL", "pillow"),
        ]
        missing = []
        lines.append("")
        lines.append("Python-Module:")
        for mod, pipname in mods:
            ok, info = try_import(mod, pipname)
            if ok:
                ver = info or "(ohne __version__)"
                lines.append(f"  - {pipname or mod:12s}  OK  {ver}")
            else:
                lines.append(f"  - {pipname or mod:12s}  FEHLT  ({info})")
                missing.append(pipname or mod)
        # Tesseract
        lines.append("")
        lines.append("Tesseract:")
        tess_cmd = (self.var_tesseract.get() or "tesseract").strip()
        try:
            p = subprocess.run([tess_cmd, "--version"], capture_output=True, text=True, timeout=8)
            if p.returncode == 0:
                first = (p.stdout or p.stderr).splitlines()[0] if (p.stdout or p.stderr) else ""
                lines.append(f"  - {tess_cmd}  OK  {first}")
                # optional: Sprachen
                try:
                    p2 = subprocess.run([tess_cmd, "--list-langs"], capture_output=True, text=True, timeout=8)
                    langs = [ln.strip() for ln in (p2.stdout or "").splitlines() if ln.strip() and "list of available languages" not in ln.lower()]
                    if langs:
                        lines.append(f"  - Sprachen: {', '.join(langs[:10])}" + (" …" if len(langs) > 10 else ""))
                except Exception:
                    pass
            else:
                lines.append(f"  - {tess_cmd}  PROBLEM  (exit {p.returncode})")
        except FileNotFoundError:
            lines.append(f"  - {tess_cmd}  FEHLT (Datei nicht gefunden)")
        except Exception as e:
            lines.append(f"  - {tess_cmd}  FEHLER  ({e})")
        # Poppler
        lines.append("")
        lines.append("Poppler:")
        pop_bin = (self.var_poppler.get() or "").strip()
        def which(cmd, extra_path=None):
            if extra_path and os.path.isdir(extra_path):
                cand = os.path.join(extra_path, cmd)
                if os.name == "nt":
                    if os.path.isfile(cand) or os.path.isfile(cand + ".exe"):
                        return cand if os.path.isfile(cand) else cand + ".exe"
                else:
                    if os.path.isfile(cand) and os.access(cand, os.X_OK):
                        return cand
            return shutil.which(cmd)
        pdftoppm = which("pdftoppm", pop_bin) or which("pdftoppm")
        pdftocairo = which("pdftocairo", pop_bin) or which("pdftocairo")
        if pdftoppm:
            try:
                p = subprocess.run([pdftoppm, "-v"], capture_output=True, text=True, timeout=8)
                ver = (p.stderr or p.stdout).splitlines()[0] if (p.stderr or p.stdout) else ""
                lines.append(f"  - pdftoppm  OK  {ver}")
            except Exception as e:
                lines.append(f"  - pdftoppm  FEHLER  ({e})")
        else:
            lines.append("  - pdftoppm  FEHLT")
        if pdftocairo:
            try:
                p = subprocess.run([pdftocairo, "-v"], capture_output=True, text=True, timeout=8)
                ver = (p.stderr or p.stdout).splitlines()[0] if (p.stderr or p.stdout) else ""
                lines.append(f"  - pdftocairo  OK  {ver}")
            except Exception as e:
                lines.append(f"  - pdftocairo  FEHLER  ({e})")
        else:
            lines.append("  - pdftocairo  FEHLT")
        # Ergebnis darstellen
        out = "\n".join(lines)
        self._last_systemcheck = out
        # in Log schreiben
        try:
            self._log("CHECK", out + "\\n")
        except Exception:
            pass
        # Messagebox – Fehler/OK
        title = "Systemcheck"
        try:
            import tkinter as _tk
            from tkinter import messagebox as _msg
            if missing:
                _msg.showwarning(title, out + "\\n\\nEmpfehlung:\\n  pip install " + " ".join(missing))
            else:
                _msg.showinfo(title, out)
        except Exception:
            print(out)
    def _copy_system_info(self):
        try:
            data = getattr(self, "_last_systemcheck", None)
            if not data:
                # einmal ausführen, um Daten zu erzeugen
                self._system_check()
                data = getattr(self, "_last_systemcheck", "")
            self.clipboard_clear()
            self.clipboard_append(data or "")
            self._log("INFO", "Systeminfo in Zwischenablage kopiert.\n")
        except Exception as e:
            self._log("ERR", f"Konnte Systeminfo nicht kopieren: {e}\n")

    # --------------------------
    # Sorter-Diagnose
    # --------------------------
    def _log_sorter_diagnostics(self):
        try:
            mod = sorter
            if mod is None:
                self._log("CHECK", "Sorter: NICHT importiert (sorter == None)\n")
                return
            path = getattr(mod, "__file__", "(unbekannt)")
            has_analyze = hasattr(mod, "analyze_pdf")
            has_process = hasattr(mod, "process_pdf")
            has_all     = hasattr(mod, "process_all")
            has_extract = hasattr(mod, "extract_text_from_pdf")
            self._log("CHECK", f"Sorter geladen aus: {path}\n")
            self._log("CHECK", "Funktionen: "
                               f"analyze_pdf={'Ja' if has_analyze else 'Nein'}, "
                               f"process_pdf={'Ja' if has_process else 'Nein'}, "
                               f"process_all={'Ja' if has_all else 'Nein'}, "
                               f"extract_text_from_pdf={'Ja' if has_extract else 'Nein'}\n")
        except Exception as e:
            self._log("ERR", f"Sorter-Diagnose fehlgeschlagen: {e}\n")


    # --------------------------
    # Ordner-Autocreate (beim Start)
    # --------------------------
    def _ensure_dirs(self):
        from pathlib import Path as _P
        try:
            # Eingangs-/Ausgangsordner (GUI-Config)
            in_dir = self.var_input.get().strip() or "inbox"
            out_dir = self.var_output.get().strip() or "processed"
            unk = self.var_unknown.get().strip() or "unbekannt"
            self.var_input.set(in_dir)
            self.var_output.set(out_dir)
            self.var_unknown.set(unk)
            _P(in_dir).mkdir(parents=True, exist_ok=True)
            od = _P(out_dir)
            od.mkdir(parents=True, exist_ok=True)
            (od / unk).mkdir(parents=True, exist_ok=True)

            # CSV-Ordner (falls aktiviert)
            if hasattr(self, "var_csv") and bool(self.var_csv.get()):
                p = self.var_csv_path.get().strip()
                if p:
                    _P(p).parent.mkdir(parents=True, exist_ok=True)
            else:
                _P("logs").mkdir(parents=True, exist_ok=True)

            # Hotfolder-Defaults (falls leer)
            if not self.var_inbox.get().strip():
                self.var_inbox.set(str(_P("inbox").resolve()))
            if not self.var_done.get().strip():
                self.var_done.set(str(_P("processed").resolve()))
            if not self.var_err.get().strip():
                self.var_err.set(str(_P("error").resolve()))

            # Hotfolder-Ordner anlegen (schadet nicht)
            _P(self.var_inbox.get()).mkdir(parents=True, exist_ok=True)
            _P(self.var_done.get()).mkdir(parents=True, exist_ok=True)
            _P(self.var_err.get()).mkdir(parents=True, exist_ok=True)

            self._log("INFO", "Ordner geprüft/angelegt (inbox/processed/error/logs etc.).\n")
        except Exception as e:
            self._log("ERR", f"Ordner-Autocreate fehlgeschlagen: {e}\n")

    # --------------------------
    # Info & Exit (eingefügt)
    # --------------------------
    def _show_info(self):
        title = "PDF Rechnung Changer — Info"
        text = ("Toolname: PDF Rechnung Changer\n"
                "Autor: Markus Dickscheit\n\n"
                "Opensource zur freien Verwendung aber auf eigene Gefahr")
        try:
            messagebox.showinfo(title, text)
        except Exception:
            print(title + "\n" + text)
    def _exit_app(self):
        try:
            if hasattr(self, "stop_flag") and self.stop_flag:
                try: self.stop_flag.set()
                except Exception: pass
            if hasattr(self, "hot") and self.hot:
                try: self.hot.stop()
                except Exception: pass
        finally:
            try:
                self.destroy()
            except Exception:
                import os
                os._exit(0)
if __name__ == "__main__":
    app = App()
    app.mainloop()