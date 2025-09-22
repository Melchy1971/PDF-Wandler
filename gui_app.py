import io
import os
import sys
import queue
import shutil
import threading
import subprocess
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import yaml

try:
    import sorter
except Exception:  # pragma: no cover - optional when CLI only
    sorter = None

APP_TITLE = "Invoice Sorter – GUI"
DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_PATTERNS_PATH = "patterns.yaml"

if sorter is not None and hasattr(sorter, "DEFAULT_OUTPUT_FILENAME_FORMAT"):
    DEFAULT_FILENAME_FMT = sorter.DEFAULT_OUTPUT_FILENAME_FORMAT
else:
    DEFAULT_FILENAME_FMT = "{date}_{supplier_safe}_Re-{date}"

CUSTOM_FILENAME_LABEL = "Benutzerdefiniert"
DEFAULT_FILENAME_FORMAT_PRESETS = (
    {"label": "Standard (Datum_Lieferant)", "pattern": DEFAULT_FILENAME_FMT},
    {"label": "Datum_Lieferant_Rechnungsnummer", "pattern": "{date}_{supplier_safe}_Re-{invoice_no_safe}"},
    {"label": "Lieferant_Rechnungsnummer", "pattern": "{supplier_safe}_Re-{invoice_no_safe}"},
    {"label": "Lieferant_Datum_Betrag", "pattern": "{supplier_safe}_{date}_{gross}"},
    {"label": "Datum_Originalname_Hash", "pattern": "{date}_{original_name_safe}_{hash_short}"},
)


