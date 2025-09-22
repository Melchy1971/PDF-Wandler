 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/gui_app.py b/gui_app.py
index 07ca086e47c63c44683e2b45d94c5523668032a4..cb93c844de83ae4a303cb8b509231da51367caaa 100644
--- a/gui_app.py
+++ b/gui_app.py
@@ -1,122 +1,249 @@
 
 import os
 import sys
 import io
 import threading
 import queue
 import subprocess
+import shutil
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
 
 if sorter is not None and hasattr(sorter, "DEFAULT_OUTPUT_FILENAME_FORMAT"):
     DEFAULT_FILENAME_FMT = sorter.DEFAULT_OUTPUT_FILENAME_FORMAT
 else:
     DEFAULT_FILENAME_FMT = "{date}_{supplier_safe}_Re-{date}"
 
+CUSTOM_FILENAME_LABEL = "Benutzerdefiniert"
+DEFAULT_FILENAME_FORMAT_PRESETS = (
+    {
+        "label": "Standard (Datum_Lieferant)",
+        "pattern": DEFAULT_FILENAME_FMT,
+    },
+    {
+        "label": "Datum_Lieferant_Rechnungsnummer",
+        "pattern": "{date}_{supplier_safe}_Re-{invoice_no_safe}",
+    },
+    {
+        "label": "Lieferant_Rechnungsnummer",
+        "pattern": "{supplier_safe}_Re-{invoice_no_safe}",
+    },
+    {
+        "label": "Lieferant_Datum_Betrag",
+        "pattern": "{supplier_safe}_{date}_{gross}",
+    },
+    {
+        "label": "Datum_Originalname_Hash",
+        "pattern": "{date}_{original_name_safe}_{hash_short}",
+    },
+)
+
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
+        self.protocol("WM_DELETE_WINDOW", self._exit_app)
+        self.after(0, self._maximize_on_start)
 
         self.queue = queue.Queue()
         self.worker_thread = None
         self.stop_flag = threading.Event()
+        self._ollama_install_thread = None
+        self._ollama_install_supported = True
 
         self.cfg = {}
         self.config_path = DEFAULT_CONFIG_PATH
         self.patterns_path = DEFAULT_PATTERNS_PATH
 
         # für Fehlerliste
         self.error_rows = []  # List[dict]
 
         self._build_ui()
+        self._ollama_install_supported = self._build_ollama_install_command() is not None
+        if not self._ollama_install_supported:
+            self.btn_install_ollama.config(state=tk.DISABLED)
+            self.var_ollama_status.set(
+                "Automatische Installation wird auf diesem System nicht unterstützt."
+            )
         self._load_config_silent(self.config_path)
+        self.after(400, lambda: self._check_ollama_status(quiet=True))
         self._poll_queue()
 
     # --------------------------
     # UI Aufbau
     # --------------------------
+    def _maximize_on_start(self):
+        """Versucht das Fenster plattformabhängig maximiert zu starten."""
+        applied = False
+
+        try:
+            self.state("zoomed")
+            applied = self.state() == "zoomed"
+        except tk.TclError:
+            applied = False
+
+        if not applied:
+            try:
+                self.attributes("-zoomed", True)
+                applied = self.state() == "zoomed"
+            except tk.TclError:
+                applied = False
+
+        if not applied:
+            self.update_idletasks()
+            screen_w = self.winfo_screenwidth()
+            screen_h = self.winfo_screenheight()
+            self.geometry(f"{screen_w}x{screen_h}+0+0")
+
     def _build_ui(self):
         root = ttk.Frame(self)
         root.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
 
