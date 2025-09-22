from __future__ import annotations

from pathlib import Path
from typing import Union, Dict, Any
import shutil

# Text-Extraktion
import fitz  # PyMuPDF

# E-Rechnung (ZUGFeRD/Factur-X/XRechnung)
try:
    from e_invoice import extract_embedded_xml, quick_invoice_fields
except Exception:
    # Falls das Modul (noch) nicht vorhanden ist, arbeiten wir nur mit Text
    extract_embedded_xml = None  # type: ignore
    quick_invoice_fields = None  # type: ignore


def _extract_text(pdf: Path) -> str:
    """Extrahiert Fließtext mit PyMuPDF; leer bei Bild-only-PDFs ohne OCR."""
    text_chunks = []
    with fitz.open(pdf) as doc:
        for page in doc:
            text_chunks.append(page.get_text("text"))
    return "\n".join(text_chunks).strip()


def _safe_slug(s: str | None, default: str = "unknown") -> str:
    import unicodedata, string
    if not s:
        return default
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    allowed = f"-_. {string.ascii_letters}{string.digits}"
    s = "".join(ch for ch in s if ch in allowed).strip().replace(" ", "_")[:120]
    return s or default


def _load_template_from_config(config_path: str) -> str | None:
    """
    Optional: lädt 'output_filename_format' aus config.yaml, wenn PyYAML vorhanden.
    Fällt sonst auf None zurück.
    """
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        return None
    try:
        cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        # akzeptiere beide Varianten
        tpl = cfg.get("output_filename_format") or cfg.get("output_filename_formats", [None])[0]
        if isinstance(tpl, list):
            tpl = tpl[0] if tpl else None
        if isinstance(tpl, str) and tpl.strip():
            return tpl.strip()
    except Exception:
        pass
    return None


def _build_filename(meta: Dict[str, Any], template: str | None) -> str:
    """
    Baut den Zieldateinamen aus Meta + Template.
    Unterstützte Platzhalter: {date}, {supplier}, {invoice_no}, {total}
    """
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


def analyze_pdf(
    input_path: Union[str, Path],
    config_path: str = "config.yaml",
    patterns_path: str = "patterns.yaml",
) -> Dict[str, Any]:
    """
    Analysiert eine einzelne PDF oder – falls ein Ordner übergeben wird – alle PDFs darin.
    Gibt ein Dict (oder Mapping filename->dict) zurück.
    """
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(p)

    if p.is_dir():
        result: Dict[str, Any] = {}
        for pdf in sorted(p.glob("*.pdf")):
            result[pdf.name] = analyze_pdf(pdf, config_path, patterns_path)
        return result

    # 1) Eingebettete XML nutzen, falls möglich
    if extract_embedded_xml is not None and quick_invoice_fields is not None:
        try:
            xml = extract_embedded_xml(p)
        except Exception:
            xml = None
        if xml:
            _, data = xml
            fields = quick_invoice_fields(data)  # type: ignore[arg-type]
            fields = fields or {}
            fields.update({"source": str(p), "method": "embedded_xml"})
            return fields

    # 2) Text-Extraktion als Fallback
    text = _extract_text(p)
    return {
        "source": str(p),
        "method": "text",
        "text_preview": text[:2000],
    }


def process_pdf(
    input_path: Union[str, Path],
    config_path: str = "config.yaml",
    patterns_path: str = "patterns.yaml",
    simulate: bool = False,
) -> Union[str, Dict[str, Any]]:
    """
    Bestimmt Zieldateinamen und verschiebt/benennt um.
    - Bei simulate=True wird nichts verschoben; wir geben Meta + Ziel zurück.
    - Bei Datei-Konflikten wird ein Suffix -1, -2, ... angehängt.
    """
    p = Path(input_path)
    if p.is_dir():
        # Batch: verarbeite alle PDFs im Ordner
        results: Dict[str, Any] = {}
        for pdf in sorted(p.glob("*.pdf")):
            results[pdf.name] = process_pdf(pdf, config_path, patterns_path, simulate=simulate)
        return results

    meta = analyze_pdf(p, config_path, patterns_path)
    template = _load_template_from_config(config_path)
    target_name = _build_filename(meta if isinstance(meta, dict) else {}, template)
    target = p.with_name(target_name)

    # Konfliktlösung per Suffix
    cand = target
    counter = 1
    while cand.exists():
        cand = target.with_stem(f"{target.stem}-{counter}")
        counter += 1

    if simulate:
        return {"source": str(p), "target": str(cand), "meta": meta}

    # tatsächliche Umbenennung (move)
    p.replace(cand)
    return str(cand)
