
import os
import sys
import io
import threading
import queue
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import yaml
from datetime import datetime

# Importiere die vorhandene Logik aus sorter.py (erweiterte Version mit Callbacks)
try:
    import sorter  # benötigt process_all(..., stop_fn, progress_fn) und Extraktions-Helpers
except Exception as e:
    sorter = None

APP_TITLE = "Invoice Sorter – GUI"
DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_PATTERNS_PATH = "patterns.yaml"

class TextQueueWriter(io.TextIOBase):
    """Leitet stdout/stderr-Text in eine Queue, damit das GUI Logs anzeigen kann."""
    def __init__(self, q: queue.Queue, tag: str = "INFO"):
        super().__init__()
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

        self.queue = queue.Queue()
        self.worker_thread = None
        self.stop_flag = threading.Event()

        self.cfg = {}
        self.config_path = DEFAULT_CONFIG_PATH
        self.patterns_path = DEFAULT_PATTERNS_PATH

        # für Fehlerliste
        self.error_rows = []  # List[dict]

        self._build_ui()
        self._load_config_silent(self.config_path)
        self._poll_queue()

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
        self.btn_save = ttk.Button(actions, text="Konfig speichern", command=self._save_config)
        self.btn_run = ttk.Button(actions, text="Verarbeiten starten", command=self._run_worker)
        self.btn_stop = ttk.Button(actions, text="Stop", command=self._stop_worker, state=tk.DISABLED)
        self.btn_preview = ttk.Button(actions, text="Vorschau laden…", command=self._preview_any_pdf)
        self.btn_save.pack(side=tk.LEFT)
        self.btn_run.pack(side=tk.LEFT, padx=8)
        self.btn_stop.pack(side=tk.LEFT)
        self.btn_preview.pack(side=tk.RIGHT)

        # Notebook mit Tabs: Log, Vorschau, Fehler, Regex-Tester
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
        if self.var_csv.get():
            cfg["csv_log_path"] = self.var_csv_path.get()
        return cfg

    def _save_config(self):
        cfg = self._vars_to_cfg()
        path = self.var_config_path.get() or DEFAULT_CONFIG_PATH
        try:
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
                sorter.process_all(self.var_config_path.get(), self.var_patterns_path.get(),
                                   stop_fn=stop_fn, progress_fn=progress_fn)
            except Exception as e:
                self._log("ERR", f"Laufzeitfehler: {e}\\n")
            finally:
                sys.stdout = self._orig_stdout
                sys.stderr = self._orig_stderr
                self.queue.put(("INFO", "\\nVerarbeitung beendet.\\n"))
                self.after(0, self._on_worker_done)

        self.worker_thread = threading.Thread(target=work, daemon=True)
        self.worker_thread.start()

    def _stop_worker(self):
        self.stop_flag.set()
        self._log("INFO", "Stop angefordert – wird nach aktueller Datei beendet.\\n")

    def _on_worker_done(self):
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

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

if __name__ == "__main__":
    app = App()
    app.mainloop()