+        main_area = ttk.Frame(root)
+        main_area.pack(fill=tk.BOTH, expand=True)
+
+        left_column = ttk.Frame(main_area)
+        left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
+
+        info_column = ttk.Frame(main_area)
+        info_column.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))
+
+        info_frame = ttk.LabelFrame(info_column, text="Tool-Info")
+        info_frame.pack(fill=tk.X, anchor=tk.N)
+        info_text = (
+            "Name: PDF Rechnungs Changer\n"
+            "Autor: Markus Dickscheit\n"
+            "Open Source Verwendung auf eigene Gefahr"
+        )
+        ttk.Label(info_frame, text=info_text, justify=tk.LEFT, wraplength=220).pack(
+            fill=tk.X, padx=8, pady=8
+        )
+
+        # System-/Ollama-Konfiguration
+        system_frame = ttk.LabelFrame(info_column, text="System-Konfiguration")
+        system_frame.pack(fill=tk.X, anchor=tk.N, pady=(12, 0))
+        ttk.Label(system_frame, text="Ollama-Integration:").pack(
+            anchor=tk.W, padx=8, pady=(8, 0)
+        )
+        self.var_ollama_status = tk.StringVar(value="Status unbekannt")
+        ttk.Label(
+            system_frame,
+            textvariable=self.var_ollama_status,
+            justify=tk.LEFT,
+            wraplength=220,
+        ).pack(fill=tk.X, padx=8, pady=(4, 8))
+        ollama_btn_row = ttk.Frame(system_frame)
+        ollama_btn_row.pack(fill=tk.X, padx=8, pady=(0, 8))
+        self.btn_check_ollama = ttk.Button(
+            ollama_btn_row, text="Status prüfen", command=self._check_ollama_status
+        )
+        self.btn_check_ollama.pack(side=tk.LEFT)
+        self.btn_install_ollama = ttk.Button(
+            ollama_btn_row,
+            text="Ollama installieren",
+            command=self._install_ollama,
+        )
+        self.btn_install_ollama.pack(side=tk.LEFT, padx=6)
+        ttk.Label(
+            system_frame,
+            text="Hinweis: Installation lädt Dateien von ollama.com herunter.",
+            justify=tk.LEFT,
+            wraplength=220,
+        ).pack(fill=tk.X, padx=8, pady=(0, 8))
+
         # Konfiguration
-        cfg_frame = ttk.LabelFrame(root, text="Konfiguration")
+        cfg_frame = ttk.LabelFrame(left_column, text="Konfiguration")
         cfg_frame.pack(fill=tk.X, padx=0, pady=(0, 10))
 
         # Zeile 1: input/output
         self.var_input = tk.StringVar()
         self.var_output = tk.StringVar()
         self.var_unknown = tk.StringVar(value="unbekannt")
         self.var_filename_fmt = tk.StringVar(value=DEFAULT_FILENAME_FMT)
+        self.var_filename_fmt_choice = tk.StringVar(value=CUSTOM_FILENAME_LABEL)
+        self.custom_format_label = CUSTOM_FILENAME_LABEL
+        self.filename_format_presets = []
+        self._updating_filename_format = False
 
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
 
         ttk.Label(row1, text="Dateiname-Muster:").grid(row=3, column=0, sticky=tk.W, pady=(6,0))
-        ttk.Entry(row1, textvariable=self.var_filename_fmt, width=70).grid(row=3, column=1, sticky=tk.W, pady=(6,0))
+        self.cmb_filename_fmt = ttk.Combobox(
+            row1,
+            textvariable=self.var_filename_fmt_choice,
+            width=40,
+            state="readonly",
+        )
+        self.cmb_filename_fmt.grid(row=3, column=1, sticky=tk.W, pady=(6,0))
         ttk.Button(row1, text="Standard", command=self._reset_filename_format).grid(row=3, column=2, padx=6, pady=(6,0))
+        ttk.Label(row1, text="Muster-Vorschau:").grid(row=4, column=0, sticky=tk.W, pady=(6,0))
+        self.entry_filename_fmt = ttk.Entry(row1, textvariable=self.var_filename_fmt, width=70)
+        self.entry_filename_fmt.grid(row=4, column=1, columnspan=2, sticky=tk.W, pady=(6,0))
+        self._set_filename_format_options([], DEFAULT_FILENAME_FMT)
+        self.var_filename_fmt.trace_add("write", self._on_filename_format_var_changed)
+        self.cmb_filename_fmt.bind("<<ComboboxSelected>>", self._on_filename_format_choice)
 
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
 
diff --git a/gui_app.py b/gui_app.py
index 07ca086e47c63c44683e2b45d94c5523668032a4..cb93c844de83ae4a303cb8b509231da51367caaa 100644
--- a/gui_app.py
+++ b/gui_app.py
@@ -134,63 +261,65 @@ class App(tk.Tk):
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
-        actions = ttk.Frame(root)
+        actions = ttk.Frame(left_column)
         actions.pack(fill=tk.X, pady=(0,10))
         self.btn_save = ttk.Button(actions, text="Konfig speichern", command=self._save_config)
         self.btn_run = ttk.Button(actions, text="Verarbeiten starten", command=self._run_worker)
         self.btn_stop = ttk.Button(actions, text="Stop", command=self._stop_worker, state=tk.DISABLED)
         self.btn_preview = ttk.Button(actions, text="Vorschau laden…", command=self._preview_any_pdf)
