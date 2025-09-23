# -*- coding: utf-8 -*-
"""
Robuste sorter.py
- Läuft auch ohne PyMuPDF; fällt auf PyPDF2 zurück.
- Nutzt optional e_invoice.extract_embedded_xml / quick_invoice_fields, wenn vorhanden.
- Bietet extract_text_from_pdf, analyze_pdf, process_pdf, process_all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union, Dict, Any, Optional, Callable
import re

# Optional-Imports
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import yaml  # für config-Template & process_all
except Exception:
    yaml = None

try:
    from e_invoice import extract_embedded_xml, quick_invoice_fields  # type: ignore
except Exception:
    extract_embedded_xml = None  # type: ignore
    quick_invoice_fields = None  # type: ignore


# -------------------- Utilities --------------------
def _safe_slug(s: Optional[str], default: str = "unknown") -> str:
    import unicodedata, string
    if not s:
        return default
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    allowed = f"-_. {string.ascii_letters}{string.digits}"
    s = "".join(ch for ch in s if ch in allowed).strip().replace(" ", "_")[:120]
    return s or default


def _build_filename(meta: Dict[str, Any], template: Optional[str]) -> str:
    vals = {
        "date": _safe_slug(meta.get("date")),
        "supplier": _safe_slug(meta.get("supplier")),
        "invoice_no": _safe_slug(meta.get("invoice_no")),
        "total": _safe_slug(meta.get("total")),
    }
    if not template:
        template = "{date}_{supplier}_{invoice_no}.pdf"
    try:
        name = template.format(**vals)
    except Exception:
        name = "{date}_{supplier}_{invoice_no}.pdf".format(**vals)
    name = name.strip()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name or "unknown.pdf"


def _load_template_from_config(config_path: str) -> Optional[str]:
    if yaml is None:
        return None
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        return None
    try:
        cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        tpl = cfg.get("output_filename_format")
        if isinstance(tpl, list):
            tpl = tpl[0] if tpl else None
        if isinstance(tpl, str) and tpl.strip():
            return tpl.strip()
    except Exception:
        pass
    return None


# -------------------- Core functions --------------------
def extract_text_from_pdf(
    input_path: Union[str, Path],
    use_ocr: bool = True,
    poppler_path: str = "",
    tesseract_cmd: str = "",
    tesseract_lang: str = "deu+eng",
) -> tuple[str, str]:
    """
    Gibt (text, method) zurück.
    OCR ist hier nicht integriert; diese Funktion liefert Text ohne OCR.
    """
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(p)

    # 1) PyMuPDF
    if fitz is not None:
        try:
            chunks = []
            with fitz.open(p) as doc:
                for page in doc:
                    chunks.append(page.get_text("text"))
            return ("\n".join(chunks).strip(), "pymupdf")
        except Exception:
            pass

    # 2) PyPDF2
    if PyPDF2 is not None:
        try:
            text = []
            with p.open("rb") as fh:
                reader = PyPDF2.PdfReader(fh)
                for page in reader.pages:
                    t = page.extract_text() or ""
                    text.append(t)
            return ("\n".join(text).strip(), "pypdf2")
        except Exception:
            pass

    # 3) Fallback
    return ("", "none")


def analyze_pdf(
    input_path: Union[str, Path],
    config_path: str = "config.yaml",
    patterns_path: str = "patterns.yaml",
) -> Dict[str, Any]:
    """
    Analysiert eine einzelne PDF. Wenn ein Ordner übergeben wird, wird ein Mapping zurückgegeben.
    Nutzt – falls verfügbar – eingebettete E-Rechnungs-XML.
    """
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(p)

    if p.is_dir():
        out: Dict[str, Any] = {}
        for pdf in sorted(p.glob("*.pdf")):
            out[pdf.name] = analyze_pdf(pdf, config_path, patterns_path)
        return out  # type: ignore[return-value]

    # 1) Eingebettete XML (optional)
    if extract_embedded_xml is not None and quick_invoice_fields is not None:
        try:
            xml = extract_embedded_xml(p)
        except Exception:
            xml = None
        if xml:
            _, data = xml
            try:
                fields = quick_invoice_fields(data) or {}  # type: ignore[arg-type]
            except Exception:
                fields = {}
            fields.update({"source": str(p), "method": "embedded_xml"})
            return fields

    # 2) Text
    text, method = extract_text_from_pdf(p)
    # Mini-Heuristik für Nummer/Datum (optional, sehr tolerant)
    invoice_no = None
    m = re.search(r"Rechnungs(?:nummer|nr\.?)\s*[:#]?\s*([A-Z0-9\-\/]+)", text, re.I)
    if m:
        invoice_no = m.group(1).strip()

    date = None
    m = re.search(r"(\d{1,2}[.\-\/]\d{1,2}[.\-\/]\d{2,4})", text)
    if m:
        raw = m.group(1).replace("/", ".").replace("-", ".")
        parts = raw.split(".")
        if len(parts) == 3:
            d, mth, y = parts
            if len(y) == 2:
                y = "20" + y  # naive
            date = f"{y}-{mth.zfill(2)}-{d.zfill(2)}"

    return {
        "source": str(p),
        "method": method,
        "text_preview": text[:2000],
        "invoice_no": invoice_no,
        "date": date,
    }


def process_pdf(
    input_path: Union[str, Path],
    config_path: str = "config.yaml",
    patterns_path: str = "patterns.yaml",
    simulate: bool = False,
) -> Union[str, Dict[str, Any]]:
    """
    Bestimmt Zieldateinamen und verschiebt/benennt um.
    - simulate=True: nur Vorschau (Meta + Ziel)
    - Konflikte: Suffix -1, -2, ...
    """
    p = Path(input_path)
    if p.is_dir():
        out: Dict[str, Any] = {}
        for pdf in sorted(p.glob("*.pdf")):
            out[pdf.name] = process_pdf(pdf, config_path, patterns_path, simulate=simulate)
        return out

    meta = analyze_pdf(p, config_path, patterns_path)
    template = _load_template_from_config(config_path)
    target_name = _build_filename(meta if isinstance(meta, dict) else {}, template)
    target = p.with_name(target_name)

    cand = target
    i = 1
    while cand.exists():
        cand = target.with_stem(f"{target.stem}-{i}")
        i += 1

    if simulate:
        return {"source": str(p), "target": str(cand), "meta": meta}

    p.replace(cand)
    return str(cand)


def process_all(
    config_path: str = "config.yaml",
    patterns_path: str = "patterns.yaml",
    stop_fn: Optional[Callable[[], bool]] = None,
    progress_fn: Optional[Callable[[int, int, str, Any], None]] = None,
) -> None:
    """
    Batch-Verarbeitung basierend auf config.yaml:
      input_dir, dry_run, csv_log_path (optional)
    Ruft progress_fn(i, n, filename, data) auf (data ist SimpleNamespace-ähnlich).
    """
    if yaml is None:
        raise RuntimeError("PyYAML ist nicht installiert – process_all benötigt PyYAML. `pip install pyyaml`")

    from types import SimpleNamespace
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    in_dir = Path(cfg.get("input_dir") or ".")
    dry = bool(cfg.get("dry_run", False))
    csv_path = cfg.get("csv_log_path")

    if not in_dir.exists():
        raise FileNotFoundError(f"Eingangsordner fehlt: {in_dir}")

    pdfs = sorted(in_dir.glob("*.pdf"))
    n = len(pdfs)
    for i, pdf in enumerate(pdfs, start=1):
        if stop_fn and stop_fn():
            print("Abbruch angefordert – stoppe nach aktueller Datei.")
            break
        try:
            meta = analyze_pdf(str(pdf), config_path, patterns_path)
            data = SimpleNamespace(
                invoice_no=(meta.get("invoice_no") if isinstance(meta, dict) else None),
                supplier=(meta.get("supplier") if isinstance(meta, dict) else None),
                invoice_date=(meta.get("date") if isinstance(meta, dict) else None),
                total=(meta.get("total") if isinstance(meta, dict) else None),
                iban=(meta.get("iban") if isinstance(meta, dict) else None),
                validation_status=("ok" if all([meta.get("invoice_no"), meta.get("date")]) else "needs_review"),
                method=(meta.get("method") if isinstance(meta, dict) else None),
            )
            if progress_fn:
                progress_fn(i, n, str(pdf), data)

            res = process_pdf(str(pdf), config_path, patterns_path, simulate=dry)
            target = res["target"] if isinstance(res, dict) else res

            if csv_path:
                try:
                    path = Path(csv_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    import csv
                    with path.open("a", newline="", encoding="utf-8") as fh:
                        w = csv.writer(fh, delimiter=";")
                        w.writerow([
                            datetime_now(),
                            pdf.name,
                            data.invoice_no or "",
                            data.supplier or "",
                            data.invoice_date or "",
                            data.total or "",
                            data.iban or "",
                            data.validation_status or "",
                            data.method or "",
                            target or "",
                        ])
                except Exception:
                    pass
            print(f"Verarbeitet: {pdf.name} -> {target}")
        except Exception as e:
            import sys
            print(f"Fehler bei {pdf.name}: {e}", file=sys.stderr)


def datetime_now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
