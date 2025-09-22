import json
import threading
import subprocess
import sys
import csv
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Projekt-APIs
try:
    from sorter import analyze_pdf, process_pdf
except Exception as e:
    raise SystemExit("Konnte sorter.py nicht importieren: " + str(e))

CFG_PATH = Path(__file__).parent / "gui_config.json"


def load_cfg() -> dict:
    if CFG_PATH.exists():
        try:
            return json.loads(CFG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cfg(cfg: dict) -> None:
    try:
        CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        messagebox.showwarning("Warnung", f"Konfiguration konnte nicht gespeichert werden: {e}")


def safe_slug(s: str, default: str = "unknown") -> str:
    import unicodedata, string
    if not s:
        return default
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    allowed = f"-_. {string.ascii_letters}{string.digits}"
    s = "".join(ch for ch in s if ch in allowed).strip().replace(" ", "_")[:120]
    return s or default


def build_filename_from_template(template: str, meta: dict) -> str:
    # Platzhalter: {date}, {supplier}, {invoice_no}, {total}
    vals = {
        "date": safe_slug((meta or {}).get("date")),
        "supplier": safe_slug((meta or {}).get("supplier")),
        "invoice_no": safe_slug((meta or {}).get("invoice_no")),
        "total": safe_slug((meta or {}).get("total")),
    }
    try:
        name = template.format(**vals)
    except KeyError as e:
        # falls Nutzer andere Platzhalter tippt
        name = template
    name = name.strip()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name or "unknown.pdf"


def resolve_conflict(base_dir: Path, filename: str, policy: str) -> Path | None:
    """policy: 'suffix', 'overwrite', 'skip'"""
    target = base_dir / filename
    if not target.exists():
        return target

    if policy == "overwrite":
        return target
    if policy == "skip":
        return None

    # 'suffix' -> foo.pdf, foo-1.pdf, foo-2.pdf ...
    stem = target.stem
    suffix = target.suffix
    i = 1
    while True:
        cand = base_dir / f"{stem}-{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1


class HotProc:
    """Startet/stoppt hotfolder.py als Subprozess; Stream landet im GUI-Log."""
    def __init__(self, on_line):
        self.proc = None
        self.on_line = on_line

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, inbox, done, err, config, patterns):
        if self.is_running():
            return
        cmd = [sys.executable, "-u", str(Path(__file__).parent / "hotfolder.py"),
               "--in", inbox, "--done", done, "--err", err,
               "--config", config, "--patterns", patterns]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            threading.Thread(target=self._pump, daemon=True).start()
        except FileNotFoundError:
            messagebox.showerror("Fehler", "hotfolder.py nicht gefunden.")

    def _pump(self):
        if not self.proc or not self.proc.stdout:
            return
        while True:
            line = self.proc.stdout.readline()
            if not line:
                break
            self.on_line(line.rstrip("\n"))

    def stop(self):
        if not self.is_running():
            return
        try:
            self.proc.terminate()
        except Exception:
            pass
        self.proc = None


class GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF-Wandler – Erweiterte GUI (Vorlagen & Konfliktlösung)")
        self.geometry("1280x780")
        self.minsize(1024, 680)

        self.cfg = load_cfg()
        self.var_config = tk.StringVar(value=self.cfg.get("config", "config.yaml"))
        self.var_patterns = tk.StringVar(value=self.cfg.get("patterns", "patterns.yaml"))
        self.var_template = tk.StringVar(value=self.cfg.get("template", "{date}_{supplier}_{invoice_no}.pdf"))
        self.var_conflict = tk.StringVar(value=self.cfg.get("conflict", "suffix"))  # suffix | overwrite | skip

        self.hot = HotProc(self.log)
        self.cancel_flag = threading.Event()

        self._build()

    # ---------- UI ----------
    def _build(self):
        # Top-Settings-Bar
        top = ttk.Frame(self); top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)
        ttk.Label(top, text="config.yaml:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.var_config, width=38).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="…", command=self.pick_cfg).pack(side=tk.LEFT, padx=2)

        ttk.Label(top, text="patterns.yaml:").pack(side=tk.LEFT, padx=(14,0))
        ttk.Entry(top, textvariable=self.var_patterns, width=38).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="…", command=self.pick_patterns).pack(side=tk.LEFT, padx=2)

        ttk.Label(top, text="Vorlage:").pack(side=tk.LEFT, padx=(14,0))
        ttk.Entry(top, textvariable=self.var_template, width=40).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="?", width=3, command=self.show_template_help).pack(side=tk.LEFT)

        ttk.Button(top, text="Speichern", command=self.save_settings).pack(side=tk.RIGHT)

        nb = ttk.Notebook(self); nb.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=8)

        self._tab_analyze(nb)
        self._tab_batch(nb)
        self._tab_hotfolder(nb)
        self._tab_patterns(nb)
        self._tab_log(nb)

    def _tab_analyze(self, nb):
        tab = ttk.Frame(nb); nb.add(tab, text="Analysieren")
        row = ttk.Frame(tab); row.pack(fill=tk.X, padx=8, pady=8)
        self.var_pdf_single = tk.StringVar()
        ttk.Entry(row, textvariable=self.var_pdf_single, width=80).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="PDF …", command=self.pick_pdf_single).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Analysieren", command=self.do_analyze_single).pack(side=tk.LEFT, padx=8)

        self.txt_single = tk.Text(tab, wrap="word")
        self.txt_single.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def _tab_batch(self, nb):
        tab = ttk.Frame(nb); nb.add(tab, text="Batch/Preview")
        # Row: folder + controls
        control = ttk.Frame(tab); control.pack(fill=tk.X, padx=8, pady=8)
        self.var_folder = tk.StringVar()
        ttk.Entry(control, textvariable=self.var_folder, width=80).pack(side=tk.LEFT, padx=4)
        ttk.Button(control, text="Ordner …", command=self.pick_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(control, text="Scannen", command=self.scan_folder).pack(side=tk.LEFT, padx=8)
        self.var_dry = tk.BooleanVar(value=True)
        ttk.Checkbutton(control, text="Trockenlauf", variable=self.var_dry).pack(side=tk.LEFT, padx=8)
        ttk.Button(control, text="Umbenennen", command=self.rename_all).pack(side=tk.LEFT, padx=8)
        ttk.Button(control, text="Abbrechen", command=self.cancel_ops).pack(side=tk.LEFT, padx=8)
        ttk.Button(control, text="Export CSV", command=self.export_csv).pack(side=tk.RIGHT, padx=8)
        ttk.Button(control, text="Export JSON", command=self.export_json).pack(side=tk.RIGHT, padx=8)

        # Conflict policy
        conflict = ttk.LabelFrame(tab, text="Konfliktlösung bei bestehenden Dateien")
        conflict.pack(fill=tk.X, padx=8, pady=(0,6))
        for val, label in (("suffix","Suffix anhängen (-1, -2, ...)"), ("overwrite","Überschreiben"), ("skip","Überspringen")):
            ttk.Radiobutton(conflict, text=label, value=val, variable=self.var_conflict).pack(side=tk.LEFT, padx=8)

        # Treeview + scrollbars
        cols = ("file", "method", "supplier", "invoice_no", "date", "preview", "target")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", height=18, selectmode="extended")
        headers = {
            "file":"Datei", "method":"Methode", "supplier":"Lieferant",
            "invoice_no":"Rechnungsnr.", "date":"Datum",
            "preview":"Vorschau", "target":"Zielname/ -pfad"
        }
        for c in cols:
            self.tree.heading(c, text=headers[c])
            self.tree.column(c, width=150 if c not in ("file","target","preview") else 280, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self.update_preview_for_selection)

        vsb = ttk.Scrollbar(tab, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tab, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,4))
        vsb.place(in_=self.tree, relx=1.0, rely=0, relheight=1.0, anchor="ne")
        hsb.pack(fill=tk.X, padx=8, pady=(0,8))

        # Context menu
        self.menu = tk.Menu(self.tree, tearoff=0)
        self.menu.add_command(label="Nur Auswahl umbenennen", command=self.rename_selection)
        self.menu.add_command(label="Aus Auswahl entfernen", command=self.remove_selection)
        self.tree.bind("<Button-3>", self._show_menu)

        # Progress
        prog_frame = ttk.Frame(tab); prog_frame.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(prog_frame, text="Fortschritt:").pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        # Statusbar
        self.var_status = tk.StringVar(value="Bereit.")
        ttk.Label(tab, textvariable=self.var_status).pack(side=tk.BOTTOM, anchor="w", padx=8, pady=4)

    def _tab_hotfolder(self, nb):
        tab = ttk.Frame(nb); nb.add(tab, text="Hotfolder")
        grid = ttk.Frame(tab); grid.pack(fill=tk.X, padx=8, pady=10)
        self.var_inbox = tk.StringVar(value=str(Path.cwd() / "inbox"))
        self.var_done = tk.StringVar(value=str(Path.cwd() / "processed"))
        self.var_err = tk.StringVar(value=str(Path.cwd() / "error"))
        self._row_path(grid, 0, "Inbox:", self.var_inbox, lambda: self.pick_dir_into(self.var_inbox))
        self._row_path(grid, 1, "Processed:", self.var_done, lambda: self.pick_dir_into(self.var_done))
        self._row_path(grid, 2, "Error:", self.var_err, lambda: self.pick_dir_into(self.var_err))

        btns = ttk.Frame(tab); btns.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(btns, text="Start", command=self.hot_start).pack(side=tk.LEFT, padx=3)
        ttk.Button(btns, text="Stop", command=self.hot_stop).pack(side=tk.LEFT, padx=3)

        ttk.Label(tab, text="Hotfolder-Log (laufende Ausgaben):").pack(anchor="w", padx=8)
        self.txt_hot = tk.Text(tab, wrap="word", height=14); self.txt_hot.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def _tab_patterns(self, nb):
        tab = ttk.Frame(nb); nb.add(tab, text="Muster (patterns.yaml)")
        tools = ttk.Frame(tab); tools.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(tools, text="patterns.yaml laden", command=self.load_patterns).pack(side=tk.LEFT, padx=4)
        ttk.Button(tools, text="Speichern", command=self.save_patterns).pack(side=tk.LEFT, padx=4)
        ttk.Button(tools, text="Validieren (leicht)", command=self.validate_patterns).pack(side=tk.LEFT, padx=4)
        self.txt_patterns = tk.Text(tab, wrap="none")
        self.txt_patterns.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Scrollbars
        vs = ttk.Scrollbar(self.txt_patterns, orient="vertical", command=self.txt_patterns.yview)
        hs = ttk.Scrollbar(tab, orient="horizontal", command=self.txt_patterns.xview)
        self.txt_patterns.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        hs.pack(fill=tk.X, padx=8, pady=(0,8))

    def _tab_log(self, nb):
        tab = ttk.Frame(nb); nb.add(tab, text="Log & Tools")
        self.txt_log = tk.Text(tab, wrap="word")
        self.txt_log.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tools = ttk.Frame(tab); tools.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(tools, text="Einstellungen speichern", command=self.save_settings).pack(side=tk.LEFT, padx=4)
        ttk.Button(tools, text="Einstellungen öffnen…", command=self.open_cfg_file).pack(side=tk.LEFT, padx=4)

    # ---------- Actions ----------
    def pick_cfg(self):
        p = filedialog.askopenfilename(filetypes=[("YAML","*.yml *.yaml"),("Alle","*.*")])
        if p: self.var_config.set(p)

    def pick_patterns(self):
        p = filedialog.askopenfilename(filetypes=[("YAML","*.yml *.yaml"),("Alle","*.*")])
        if p: self.var_patterns.set(p)

    def save_settings(self):
        self.cfg["config"] = self.var_config.get().strip()
        self.cfg["patterns"] = self.var_patterns.get().strip()
        self.cfg["template"] = self.var_template.get().strip()
        self.cfg["conflict"] = self.var_conflict.get().strip()
        save_cfg(self.cfg)
        messagebox.showinfo("Gespeichert", "Einstellungen gespeichert.")

    def show_template_help(self):
        messagebox.showinfo(
            "Vorlagen-Hilfe",
            "Verwende Platzhalter:\n"
            "{date}, {supplier}, {invoice_no}, {total}\n\n"
            "Beispiel: {date}_{supplier}_{invoice_no}.pdf\n"
            "Hinweis: Ungültige Zeichen werden entfernt, leere Felder als 'unknown' ersetzt."
        )

    def open_cfg_file(self):
        try:
            Path(CFG_PATH).parent.mkdir(parents=True, exist_ok=True)
            if not Path(CFG_PATH).exists():
                save_cfg(self.cfg)
            messagebox.showinfo("Pfad", f"Config: {CFG_PATH}")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def pick_pdf_single(self):
        p = filedialog.askopenfilename(filetypes=[("PDF","*.pdf")])
        if p: self.var_pdf_single.set(p)

    def do_analyze_single(self):
        path = self.var_pdf_single.get().strip()
        if not path:
            messagebox.showwarning("Hinweis", "Bitte eine PDF auswählen.")
            return
        self.txt_single.delete("1.0","end")

        def work():
            try:
                meta = analyze_pdf(path, self.var_config.get(), self.var_patterns.get())
                # Template-Vorschau für Einzeldatei
                preview_name = build_filename_from_template(self.var_template.get(), meta)
                out = {"meta": meta, "template_preview": preview_name}
                self._set_text(self.txt_single, json.dumps(out, ensure_ascii=False, indent=2))
            except Exception as e:
                self._set_text(self.txt_single, f"Fehler: {e}")
                self.log(f"[Analyze] Fehler: {e}")

        threading.Thread(target=work, daemon=True).start()

    def pick_folder(self):
        d = filedialog.askdirectory()
        if d: self.var_folder.set(d)

    def scan_folder(self):
        folder = Path(self.var_folder.get().strip())
        if not folder.exists():
            messagebox.showwarning("Hinweis", "Ordner existiert nicht.")
            return
        self.tree.delete(*self.tree.get_children())
        self.var_status.set("Scanne…")
        self.progress.configure(value=0)
        self.cancel_flag.clear()

        def work():
            files = sorted(folder.glob("*.pdf"))
            total = len(files)
            done = 0
            for pdf in files:
                if self.cancel_flag.is_set():
                    break
                try:
                    # Metadaten ziehen
                    meta = analyze_pdf(str(pdf), self.var_config.get(), self.var_patterns.get())
                    target_name = build_filename_from_template(self.var_template.get(), meta)
                    target = str(pdf.parent / target_name)
                    method = meta.get("method") if isinstance(meta, dict) else ""
                    row = (
                        str(pdf.name),
                        str(method or ""),
                        str((meta or {}).get("supplier") or ""),
                        str((meta or {}).get("invoice_no") or ""),
                        str((meta or {}).get("date") or ""),
                        (meta.get("text_preview", "")[:60] + "…") if isinstance(meta, dict) and meta.get("text_preview") else "",
                        target
                    )
                    self.tree.insert("", "end", values=row, iid=str(pdf))
                except Exception as e:
                    self.log(f"[Scan] Fehler bei {pdf}: {e}")
                finally:
                    done += 1
                    self.progress.configure(maximum=total, value=done)
                    self.var_status.set(f"Scanne… {done}/{total}")
            self.var_status.set(f"Scan {'abgebrochen' if self.cancel_flag.is_set() else 'fertig'}. {done} verarbeitet.")
        threading.Thread(target=work, daemon=True).start()

    def update_preview_for_selection(self, event=None):
        # bei Template-Änderungen könnte man hier zukünftige Live-Updates triggern
        pass

    def rename_all(self):
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("Hinweis", "Nichts zu verarbeiten. Bitte erst 'Scannen'.")
            return
        dry = self.var_dry.get()
        self.progress.configure(value=0)
        self.cancel_flag.clear()

        def work():
            total = len(items)
            ok, failed, done = 0, 0, 0
            for iid in items:
                if self.cancel_flag.is_set():
                    break
                pdf_path = Path(iid)
                try:
                    # Metadaten & Zielname per GUI-Template
                    meta = analyze_pdf(str(pdf_path), self.var_config.get(), self.var_patterns.get())
                    filename = build_filename_from_template(self.var_template.get(), meta)
                    target = resolve_conflict(pdf_path.parent, filename, self.var_conflict.get())
                    if target is None:
                        self.log(f"[Rename] Übersprungen (existiert): {pdf_path.name}")
                    else:
                        if dry:
                            self.log(f"[Rename] (dry) {pdf_path.name} -> {target.name}")
                        else:
                            # Fallback auf process_pdf, falls es selbst verschiebt; sonst kopieren
                            try:
                                res = process_pdf(str(pdf_path), self.var_config.get(), self.var_patterns.get(), simulate=False)
                                # Wenn process_pdf nicht verschiebt, kopieren wir sicherheitshalber
                                if isinstance(res, str) and not Path(res).exists():
                                    pdf_path.replace(target)
                                elif isinstance(res, dict) and "target" in res and Path(res["target"]).exists():
                                    pass
                                else:
                                    pdf_path.replace(target)
                            except TypeError:
                                # alte Signatur -> selber verschieben
                                pdf_path.replace(target)
                            self.log(f"[Rename] {pdf_path.name} -> {target.name}")
                        ok += 1
                except Exception as e:
                    self.log(f"[Rename] Fehler bei {pdf_path.name}: {e}")
                    failed += 1
                finally:
                    done += 1
                    self.progress.configure(maximum=total, value=done)
                    self.var_status.set(f"Umbenennen… {done}/{total}")
            self.var_status.set(f"Fertig. Erfolgreich: {ok}, Fehler: {failed}, Dry-Run: {dry}{' (abgebrochen)' if self.cancel_flag.is_set() else ''}")
        threading.Thread(target=work, daemon=True).start()

    def rename_selection(self):
        items = self.tree.selection()
        if not items:
            messagebox.showinfo("Hinweis", "Bitte Zeilen markieren (Strg/Shift + Klick).")
            return
        dry = self.var_dry.get()
        self.progress.configure(value=0)
        self.cancel_flag.clear()

        def work():
            total = len(items)
            ok, failed, done = 0, 0, 0
            for iid in items:
                if self.cancel_flag.is_set():
                    break
                pdf_path = Path(iid)
                try:
                    meta = analyze_pdf(str(pdf_path), self.var_config.get(), self.var_patterns.get())
                    filename = build_filename_from_template(self.var_template.get(), meta)
                    target = resolve_conflict(pdf_path.parent, filename, self.var_conflict.get())
                    if target is None:
                        self.log(f"[Rename] Übersprungen (existiert): {pdf_path.name}")
                    else:
                        if dry:
                            self.log(f"[Rename] (dry) {pdf_path.name} -> {target.name}")
                        else:
                            try:
                                res = process_pdf(str(pdf_path), self.var_config.get(), self.var_patterns.get(), simulate=False)
                                if isinstance(res, str) and not Path(res).exists():
                                    pdf_path.replace(target)
                                elif isinstance(res, dict) and "target" in res and Path(res["target"]).exists():
                                    pass
                                else:
                                    pdf_path.replace(target)
                            except TypeError:
                                pdf_path.replace(target)
                            self.log(f"[Rename] {pdf_path.name} -> {target.name}")
                        ok += 1
                except Exception as e:
                    self.log(f"[Rename] Fehler bei {pdf_path.name}: {e}")
                    failed += 1
                finally:
                    done += 1
                    self.progress.configure(maximum=total, value=done)
                    self.var_status.set(f"Umbenennen (Auswahl)… {done}/{total}")
            self.var_status.set(f"Fertig (Auswahl). Erfolgreich: {ok}, Fehler: {failed}, Dry-Run: {dry}{' (abgebrochen)' if self.cancel_flag.is_set() else ''}")
        threading.Thread(target=work, daemon=True).start()

    def remove_selection(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)

    def _show_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.menu.tk_popup(event.x_root, event.y_root)

    def cancel_ops(self):
        self.cancel_flag.set()

    def export_csv(self):
        if not self.tree.get_children():
            messagebox.showinfo("Export", "Keine Daten zum Exportieren.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if not p: return
        cols = ("file", "method", "supplier", "invoice_no", "date", "preview", "target")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(cols)
            for iid in self.tree.get_children():
                w.writerow(self.tree.item(iid, "values"))
        messagebox.showinfo("Export", f"CSV gespeichert: {p}")

    def export_json(self):
        if not self.tree.get_children():
            messagebox.showinfo("Export", "Keine Daten zum Exportieren.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")])
        if not p: return
        data = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            data.append({
                "file": vals[0], "method": vals[1], "supplier": vals[2],
                "invoice_no": vals[3], "date": vals[4],
                "preview": vals[5], "target": vals[6]
            })
        Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo("Export", f"JSON gespeichert: {p}")

    def _row_path(self, parent, row, label, var, picker):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e")
        ttk.Entry(parent, textvariable=var, width=70).grid(row=row, column=1, padx=5, pady=2, sticky="we")
        ttk.Button(parent, text="…", command=picker).grid(row=row, column=2)

    def pick_dir_into(self, var: tk.StringVar):
        d = filedialog.askdirectory()
        if d: var.set(d)

    def hot_start(self):
        self.hot.start(self.var_inbox.get(), self.var_done.get(), self.var_err.get(),
                       self.var_config.get(), self.var_patterns.get())

    def hot_stop(self):
        self.hot.stop()

    # ---------- Patterns ----------
    def load_patterns(self):
        path = self.var_patterns.get().strip()
        if not path:
            messagebox.showwarning("Hinweis", "Bitte eine patterns.yaml angeben.")
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            self._set_text(self.txt_patterns, text)
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Datei nicht lesen: {e}")

    def save_patterns(self):
        path = self.var_patterns.get().strip()
        if not path:
            messagebox.showwarning("Hinweis", "Bitte eine patterns.yaml angeben.")
            return
        try:
            txt = self.txt_patterns.get("1.0","end")
            Path(path).write_text(txt, encoding="utf-8")
            messagebox.showinfo("Gespeichert", f"patterns.yaml gespeichert: {path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Datei nicht speichern: {e}")

    def validate_patterns(self):
        # Sehr einfache Plausibilitätsprüfung (YAML-Parsing, vorhandene Schlüssel)
        try:
            import yaml  # optional; falls nicht installiert: Hinweis
        except Exception:
            messagebox.showwarning("Hinweis", "PyYAML nicht installiert. `pip install pyyaml` für Validierung.")
            return
        try:
            txt = self.txt_patterns.get("1.0","end")
            data = yaml.safe_load(txt) if txt.strip() else {}
            if not isinstance(data, dict):
                raise ValueError("Root ist kein Mapping (dict).")
            problems = []
            for name, node in (data.items() if data else []):
                if not isinstance(node, dict):
                    problems.append(f"{name}: Eintrag ist kein Mapping")
                    continue
                for key in ("invoice_no", "date"):
                    if key not in node:
                        problems.append(f"{name}: Schlüssel fehlt: {key}")
            if problems:
                self.log("[Patterns] Probleme:\n- " + "\n- ".join(problems))
                messagebox.showwarning("Validierung", f"{len(problems)} Problem(e) gefunden – Details im Log.")
            else:
                messagebox.showinfo("Validierung", "OK: Grundlegende Prüfung bestanden.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Validierung fehlgeschlagen: {e}")

    # ---------- Log helpers ----------
    def log(self, line: str):
        try:
            self.txt_hot.insert("end", line + "\n")
            self.txt_hot.see("end")
        except Exception:
            pass
        try:
            self.txt_log.insert("end", line + "\n")
            self.txt_log.see("end")
        except Exception:
            pass

    def _set_text(self, widget: tk.Text, text: str):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="normal")


def main():
    app = GUI()
    app.mainloop()


if __name__ == "__main__":
    main()