+        self.btn_exit = ttk.Button(actions, text="Beenden", command=self._exit_app)
         self.btn_save.pack(side=tk.LEFT)
         self.btn_run.pack(side=tk.LEFT, padx=8)
         self.btn_stop.pack(side=tk.LEFT)
-        self.btn_preview.pack(side=tk.RIGHT)
+        self.btn_exit.pack(side=tk.RIGHT)
+        self.btn_preview.pack(side=tk.RIGHT, padx=(0, 8))
 
         # Notebook mit Tabs: Log, Vorschau, Fehler, Regex-Tester
-        nb = ttk.Notebook(root)
+        nb = ttk.Notebook(left_column)
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
 
diff --git a/gui_app.py b/gui_app.py
index 07ca086e47c63c44683e2b45d94c5523668032a4..cb93c844de83ae4a303cb8b509231da51367caaa 100644
--- a/gui_app.py
+++ b/gui_app.py
@@ -239,131 +368,408 @@ class App(tk.Tk):
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
 
     def _reset_filename_format(self):
-        self.var_filename_fmt.set(DEFAULT_FILENAME_FMT)
+        self._set_filename_format_options(None, DEFAULT_FILENAME_FMT)
+
+    def _default_filename_format_presets(self):
+        return [dict(item) for item in DEFAULT_FILENAME_FORMAT_PRESETS]
+
+    def _normalize_filename_format_presets(self, presets_raw):
+        presets = []
+        seen = set()
+
+        def add_entry(label, pattern):
+            if pattern is None:
+                return
+            pattern_str = str(pattern).strip()
+            if not pattern_str:
+                return
+            label_str = str(label).strip() if label is not None else ""
+            if not label_str:
+                label_str = pattern_str
+            key = (label_str, pattern_str)
+            if key in seen:
+                return
+            seen.add(key)
+            presets.append({"label": label_str, "pattern": pattern_str})
+
+        if isinstance(presets_raw, dict):
+            for label, pattern in presets_raw.items():
+                add_entry(label, pattern)
+        elif isinstance(presets_raw, list):
+            for item in presets_raw:
+                if isinstance(item, dict):
+                    label = (
+                        item.get("label")
+                        or item.get("name")
+                        or item.get("title")
+                        or item.get("id")
+                    )
+                    pattern = (
+                        item.get("pattern")
+                        or item.get("format")
+                        or item.get("template")
+                        or item.get("value")
+                    )
+                    add_entry(label, pattern)
+                elif isinstance(item, (list, tuple)) and len(item) >= 2:
+                    add_entry(item[0], item[1])
+                elif isinstance(item, str):
+                    add_entry(item, item)
+        return presets
+
+    def _ensure_custom_label_available(self):
+        values = list(self.cmb_filename_fmt.cget("values") or [])
+        if self.custom_format_label not in values:
+            values.append(self.custom_format_label)
+            self.cmb_filename_fmt.configure(values=values)
+
+    def _get_pattern_for_label(self, label):
+        for preset in self.filename_format_presets:
+            if preset.get("label") == label:
+                return preset.get("pattern")
+        return None
+
+    def _get_label_for_pattern(self, pattern):
+        for preset in self.filename_format_presets:
+            if preset.get("pattern") == pattern:
+                return preset.get("label")
+        return None
+
+    def _set_filename_format_options(self, presets_raw, selected_pattern):
+        if presets_raw is None:
+            presets = [dict(item) for item in self.filename_format_presets]
+        else:
+            presets = self._normalize_filename_format_presets(presets_raw)
+        if not presets:
+            presets = self._default_filename_format_presets()
+        self.filename_format_presets = presets
+        values = [item.get("label", "") for item in presets]
+        if self.custom_format_label not in values:
+            values.append(self.custom_format_label)
+        self.cmb_filename_fmt.configure(values=values)
+
+        pattern = ""
+        if isinstance(selected_pattern, str):
+            pattern = selected_pattern.strip()
+        if not pattern and presets:
+            pattern = presets[0].get("pattern", DEFAULT_FILENAME_FMT)
+        label = self._get_label_for_pattern(pattern)
+        if label is None:
+            label = self.custom_format_label
+        self._updating_filename_format = True
+        self.var_filename_fmt_choice.set(label)
+        self.var_filename_fmt.set(pattern or DEFAULT_FILENAME_FMT)
+        self._updating_filename_format = False
+        if label == self.custom_format_label:
+            self._ensure_custom_label_available()
+
+    def _on_filename_format_choice(self, event=None):
+        if self._updating_filename_format:
+            return
+        label = self.var_filename_fmt_choice.get()
+        pattern = self._get_pattern_for_label(label)
+        if pattern is not None:
+            self._updating_filename_format = True
+            self.var_filename_fmt.set(pattern)
+            self._updating_filename_format = False
+        elif label == self.custom_format_label:
+            self._ensure_custom_label_available()
+
+    def _on_filename_format_var_changed(self, *args):
+        if self._updating_filename_format:
+            return
+        pattern = self.var_filename_fmt.get()
+        label = self._get_label_for_pattern(pattern)
+        self._updating_filename_format = True
+        if label is not None:
+            self.var_filename_fmt_choice.set(label)
+        else:
+            self._ensure_custom_label_available()
+            self.var_filename_fmt_choice.set(self.custom_format_label)
+        self._updating_filename_format = False
+
+    # --------------------------
+    # Ollama-Konfiguration
+    # --------------------------
+    def _detect_ollama_installation(self):
+        executable = shutil.which("ollama")
+        if not executable:
+            return False, "Ollama wurde nicht gefunden."
+        try:
+            result = subprocess.run(
+                [executable, "--version"],
+                capture_output=True,
+                text=True,
+                timeout=5,
+            )
+            if result.returncode == 0:
+                output = (result.stdout or result.stderr or "").strip()
+                if output:
+                    return True, f"Ollama installiert ({output})"
+                return True, "Ollama ist installiert."
+            return True, "Ollama gefunden, Versionsprüfung fehlgeschlagen."
+        except Exception as exc:
+            return True, f"Ollama gefunden, Versionsprüfung fehlgeschlagen: {exc}"
+
+    def _apply_ollama_status(self, installed, text, installing=False):
+        if text:
+            self.var_ollama_status.set(text)
+        else:
+            self.var_ollama_status.set("Status unbekannt")
+        if installing:
+            self.btn_check_ollama.config(state=tk.DISABLED)
+            self.btn_install_ollama.config(state=tk.DISABLED)
+            return
+        self.btn_check_ollama.config(state=tk.NORMAL)
+        if self._ollama_install_supported:
+            self.btn_install_ollama.config(state=tk.DISABLED if installed else tk.NORMAL)
+        else:
+            self.btn_install_ollama.config(state=tk.DISABLED)
+
+    def _check_ollama_status(self, quiet=False):
+        installed, message = self._detect_ollama_installation()
+        info = message or ("Ollama ist installiert." if installed else "Ollama wurde nicht gefunden.")
+        self._apply_ollama_status(installed, info)
+        if not quiet:
+            self._log("INFO", info + "\n")
+        return installed
+
+    def _build_ollama_install_command(self):
+        if sys.platform.startswith("linux") or sys.platform == "darwin":
+            return [
+                "bash",
+                "-lc",
+                "curl -fsSL https://ollama.com/install.sh | sh",
+            ]
+        if os.name == "nt":
+            script = (
+                "$ProgressPreference='SilentlyContinue';"
+                "$installer=Join-Path $env:TEMP 'OllamaSetup.exe';"
+                "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile $installer;"
+                "Start-Process -FilePath $installer -Wait"
+            )
+            return [
+                "powershell",
+                "-NoProfile",
+                "-ExecutionPolicy",
+                "Bypass",
+                "-Command",
+                script,
+            ]
+        return None
+
+    def _install_ollama(self):
+        if self._ollama_install_thread and self._ollama_install_thread.is_alive():
+            messagebox.showinfo("Ollama", "Eine Installation läuft bereits im Hintergrund.")
+            return
+        installed, message = self._detect_ollama_installation()
+        if installed:
+            info_text = message or "Ollama ist bereits installiert."
+            messagebox.showinfo("Ollama", info_text)
+            self._apply_ollama_status(True, info_text)
+            return
+        command = self._build_ollama_install_command()
+        if command is None:
+            self._ollama_install_supported = False
+            self._apply_ollama_status(False, "Automatische Installation wird nicht unterstützt.")
+            messagebox.showinfo(
+                "Ollama",
+                "Die automatische Installation wird auf diesem Betriebssystem nicht unterstützt. Bitte folge den manuellen Anweisungen auf ollama.com.",
+            )
+            return
+        if not messagebox.askyesno(
+            "Ollama installieren",
+            "Soll Ollama jetzt installiert werden? Es wird eine Internetverbindung benötigt und ggf. ein separates Installationsfenster geöffnet.",
+        ):
+            return
+        self._apply_ollama_status(False, "Installation läuft …", installing=True)
+        thread = threading.Thread(
+            target=self._run_ollama_installation_worker,
+            args=(command,),
+            daemon=True,
+        )
+        self._ollama_install_thread = thread
+        thread.start()
+
+    def _run_ollama_installation_worker(self, command):
+        installed = False
+        status_msg = ""
+        try:
+            self.queue.put(("INFO", "Starte Ollama-Installation …\n"))
+            proc = subprocess.Popen(
+                command,
+                stdout=subprocess.PIPE,
+                stderr=subprocess.STDOUT,
+                text=True,
+            )
+            if proc.stdout is not None:
+                for line in proc.stdout:
+                    if line:
+                        self.queue.put(("INFO", f"[ollama] {line}"))
+            return_code = proc.wait()
+            if return_code != 0:
+                raise RuntimeError(f"Installationsprozess endete mit Code {return_code}")
+            installed, status_msg = self._detect_ollama_installation()
+            if not installed:
+                raise RuntimeError(status_msg or "Ollama konnte nach der Installation nicht gefunden werden.")
+        except Exception as exc:
+            installed = False
+            status_msg = f"Ollama Installation fehlgeschlagen: {exc}"
+            self.queue.put(("ERR", status_msg + "\n"))
+        else:
+            if not status_msg:
+                status_msg = "Ollama Installation abgeschlossen."
+            self.queue.put(("INFO", status_msg + "\n"))
+        finally:
+            self.after(0, lambda: self._on_ollama_installation_finished(installed, status_msg))
+
+    def _on_ollama_installation_finished(self, installed, status_msg):
+        self._ollama_install_thread = None
+        if installed:
+            self._apply_ollama_status(True, status_msg or "Ollama ist installiert.")
+        else:
+            fallback_msg = status_msg or "Ollama wurde nicht installiert."
+            self._apply_ollama_status(False, fallback_msg)
 
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
-        fmt = cfg.get("output_filename_format")
-        if fmt:
-            self.var_filename_fmt.set(fmt)
-        else:
-            self.var_filename_fmt.set(DEFAULT_FILENAME_FMT)
+        self._set_filename_format_options(
+            cfg.get("output_filename_formats"),
+            cfg.get("output_filename_format"),
+        )
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
         fmt = (self.var_filename_fmt.get() or "").strip()
         cfg["output_filename_format"] = fmt or DEFAULT_FILENAME_FMT
+        if self.filename_format_presets:
+            presets_out = []
+            seen = set()
+            for item in self.filename_format_presets:
+                label = str(item.get("label", "")).strip()
+                pattern = str(item.get("pattern", "")).strip()
+                if not pattern:
+                    continue
+                if not label:
+                    label = pattern
+                key = (label, pattern)
+                if key in seen:
+                    continue
+                seen.add(key)
+                presets_out.append({"label": label, "pattern": pattern})
+            if presets_out:
+                cfg["output_filename_formats"] = presets_out
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
diff --git a/gui_app.py b/gui_app.py
index 07ca086e47c63c44683e2b45d94c5523668032a4..cb93c844de83ae4a303cb8b509231da51367caaa 100644
--- a/gui_app.py
+++ b/gui_app.py
@@ -388,50 +794,61 @@ class App(tk.Tk):
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
 
+    def _exit_app(self):
+        if self.worker_thread and self.worker_thread.is_alive():
+            should_exit = messagebox.askyesno(
+                "Verarbeitung läuft",
+                "Die Verarbeitung läuft noch. Möchten Sie die Anwendung trotzdem beenden?",
+            )
+            if not should_exit:
+                return
+            self.stop_flag.set()
+        self.destroy()
+
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
 
EOF
)