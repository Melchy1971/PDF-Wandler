import os
import sys
import io
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import yaml
from datetime import datetime

# Importiere die vorhandene Logik aus sorter.py
try:
    import sorter  # nutzt process_all(...) und die übrige Logik
except Exception as e:
    sorter = None

APP_TITLE = "Invoice Sorter – GUI"
DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_PATTERNS_PATH = "patterns.yaml"

class TextQueueWriter(io.TextIOBase):
    """Leitet .write()-Aufrufe in eine Queue um, damit das GUI die Logs anzeigen kann."""
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
        self.geometry("900x680")
        self.minsize(840, 600)

        self.queue = queue.Queue()
        self.worker_thread = None
        self.stop_flag = threading.Event()

        self.cfg = {}
        self.config_path = DEFAULT_CONFIG_PATH
        self.patterns_path = DEFAULT_PATTERNS_PATH

        self._build_ui()
        self._load_config_silent(self.config_path)
        self._poll_queue()

    # --------------------------
    # UI Aufbau
    # --------------------------
    def _build_ui(self):
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Konfigurationsbereich
        cfg_frame = ttk.LabelFrame(root, text="Konfiguration")
        cfg_frame.pack(fill=tk.X, padx=0, pady=(0, 10))

        # Zeile 1: input/output
        self.var_input = tk.StringVar()
        self.var_output = tk.StringVar()
        self.var_unknown = tk.StringVar(value="unbekannt")

        row1 = ttk.Frame(cfg_frame)
        row1.pack(fill=tk.X, pady=6)
        ttk.Label(row1, text="Eingangsordner:").grid(row=0, column=0, sticky=tk.W)
        e_in = ttk.Entry(row1, textvariable=self.var_input, width=70)
        e_in.grid(row=0, column=1, sticky=tk.W)
        ttk.Button(row1, text="Wählen", command=self._choose_input).grid(row=0, column=2, padx=6)

        ttk.Label(row1, text="Ausgangsordner:").grid(row=1, column=0, sticky=tk.W, pady=(6,0))
        e_out = ttk.Entry(row1, textvariable=self.var_output, width=70)
        e_out.grid(row=1, column=1, sticky=tk.W, pady=(6,0))
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

        ttk.Label(row2, text="Tesseract Sprache (z.B. deu+eng):").grid(row=3, column=0, sticky=tk.W, pady=(6,0))
        self.var_tess_lang = tk.StringVar(value="deu+eng")
        ttk.Entry(row2, textvariable=self.var_tess_lang, width=30).grid(row=3, column=1, sticky=tk.W, pady=(6,0))

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

        # Aktions-Buttons
        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, pady=(0,10))
        self.btn_save = ttk.Button(actions, text="Konfig speichern", command=self._save_config)
        self.btn_run = ttk.Button(actions, text="Verarbeiten starten", command=self._run_worker)
        self.btn_stop = ttk.Button(actions, text="Stop", command=self._stop_worker, state=tk.DISABLED)
        self.btn_save.pack(side=tk.LEFT)
        self.btn_run.pack(side=tk.LEFT, padx=8)
        self.btn_stop.pack(side=tk.LEFT)

        # Fortschritt + Log
        progress_frame = ttk.LabelFrame(root, text="Fortschritt & Log")
        progress_frame.pack(fill=tk.BOTH, expand=True)

        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=100, value=0)
        self.progress.pack(fill=tk.X, padx=8, pady=8)

        self.txt = tk.Text(progress_frame, wrap="word", height=18)
        self.txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))
        self.txt.configure(state=tk.DISABLED)

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
    # Config laden/speichern
    # --------------------------
    def _load_config_silent(self, path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            self.cfg = cfg
            self._cfg_to_vars(cfg)
            self._log("INFO", f"Konfiguration geladen: {path}")
        except Exception as e:
            self._log("WARN", f"Konnte Konfiguration nicht laden: {e}")

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
            self._log("INFO", f"Konfiguration gespeichert: {path}")
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
            # An GUI-Thread melden
            self.queue.put(("PROG", (i, n, filename)))

        def work():
            try:
                sorter.process_all(self.var_config_path.get(), self.var_patterns_path.get(),
                                   stop_fn=stop_fn, progress_fn=progress_fn)
            except Exception as e:
                self._log("ERR", f"Laufzeitfehler: {e}")
            finally:
                sys.stdout = self._orig_stdout
                sys.stderr = self._orig_stderr
                self.queue.put(("INFO", "Verarbeitung beendet."))
                self.after(0, self._on_worker_done)

        self.worker_thread = threading.Thread(target=work, daemon=True)
        self.worker_thread.start()

    def _stop_worker(self):
        self.stop_flag.set()
        self._log("INFO", "Stop angefordert – wird nach aktuellem Schritt beendet.")

    def _on_worker_done(self):
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    # --------------------------
    # Log-Anzeige
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
                    i, n, filename = payload
                    pct = int(i / max(n, 1) * 100)
                    self.progress.config(value=pct, maximum=100)
                else:
                    self._log(tag, payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

if __name__ == "__main__":
    app = App()
    app.mainloop()