class TextQueueWriter(io.TextIOBase):
    """Forward stdout/stderr streams into a Tk queue."""

    def __init__(self, target: queue.Queue, tag: str = "INFO") -> None:
        super().__init__()
        self._queue = target
        self._tag = tag

    def write(self, data: str) -> int:  # pragma: no cover - GUI utility
        if data and data.strip():
            self._queue.put((self._tag, data))
        return len(data or "")

    def flush(self) -> None:  # pragma: no cover - GUI utility
        return None


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x760")
        self.minsize(980, 680)
        self.protocol("WM_DELETE_WINDOW", self._exit_app)
        self.after(0, self._maximize_on_start)

        self.queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self._ollama_install_thread: threading.Thread | None = None
        self._ollama_install_supported = True

        self.cfg: dict[str, object] = {}
        self.config_path = DEFAULT_CONFIG_PATH
        self.patterns_path = DEFAULT_PATTERNS_PATH

        self.error_rows: list[dict[str, str]] = []
        self.filename_format_presets: list[dict[str, str]] = []
        self.custom_format_label = CUSTOM_FILENAME_LABEL
        self._updating_filename_format = False

        self._build_ui()
        self._ollama_install_supported = self._build_ollama_install_command() is not None
        if not self._ollama_install_supported:
            self.btn_install_ollama.config(state=tk.DISABLED)
            self.var_ollama_status.set(
                "Automatische Installation wird auf diesem System nicht unterstützt."
            )
        self._load_config_silent(self.config_path)
        self.after(400, lambda: self._check_ollama_status(quiet=True))
        self._poll_queue()

    # ------------------------------------------------------------------
    # Window helpers
    # ------------------------------------------------------------------
    def _maximize_on_start(self) -> None:
        applied = False
        try:
            self.state("zoomed")
            applied = self.state() == "zoomed"
        except tk.TclError:
            applied = False

        if not applied:
            try:
                self.attributes("-zoomed", True)
                applied = self.state() == "zoomed"
            except tk.TclError:
                applied = False

        if not applied:
            self.update_idletasks()
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        main_area = ttk.Frame(root)
        main_area.pack(fill=tk.BOTH, expand=True)

        left_column = ttk.Frame(main_area)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        info_column = ttk.Frame(main_area)
        info_column.pack(side=tk.RIGHT, fill=tk.Y, padx=(12, 0))

        self._build_tool_info(info_column)
        self._build_system_config(info_column)
        self._build_configuration(left_column)
        self._build_actions(left_column)
        self._build_notebook(left_column)

    def _build_tool_info(self, parent: ttk.Frame) -> None:
        info_frame = ttk.LabelFrame(parent, text="Tool-Info")
        info_frame.pack(fill=tk.X, anchor=tk.N)
        info_text = (
            "Name: PDF Rechnungs Changer\n"
            "Autor: Markus Dickscheit\n"
            "Open Source Verwendung auf eigene Gefahr"
        )
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT, wraplength=220).pack(
            fill=tk.X, padx=8, pady=8
        )

    def _build_system_config(self, parent: ttk.Frame) -> None:
        system_frame = ttk.LabelFrame(parent, text="System-Konfiguration")
        system_frame.pack(fill=tk.X, anchor=tk.N, pady=(12, 0))

        ttk.Label(system_frame, text="Ollama-Integration:").pack(
            anchor=tk.W, padx=8, pady=(8, 0)
        )
        self.var_ollama_status = tk.StringVar(value="Status unbekannt")
        ttk.Label(
            system_frame,
            textvariable=self.var_ollama_status,
            justify=tk.LEFT,
            wraplength=220,
        ).pack(fill=tk.X, padx=8, pady=(4, 8))

        button_row = ttk.Frame(system_frame)
        button_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.btn_check_ollama = ttk.Button(
            button_row, text="Status prüfen", command=self._check_ollama_status
        )
        self.btn_check_ollama.pack(side=tk.LEFT)
        self.btn_install_ollama = ttk.Button(
            button_row, text="Ollama installieren", command=self._install_ollama
        )
        self.btn_install_ollama.pack(side=tk.LEFT, padx=6)

        ttk.Label(
            system_frame,
            text="Hinweis: Installation lädt Dateien von ollama.com herunter.",
            justify=tk.LEFT,
            wraplength=220,
        ).pack(fill=tk.X, padx=8, pady=(0, 8))
    def _build_configuration(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Konfiguration")
        frame.pack(fill=tk.X, pady=(0, 10))

        self.var_input = tk.StringVar()
        self.var_output = tk.StringVar()
        self.var_unknown = tk.StringVar(value="unbekannt")
        self.var_filename_fmt = tk.StringVar(value=DEFAULT_FILENAME_FMT)
        self.var_filename_fmt_choice = tk.StringVar(value=self.custom_format_label)
        self.var_tesseract = tk.StringVar()
        self.var_poppler = tk.StringVar()
        self.var_tess_lang = tk.StringVar(value="deu+eng")
        self.var_use_ocr = tk.BooleanVar(value=True)
        self.var_use_ollama = tk.BooleanVar(value=False)
        self.var_ollama_host = tk.StringVar(value="http://localhost:11434")
        self.var_ollama_model = tk.StringVar(value="llama3")
        self.var_dry = tk.BooleanVar(value=False)
        self.var_csv = tk.BooleanVar(value=False)
        self.var_csv_path = tk.StringVar(value="logs/processed.csv")
        self.var_config_path = tk.StringVar(value=self.config_path)
        self.var_patterns_path = tk.StringVar(value=self.patterns_path)

        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=6)
        ttk.Label(row1, text="Eingangsordner:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(row1, textvariable=self.var_input, width=70).grid(
            row=0, column=1, sticky=tk.W
        )
        ttk.Button(row1, text="Wählen", command=self._choose_input).grid(
            row=0, column=2, padx=6
        )

        ttk.Label(row1, text="Ausgangsordner:").grid(
            row=1, column=0, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(row1, textvariable=self.var_output, width=70).grid(
            row=1, column=1, sticky=tk.W, pady=(6, 0)
        )
        ttk.Button(row1, text="Wählen", command=self._choose_output).grid(
            row=1, column=2, padx=6, pady=(6, 0)
        )

        ttk.Label(row1, text="Ordner für Unbekannt:").grid(
            row=2, column=0, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(row1, textvariable=self.var_unknown, width=30).grid(
            row=2, column=1, sticky=tk.W, pady=(6, 0)
        )

        ttk.Label(row1, text="Dateiname-Muster:").grid(
            row=3, column=0, sticky=tk.W, pady=(6, 0)
        )
        self.cmb_filename_fmt = ttk.Combobox(
            row1,
            textvariable=self.var_filename_fmt_choice,
            state="readonly",
            width=40,
        )
        self.cmb_filename_fmt.grid(row=3, column=1, sticky=tk.W, pady=(6, 0))
        ttk.Button(row1, text="Standard", command=self._reset_filename_format).grid(
            row=3, column=2, padx=6, pady=(6, 0)
        )

        ttk.Label(row1, text="Muster-Vorschau:").grid(
            row=4, column=0, sticky=tk.W, pady=(6, 0)
        )
        self.entry_filename_fmt = ttk.Entry(
            row1, textvariable=self.var_filename_fmt, width=70
        )
        self.entry_filename_fmt.grid(row=4, column=1, columnspan=2, sticky=tk.W, pady=(6, 0))
        self._set_filename_format_options([], DEFAULT_FILENAME_FMT)
        self.var_filename_fmt.trace_add("write", self._on_filename_format_var_changed)
        self.cmb_filename_fmt.bind("<<ComboboxSelected>>", self._on_filename_format_choice)

        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=6)
        ttk.Checkbutton(
            row2, text="OCR verwenden (Scans)", variable=self.var_use_ocr
        ).grid(row=0, column=0, sticky=tk.W)

        ttk.Label(row2, text="Tesseract Pfad (tesseract.exe):").grid(
            row=1, column=0, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(row2, textvariable=self.var_tesseract, width=70).grid(
            row=1, column=1, sticky=tk.W, pady=(6, 0)
        )
        ttk.Button(row2, text="Suchen", command=self._choose_tesseract).grid(
            row=1, column=2, padx=6, pady=(6, 0)
        )

        ttk.Label(row2, text="Poppler bin Pfad:").grid(
            row=2, column=0, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(row2, textvariable=self.var_poppler, width=70).grid(
            row=2, column=1, sticky=tk.W, pady=(6, 0)
        )
        ttk.Button(row2, text="Wählen", command=self._choose_poppler).grid(
            row=2, column=2, padx=6, pady=(6, 0)
        )

        ttk.Label(row2, text="Tesseract Sprache (deu/deu+eng):").grid(
            row=3, column=0, sticky=tk.W, pady=(6, 0)
        )
        self.cmb_tess_lang = ttk.Combobox(
            row2,
            textvariable=self.var_tess_lang,
            values=["deu", "deu+eng"],
            width=28,
            state="normal",
        )
        self.cmb_tess_lang.grid(row=3, column=1, sticky=tk.W, pady=(6, 0))
        ttk.Button(row2, text="Aktualisieren", command=self._refresh_tess_langs).grid(
            row=3, column=2, padx=6, pady=(6, 0)
        )

        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=6)
        ttk.Checkbutton(
            row3, text="Ollama-Fallback verwenden", variable=self.var_use_ollama
        ).grid(row=0, column=0, sticky=tk.W)

        ttk.Label(row3, text="Ollama Host:").grid(
            row=1, column=0, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(row3, textvariable=self.var_ollama_host, width=40).grid(
            row=1, column=1, sticky=tk.W, pady=(6, 0)
        )
        ttk.Label(row3, text="Ollama Modell:").grid(
            row=1, column=2, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(row3, textvariable=self.var_ollama_model, width=20).grid(
            row=1, column=3, sticky=tk.W, pady=(6, 0)
        )

        row4 = ttk.Frame(frame)
        row4.pack(fill=tk.X, pady=6)
        ttk.Checkbutton(
            row4, text="Dry-Run (nichts verschieben)", variable=self.var_dry
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(
            row4, text="CSV-Log aktivieren", variable=self.var_csv
        ).grid(row=0, column=1, sticky=tk.W, padx=(12, 0))
        ttk.Label(row4, text="CSV-Pfad:").grid(row=0, column=2, sticky=tk.E)
        ttk.Entry(row4, textvariable=self.var_csv_path, width=32).grid(
            row=0, column=3, sticky=tk.W
        )

        ttk.Label(row4, text="config.yaml:").grid(
            row=1, column=0, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(row4, textvariable=self.var_config_path, width=52).grid(
            row=1, column=1, sticky=tk.W, pady=(6, 0)
        )
        ttk.Button(row4, text="Laden", command=self._choose_config).grid(
            row=1, column=2, padx=6, pady=(6, 0)
        )

        ttk.Label(row4, text="patterns.yaml:").grid(
            row=2, column=0, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(row4, textvariable=self.var_patterns_path, width=52).grid(
            row=2, column=1, sticky=tk.W, pady=(6, 0)
        )
        ttk.Button(row4, text="Laden", command=self._choose_patterns).grid(
            row=2, column=2, padx=6, pady=(6, 0)
        )

    def _build_actions(self, parent: ttk.Frame) -> None:
        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, pady=(0, 10))
        self.btn_save = ttk.Button(actions, text="Konfig speichern", command=self._save_config)
        self.btn_run = ttk.Button(actions, text="Verarbeiten starten", command=self._run_worker)
        self.btn_stop = ttk.Button(actions, text="Stop", command=self._stop_worker, state=tk.DISABLED)
        self.btn_preview = ttk.Button(actions, text="Vorschau laden…", command=self._preview_any_pdf)
        self.btn_exit = ttk.Button(actions, text="Beenden", command=self._exit_app)
        self.btn_save.pack(side=tk.LEFT)
        self.btn_run.pack(side=tk.LEFT, padx=8)
        self.btn_stop.pack(side=tk.LEFT)
        self.btn_exit.pack(side=tk.RIGHT)
        self.btn_preview.pack(side=tk.RIGHT, padx=(0, 8))

    def _build_notebook(self, parent: ttk.Frame) -> None:
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True)
        self.nb = nb

        tab_log = ttk.Frame(nb)
        nb.add(tab_log, text="Log")
        self.progress = ttk.Progressbar(tab_log, mode="determinate", maximum=100, value=0)
        self.progress.pack(fill=tk.X, padx=8, pady=8)
        self.txt = tk.Text(tab_log, wrap="word", height=20)
        self.txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.txt.configure(state=tk.DISABLED)

        tab_prev = ttk.Frame(nb)
        nb.add(tab_prev, text="Vorschau")
        prev_top = ttk.Frame(tab_prev)
        prev_top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(prev_top, text="Vorschau-Quelle:").pack(side=tk.LEFT)
        self.var_preview_path = tk.StringVar()
        ttk.Entry(prev_top, textvariable=self.var_preview_path, width=80).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(prev_top, text="…", command=self._preview_any_pdf).pack(side=tk.LEFT)
        self.preview_txt = tk.Text(tab_prev, wrap="word")
        self.preview_txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.preview_txt.configure(state=tk.NORMAL)

        tab_err = ttk.Frame(nb)
        nb.add(tab_err, text="Fehler")
        err_top = ttk.Frame(tab_err)
        err_top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(err_top, text="Liste leeren", command=self._errors_clear).pack(side=tk.RIGHT)
        self.err_tree = ttk.Treeview(tab_err, columns=("file", "msg"), show="headings")
        self.err_tree.heading("file", text="Datei")
        self.err_tree.heading("msg", text="Meldung")
        self.err_tree.column("file", width=320)
        self.err_tree.column("msg", width=560)
        self.err_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tab_rx = ttk.Frame(nb)
        nb.add(tab_rx, text="Regex-Tester")
        rx_top = ttk.Frame(tab_rx)
        rx_top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(rx_top, text="patterns.yaml laden", command=self._load_patterns_for_tester).pack(
            side=tk.LEFT
        )
        ttk.Button(rx_top, text="Test ausführen", command=self._run_regex_test).pack(
            side=tk.LEFT, padx=6
        )
        self.rx_info = tk.StringVar(value="– noch keine Patterns geladen –")
        ttk.Label(rx_top, textvariable=self.rx_info).pack(side=tk.LEFT, padx=12)
        self.rx_text = tk.Text(tab_rx, wrap="word", height=12)
        self.rx_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.rx_result = tk.Text(tab_rx, wrap="word", height=8)
        self.rx_result.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.loaded_patterns: dict[str, object] | None = None
    # ------------------------------------------------------------------
    # Filename format handling
    # ------------------------------------------------------------------
    def _reset_filename_format(self) -> None:
        self._set_filename_format_options(None, DEFAULT_FILENAME_FMT)

    def _default_filename_format_presets(self) -> list[dict[str, str]]:
        return [dict(item) for item in DEFAULT_FILENAME_FORMAT_PRESETS]

    def _normalize_filename_format_presets(self, presets_raw) -> list[dict[str, str]]:
        presets: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add_entry(label: str | None, pattern: str | None) -> None:
            if pattern is None:
                return
            pattern_str = str(pattern).strip()
            if not pattern_str:
                return
            label_str = str(label).strip() if label is not None else ""
            if not label_str:
                label_str = pattern_str
            key = (label_str, pattern_str)
            if key in seen:
                return
            seen.add(key)
            presets.append({"label": label_str, "pattern": pattern_str})

        if isinstance(presets_raw, dict):
            for label, pattern in presets_raw.items():
                add_entry(label, pattern)
        elif isinstance(presets_raw, list):
            for item in presets_raw:
                if isinstance(item, dict):
                    label = (
                        item.get("label")
                        or item.get("name")
                        or item.get("title")
                        or item.get("id")
                    )
                    pattern = (
                        item.get("pattern")
                        or item.get("format")
                        or item.get("template")
                        or item.get("value")
                    )
                    add_entry(label, pattern)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    add_entry(item[0], item[1])
                elif isinstance(item, str):
                    add_entry(item, item)
        return presets

    def _ensure_custom_label_available(self) -> None:
        values = list(self.cmb_filename_fmt.cget("values") or [])
        if self.custom_format_label not in values:
            values.append(self.custom_format_label)
            self.cmb_filename_fmt.configure(values=values)

    def _get_pattern_for_label(self, label: str) -> str | None:
        for preset in self.filename_format_presets:
            if preset.get("label") == label:
                return preset.get("pattern")
        return None

    def _get_label_for_pattern(self, pattern: str) -> str | None:
        for preset in self.filename_format_presets:
            if preset.get("pattern") == pattern:
                return preset.get("label")
        return None

    def _set_filename_format_options(self, presets_raw, selected_pattern: str | None) -> None:
        presets = (
            [dict(item) for item in self.filename_format_presets]
            if presets_raw is None
            else self._normalize_filename_format_presets(presets_raw)
        )
        if not presets:
            presets = self._default_filename_format_presets()
        self.filename_format_presets = presets
        values = [item.get("label", "") for item in presets]
        if self.custom_format_label not in values:
            values.append(self.custom_format_label)
        self.cmb_filename_fmt.configure(values=values)

        pattern = (selected_pattern or "").strip() if isinstance(selected_pattern, str) else ""
        if not pattern and presets:
            pattern = presets[0].get("pattern", DEFAULT_FILENAME_FMT)
        label = self._get_label_for_pattern(pattern)
        if label is None:
            label = self.custom_format_label
        self._updating_filename_format = True
        self.var_filename_fmt_choice.set(label)
        self.var_filename_fmt.set(pattern or DEFAULT_FILENAME_FMT)
        self._updating_filename_format = False
        if label == self.custom_format_label:
            self._ensure_custom_label_available()

    def _on_filename_format_choice(self, _event=None) -> None:
        if self._updating_filename_format:
            return
        label = self.var_filename_fmt_choice.get()
        pattern = self._get_pattern_for_label(label)
        if pattern is not None:
            self._updating_filename_format = True
            self.var_filename_fmt.set(pattern)
            self._updating_filename_format = False
        elif label == self.custom_format_label:
            self._ensure_custom_label_available()

    def _on_filename_format_var_changed(self, *_args) -> None:
        if self._updating_filename_format:
            return
        pattern = self.var_filename_fmt.get()
        label = self._get_label_for_pattern(pattern)
        self._updating_filename_format = True
        if label is not None:
            self.var_filename_fmt_choice.set(label)
        else:
            self._ensure_custom_label_available()
            self.var_filename_fmt_choice.set(self.custom_format_label)
        self._updating_filename_format = False
    # ------------------------------------------------------------------
    # Dialog helpers
    # ------------------------------------------------------------------
    def _choose_input(self) -> None:
        selected = filedialog.askdirectory(title="Eingangsordner wählen")
        if selected:
            self.var_input.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title="Ausgangsordner wählen")
        if selected:
            self.var_output.set(selected)

    def _choose_tesseract(self) -> None:
        selected = filedialog.askopenfilename(
            title="tesseract.exe wählen",
            filetypes=[("Programme", "*.exe"), ("Alle Dateien", "*.*")],
        )
        if selected:
            self.var_tesseract.set(selected)

    def _choose_poppler(self) -> None:
        selected = filedialog.askdirectory(title="Poppler bin-Ordner wählen")
        if selected:
            self.var_poppler.set(selected)

    def _choose_config(self) -> None:
        selected = filedialog.askopenfilename(
            title="config.yaml wählen",
            filetypes=[("YAML", "*.yaml;*.yml"), ("Alle Dateien", "*.*")],
        )
        if selected:
            self.var_config_path.set(selected)
            self._load_config_silent(selected)

    def _choose_patterns(self) -> None:
        selected = filedialog.askopenfilename(
            title="patterns.yaml wählen",
            filetypes=[("YAML", "*.yaml;*.yml"), ("Alle Dateien", "*.*")],
        )
        if selected:
            self.var_patterns_path.set(selected)
    # ------------------------------------------------------------------
    # Ollama helpers
    # ------------------------------------------------------------------
    def _detect_ollama_installation(self) -> tuple[bool, str]:
        executable = shutil.which("ollama")
        if not executable:
            return False, "Ollama wurde nicht gefunden."
        try:
            result = subprocess.run(
                [executable, "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                output = (result.stdout or result.stderr or "").strip()
                if output:
                    return True, f"Ollama installiert ({output})"
                return True, "Ollama ist installiert."
            return True, "Ollama gefunden, Versionsprüfung fehlgeschlagen."
        except Exception as exc:  # pragma: no cover - platform specific
            return True, f"Ollama gefunden, Versionsprüfung fehlgeschlagen: {exc}"

    def _apply_ollama_status(self, installed: bool, text: str, installing: bool = False) -> None:
        self.var_ollama_status.set(text or "Status unbekannt")
        if installing:
            self.btn_check_ollama.config(state=tk.DISABLED)
            self.btn_install_ollama.config(state=tk.DISABLED)
            return
        self.btn_check_ollama.config(state=tk.NORMAL)
        if self._ollama_install_supported:
            self.btn_install_ollama.config(state=tk.DISABLED if installed else tk.NORMAL)
        else:
            self.btn_install_ollama.config(state=tk.DISABLED)

    def _check_ollama_status(self, quiet: bool = False) -> bool:
        installed, message = self._detect_ollama_installation()
        info = message or (
            "Ollama ist installiert." if installed else "Ollama wurde nicht gefunden."
        )
        self._apply_ollama_status(installed, info)
        if not quiet:
            self._log("INFO", info + "\n")
        return installed

    def _build_ollama_install_command(self) -> list[str] | None:
        if sys.platform.startswith("linux") or sys.platform == "darwin":
            return ["bash", "-lc", "curl -fsSL https://ollama.com/install.sh | sh"]
        if os.name == "nt":  # pragma: no cover - windows specific
            script = (
                "$ProgressPreference='SilentlyContinue';"
                "$installer=Join-Path $env:TEMP 'OllamaSetup.exe';"
                "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile $installer;"
                "Start-Process -FilePath $installer -Wait"
            )
            return [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ]
        return None

    def _install_ollama(self) -> None:
        if self._ollama_install_thread and self._ollama_install_thread.is_alive():
            messagebox.showinfo("Ollama", "Eine Installation läuft bereits im Hintergrund.")
            return
        installed, message = self._detect_ollama_installation()
        if installed:
            info_text = message or "Ollama ist bereits installiert."
            messagebox.showinfo("Ollama", info_text)
            self._apply_ollama_status(True, info_text)
            return
        command = self._build_ollama_install_command()
        if command is None:
            self._ollama_install_supported = False
            self._apply_ollama_status(False, "Automatische Installation wird nicht unterstützt.")
            messagebox.showinfo(
                "Ollama",
                "Die automatische Installation wird auf diesem Betriebssystem nicht unterstützt. Bitte folge den manuellen Anweisungen auf ollama.com.",
            )
            return
        if not messagebox.askyesno(
            "Ollama installieren",
            "Soll Ollama jetzt installiert werden? Es wird eine Internetverbindung benötigt und ggf. ein separates Installationsfenster geöffnet.",
        ):
            return
        self._apply_ollama_status(False, "Installation läuft …", installing=True)
        thread = threading.Thread(
            target=self._run_ollama_installation_worker,
            args=(command,),
            daemon=True,
        )
        self._ollama_install_thread = thread
        thread.start()

    def _run_ollama_installation_worker(self, command: list[str]) -> None:
        installed = False
        status_msg = ""
        try:
            self.queue.put(("INFO", "Starte Ollama-Installation …\n"))
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if proc.stdout is not None:
                for line in proc.stdout:
                    if line:
                        self.queue.put(("INFO", f"[ollama] {line}"))
            return_code = proc.wait()
            if return_code != 0:
                raise RuntimeError(f"Installationsprozess endete mit Code {return_code}")
            installed, status_msg = self._detect_ollama_installation()
            if not installed:
                raise RuntimeError(status_msg or "Ollama konnte nach der Installation nicht gefunden werden.")
        except Exception as exc:  # pragma: no cover - background worker
            installed = False
            status_msg = f"Ollama Installation fehlgeschlagen: {exc}"
            self.queue.put(("ERR", status_msg + "\n"))
        else:
            if not status_msg:
                status_msg = "Ollama Installation abgeschlossen."
            self.queue.put(("INFO", status_msg + "\n"))
        finally:
            self.after(0, lambda: self._on_ollama_installation_finished(installed, status_msg))

    def _on_ollama_installation_finished(self, installed: bool, status_msg: str) -> None:
        self._ollama_install_thread = None
        if installed:
            self._apply_ollama_status(True, status_msg or "Ollama ist installiert.")
        else:
            fallback_msg = status_msg or "Ollama wurde nicht installiert."
            self._apply_ollama_status(False, fallback_msg)
    # ------------------------------------------------------------------
    # Config handling
    # ------------------------------------------------------------------
    def _refresh_tess_langs(self) -> None:
        cmd = (self.var_tesseract.get() or "").strip() or "tesseract"
        langs = ["deu", "eng", "deu+eng"]
        try:
            proc = subprocess.run(
                [cmd, "--list-langs"], capture_output=True, text=True, timeout=8
            )
            if proc.returncode == 0:
                found: list[str] = []
                for line in proc.stdout.splitlines():
                    text = line.strip()
                    if not text or "list of available languages" in text.lower():
                        continue
                    found.append(text)
                if "deu" in found and "eng" in found and "deu+eng" not in found:
                    found.append("deu+eng")
                if found:
                    langs = sorted(set(found), key=str.lower)
        except Exception:  # pragma: no cover - depends on external tools
            pass
        self.cmb_tess_lang.configure(values=langs)
        if self.var_tess_lang.get() not in langs:
            self.var_tess_lang.set(langs[0])
        self._log("INFO", f"Sprachen aktualisiert: {', '.join(langs)}\n")

    def _load_config_silent(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                cfg = yaml.safe_load(handle) or {}
            self.cfg = cfg
            self._cfg_to_vars(cfg)
            self._log("INFO", f"Konfiguration geladen: {path}\n")
        except Exception as exc:
            self._log("WARN", f"Konnte Konfiguration nicht laden: {exc}\n")

    def _cfg_to_vars(self, cfg: dict[str, object]) -> None:
        self.var_input.set(cfg.get("input_dir", ""))
        self.var_output.set(cfg.get("output_dir", ""))
        self.var_unknown.set(cfg.get("unknown_dir_name", "unbekannt"))
        self._set_filename_format_options(
            cfg.get("output_filename_formats"), cfg.get("output_filename_format")
        )
        self.var_tesseract.set(cfg.get("tesseract_cmd", ""))
        self.var_poppler.set(cfg.get("poppler_path", ""))
        self.var_use_ocr.set(bool(cfg.get("use_ocr", True)))
        self.var_use_ollama.set(bool(cfg.get("use_ollama", False)))
        self.var_tess_lang.set(cfg.get("tesseract_lang", "deu+eng"))
        ollama_cfg = cfg.get("ollama", {}) or {}
        self.var_ollama_host.set(ollama_cfg.get("host", "http://localhost:11434"))
        self.var_ollama_model.set(ollama_cfg.get("model", "llama3"))
        self.var_dry.set(bool(cfg.get("dry_run", False)))
        if cfg.get("csv_log_path"):
            self.var_csv.set(True)
            self.var_csv_path.set(cfg.get("csv_log_path"))

    def _vars_to_cfg(self) -> dict[str, object]:
        cfg: dict[str, object] = {
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
        if self.filename_format_presets:
            presets_out: list[dict[str, str]] = []
            seen: set[tuple[str, str]] = set()
            for item in self.filename_format_presets:
                label = str(item.get("label", "")).strip()
                pattern = str(item.get("pattern", "")).strip()
                if not pattern:
                    continue
                if not label:
                    label = pattern
                key = (label, pattern)
                if key in seen:
                    continue
                seen.add(key)
                presets_out.append({"label": label, "pattern": pattern})
            if presets_out:
                cfg["output_filename_formats"] = presets_out
        if self.var_csv.get():
            cfg["csv_log_path"] = self.var_csv_path.get()
        return cfg

    def _save_config(self) -> None:
        cfg = self._vars_to_cfg()
        path = self.var_config_path.get() or DEFAULT_CONFIG_PATH
        try:
            with open(path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(cfg, handle, allow_unicode=True, sort_keys=False)
            self._log("INFO", f"Konfiguration gespeichert: {path}\n")
        except Exception as exc:
            messagebox.showerror(
                "Fehler", f"Konfiguration konnte nicht gespeichert werden: {exc}"
            )
    # ------------------------------------------------------------------
    # Worker / processing
    # ------------------------------------------------------------------
    def _run_worker(self) -> None:
        if sorter is None:
            messagebox.showerror(
                "Fehlende Abhängigkeit", "sorter.py konnte nicht importiert werden."
            )
            return
        if self.worker_thread and self.worker_thread.is_alive():
            return
        self._save_config()
        self.stop_flag.clear()
        self.progress.config(mode="determinate", maximum=100, value=0)
        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = TextQueueWriter(self.queue, tag="OUT")
        sys.stderr = TextQueueWriter(self.queue, tag="ERR")

        def stop_fn() -> bool:
            return self.stop_flag.is_set()

        def progress_fn(index: int, total: int, filename: str, data: dict[str, object]) -> None:
            self.queue.put(("PROG", (index, total, filename, data)))

        def work() -> None:
            try:
                sorter.process_all(
                    self.var_config_path.get(),
                    self.var_patterns_path.get(),
                    stop_fn=stop_fn,
                    progress_fn=progress_fn,
                )
            except Exception as exc:
                self.queue.put(("ERR", f"Fehler im Worker: {exc}\n"))
            finally:
                self.queue.put(("DONE", None))

        thread = threading.Thread(target=work, daemon=True)
        self.worker_thread = thread
        thread.start()

    def _stop_worker(self) -> None:
        self.stop_flag.set()
        self.btn_stop.config(state=tk.DISABLED)
        self._log("INFO", "Stop angefordert…\n")

    def _exit_app(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            if not messagebox.askyesno(
                "Beenden", "Es läuft noch eine Verarbeitung. Trotzdem beenden?"
            ):
                return
            self.stop_flag.set()
        self.destroy()

    def _restore_streams(self) -> None:
        if hasattr(self, "_orig_stdout"):
            sys.stdout = self._orig_stdout  # type: ignore[attr-defined]
        if hasattr(self, "_orig_stderr"):
            sys.stderr = self._orig_stderr  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Queue/Log processing
    # ------------------------------------------------------------------
    def _poll_queue(self) -> None:
        try:
            while True:
                tag, payload = self.queue.get_nowait()
                if tag in {"OUT", "INFO", "WARN", "ERR"}:
                    self._append_text(payload, tag)
                elif tag == "PROG":
                    self._update_progress(*payload)
                elif tag == "ERROR":
                    self._errors_add(payload)
                elif tag == "PREVIEW":
                    self._update_preview(payload)
                elif tag == "DONE":
                    self._on_worker_done()
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _on_worker_done(self) -> None:
        self._restore_streams()
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.progress.config(value=0)
        self._log("INFO", "Verarbeitung abgeschlossen.\n")

    def _append_text(self, message: object, tag: str) -> None:
        text = str(message)
        self.txt.configure(state=tk.NORMAL)
        prefix = {
            "OUT": "",
            "INFO": "[INFO] ",
            "WARN": "[WARN] ",
            "ERR": "[ERR] ",
        }.get(tag, "")
        self.txt.insert(tk.END, prefix + text)
        self.txt.see(tk.END)
        self.txt.configure(state=tk.DISABLED)

    def _log(self, tag: str, message: str) -> None:
        self.queue.put((tag, message))

    def _update_progress(self, index: int, total: int, filename: str, data: dict[str, object]) -> None:
        if total:
            value = max(0, min(100, int((index / total) * 100)))
            self.progress.config(value=value)
        if data and data.get("status") == "error":
            self._errors_add(
                {
                    "file": filename,
                    "message": data.get("message", "Unbekannter Fehler"),
                }
            )
        elif data and data.get("preview"):
            self._update_preview({"text": data.get("preview"), "source": filename})

    def _errors_add(self, entry) -> None:
        if not entry:
            return
        file_name = entry.get("file", "")
        message = entry.get("message", "")
        self.err_tree.insert("", tk.END, values=(file_name, message))
        self.error_rows.append({"file": file_name, "message": message})

    def _errors_clear(self) -> None:
        for item in self.err_tree.get_children():
            self.err_tree.delete(item)
        self.error_rows.clear()

    def _update_preview(self, payload) -> None:
        if not payload:
            return
        text = payload.get("text", "")
        source = payload.get("source", "")
        if source:
            self.var_preview_path.set(source)
        self.preview_txt.configure(state=tk.NORMAL)
        self.preview_txt.delete("1.0", tk.END)
        self.preview_txt.insert("1.0", text)
        self.preview_txt.configure(state=tk.NORMAL)
    # ------------------------------------------------------------------
    # Preview / regex helper
    # ------------------------------------------------------------------
    def _preview_any_pdf(self) -> None:
        selected = filedialog.askopenfilename(
            title="PDF wählen",
            filetypes=[("PDF", "*.pdf"), ("Alle Dateien", "*.*")],
        )
        if selected:
            self.var_preview_path.set(selected)
            self._preview_pdf(selected)

    def _preview_pdf(self, path: str) -> None:
        if sorter is None:
            messagebox.showerror(
                "Fehlende Abhängigkeit", "sorter.py konnte nicht importiert werden."
            )
            return
        try:
            cfg_like = self._vars_to_cfg()
            text, method = sorter.extract_text_from_pdf(
                path,
                use_ocr=cfg_like.get("use_ocr", True),
                poppler_path=cfg_like.get("poppler_path"),
                tesseract_cmd=cfg_like.get("tesseract_cmd"),
                tesseract_lang=cfg_like.get("tesseract_lang", "deu+eng"),
            )
        except Exception as exc:
            messagebox.showerror("Fehler", f"Vorschau fehlgeschlagen: {exc}")
            return
        header = f"Quelle: {path}\nModus: {method}\nErstellt: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
        self.preview_txt.configure(state=tk.NORMAL)
        self.preview_txt.delete("1.0", tk.END)
        self.preview_txt.insert("1.0", header + (text or ""))
        self.preview_txt.configure(state=tk.NORMAL)

    def _load_patterns_for_tester(self) -> None:
        path = self.var_patterns_path.get() or self.patterns_path
        try:
            self.loaded_patterns = sorter.load_patterns(path) if sorter else None
        except Exception as exc:
            messagebox.showerror("Fehler", f"Patterns konnten nicht geladen werden: {exc}")
            return
        if self.loaded_patterns is None:
            self.rx_info.set("Keine Patterns geladen")
        else:
            pats = self.loaded_patterns
            invn = len(pats.get("invoice_number_patterns", []))
            datn = len(pats.get("date_patterns", []))
            supp = len(pats.get("supplier_hints", {}) or {})
            self.rx_info.set(
                f"Geladen – Rechnungsnr: {invn}, Datumsregex: {datn}, Lieferanten: {supp}"
            )
            self._log("INFO", "Regex-Patterns für Tester geladen.\n")

    def _run_regex_test(self) -> None:
        if not sorter:
            messagebox.showerror(
                "Fehlende Abhängigkeit", "sorter.py konnte nicht importiert werden."
            )
            return
        if not self.loaded_patterns:
            messagebox.showinfo("Regex-Tester", "Bitte zuerst patterns.yaml laden.")
            return
        text = self.rx_text.get("1.0", tk.END)
        if not text.strip():
            messagebox.showinfo("Regex-Tester", "Bitte einen Testtext eingeben.")
            return
        pats = self.loaded_patterns
        invoice_no = sorter.extract_invoice_no(text, pats.get("invoice_number_patterns", []))
        invoice_date = sorter.extract_date(text, pats.get("date_patterns", []))
        supplier = sorter.detect_supplier(text, pats.get("supplier_hints", {}))
        amounts = sorter.extract_amounts(text, pats)

        lines = ["--- Regex Testergebnis ---"]
        lines.append(f"Gefundener Lieferant: {supplier or '–'}")
        lines.append(f"Rechnungsnummer: {invoice_no or '–'}")
        lines.append(f"Rechnungsdatum: {invoice_date or '–'}")
        gross, net, tax, currency = amounts
        lines.append(
            "Beträge: "
            + ", ".join(
                part
                for part in [
                    f"Brutto={gross}" if gross is not None else None,
                    f"Netto={net}" if net is not None else None,
                    f"Steuer={tax}" if tax is not None else None,
                    f"Währung={currency}" if currency else None,
                ]
                if part is not None
            )
            or "–"
        )

        self.rx_result.configure(state=tk.NORMAL)
        self.rx_result.delete("1.0", tk.END)
        self.rx_result.insert("1.0", "\n".join(lines))
        self.rx_result.configure(state=tk.NORMAL)

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover - GUI bootstrap
    main()
