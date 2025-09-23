from __future__ import annotations

import csv
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore

PathLike = Union[str, os.PathLike[str]]

DEFAULT_CONFIG: Dict[str, Union[str, bool]] = {
    "input_dir": "inbox",
    "output_dir": "processed",
    "unknown_dir_name": "unbekannt",
    "tesseract_cmd": "",
    "poppler_path": "",
    "tesseract_lang": "deu+eng",
    "use_ocr": True,
    "dry_run": False,
    "csv_log_path": "",
    "output_filename_format": "{date}_{supplier}_{invoice_no}.pdf",
}

DEFAULT_PATTERNS: Dict[str, object] = {
    "invoice_number_patterns": [],
    "date_patterns": [],
    "supplier_hints": {},
    "supplier_patterns": {},
}


@dataclass
class ExtractionResult:
    text: str
    method: str
    page_count: int


def _read_yaml(path: PathLike) -> Dict[str, object]:
    if yaml is None:
        raise RuntimeError("PyYAML ist nicht installiert – config/patterns können nicht gelesen werden.")
    with open(Path(path), "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, dict):
        return dict(data)
    raise ValueError(f"YAML-Datei {path} muss ein Mapping enthalten.")


def load_config(config_like: Union[None, PathLike, Mapping[str, object]]) -> Dict[str, object]:
    """Lädt die Konfiguration aus Datei oder Mapping und mischt sie mit Defaults."""

    cfg: Dict[str, object] = dict(DEFAULT_CONFIG)
    if config_like is None:
        return cfg
    data: Mapping[str, object]
    if isinstance(config_like, (str, os.PathLike)):
        data = _read_yaml(config_like)
    elif isinstance(config_like, Mapping):
        data = config_like
    else:  # pragma: no cover - defensive
        raise TypeError("config_like muss Pfad oder Mapping sein")
    for key, value in data.items():
        if value is None:
            continue
        cfg[key] = value
    # Strings bereinigen
    for key in ("tesseract_cmd", "poppler_path", "unknown_dir_name", "csv_log_path", "output_filename_format"):
        if key in cfg and isinstance(cfg[key], str):
            cfg[key] = cfg[key].strip()
    return cfg


def load_patterns(patterns_like: Union[None, PathLike, Mapping[str, object]]) -> Dict[str, object]:
    pats: Dict[str, object] = dict(DEFAULT_PATTERNS)
    if patterns_like is None:
        return pats
    data: Mapping[str, object]
    if isinstance(patterns_like, (str, os.PathLike)):
        data = _read_yaml(patterns_like)
    elif isinstance(patterns_like, Mapping):
        data = patterns_like
    else:  # pragma: no cover - defensive
        raise TypeError("patterns_like muss Pfad oder Mapping sein")
    for key, value in data.items():
        if value is None:
            continue
        pats[key] = value
    return pats


def _sanitize_component(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    table = str.maketrans({c: "_" for c in '<>:"/\\|?*'})
    text = text.translate(table)
    text = text.strip(" ._")
    return text


def _ensure_filename(name: str) -> str:
    name = name.strip()
    if not name:
        return "document.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = name.strip(" .")
    return name or "document.pdf"


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, ext = os.path.splitext(filename)
    counter = 1
    while True:
        alt = directory / f"{stem}_{counter}{ext or '.pdf'}"
        if not alt.exists():
            return alt
        counter += 1


def _extract_with_pymupdf(pdf_path: Path) -> ExtractionResult:
    try:
        import fitz  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        return ExtractionResult(text="", method="unavailable", page_count=0)
    text_parts: List[str] = []
    page_count = 0
    try:
        with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
            page_count = doc.page_count
            for page in doc:  # type: ignore[assignment]
                text_parts.append(page.get_text("text") or "")
    except Exception:
        return ExtractionResult(text="", method="error", page_count=page_count)
    text = "\n".join(text_parts)
    return ExtractionResult(text=text, method="text", page_count=page_count)


def _extract_with_pypdf2(pdf_path: Path) -> ExtractionResult:
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        return ExtractionResult(text="", method="unavailable", page_count=0)
    text_parts: List[str] = []
    try:
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        for page in reader.pages:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                text_parts.append("")
    except Exception:
        return ExtractionResult(text="", method="error", page_count=0)
    text = "\n".join(text_parts)
    return ExtractionResult(text=text, method="text", page_count=len(text_parts))


def _extract_with_ocr(
    pdf_path: Path,
    poppler_path: Optional[str],
    tesseract_cmd: Optional[str],
    tesseract_lang: str,
    max_pages: int = 5,
) -> ExtractionResult:
    try:
        from pdf2image import convert_from_path  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        return ExtractionResult(text="", method="unavailable", page_count=0)
    try:
        import pytesseract  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        return ExtractionResult(text="", method="unavailable", page_count=0)

    if tesseract_cmd:
        try:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        except Exception:
            pass
    lang = tesseract_lang or "deu+eng"
    try:
        images = convert_from_path(
            str(pdf_path),
            dpi=300,
            poppler_path=poppler_path or None,
            first_page=1,
            last_page=max_pages,
        )
    except Exception:
        return ExtractionResult(text="", method="error", page_count=0)
    text_parts: List[str] = []
    for image in images:
        try:
            text_parts.append(pytesseract.image_to_string(image, lang=lang) or "")
        except Exception:
            text_parts.append("")
    text = "\n".join(text_parts)
    return ExtractionResult(text=text, method="ocr", page_count=len(images))


def extract_text_from_pdf(
    pdf_path: PathLike,
    *,
    use_ocr: bool = True,
    poppler_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
    tesseract_lang: str = "deu+eng",
    min_text_length: int = 50,
) -> Tuple[str, str]:
    """Extrahiert Text aus einer PDF-Datei und nutzt optional OCR als Fallback."""

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF nicht gefunden: {path}")

    result = _extract_with_pymupdf(path)
    text = result.text
    method = result.method

    if not text.strip():
        alt = _extract_with_pypdf2(path)
        if alt.text.strip():
            text = alt.text
            method = alt.method

    if use_ocr and len(text.strip()) < min_text_length:
        ocr_res = _extract_with_ocr(path, poppler_path, tesseract_cmd, tesseract_lang)
        if ocr_res.text.strip():
            text = ocr_res.text
            method = ocr_res.method

    return text, method


def extract_invoice_no(text: str, patterns: Sequence[str]) -> Optional[str]:
    if not text:
        return None
    for pattern in patterns:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        match = regex.search(text)
        if match:
            groups = [g for g in match.groups() if g]
            value = groups[0] if groups else match.group(0)
            if value:
                cleaned = re.sub(r"[^A-Z0-9\-_/]+", "", value.upper())
                return cleaned or value.strip()
    return None


def _normalize_date_candidate(candidate: str) -> Optional[str]:
    candidate = candidate.strip()
    if not candidate:
        return None
    candidate = candidate.replace("\\", ".")
    candidate = re.sub(r"[\s]+", "", candidate)
    formats = [
        "%d.%m.%Y",
        "%d.%m.%y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y.%m.%d",
        "%Y%m%d",
        "%d%m%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(candidate, fmt)
            if dt.year < 1900 or dt.year > 2100:
                continue
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Heuristik: ersetze verschiedene Trenner mit '-'
    cleaned = re.sub(r"[./]", "-", candidate)
    parts = cleaned.split("-")
    if len(parts) == 3:
        a, b, c = parts
        try:
            if len(a) == 4:
                dt = datetime(int(a), int(b), int(c))
            elif len(c) == 4:
                dt = datetime(int(c), int(b), int(a))
            else:
                dt = datetime(int(c), int(b), int(a))
            if 1900 <= dt.year <= 2100:
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def extract_date(text: str, patterns: Sequence[str]) -> Optional[str]:
    if not text:
        return None
    for pattern in patterns:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        for match in regex.finditer(text):
            groups = [g for g in match.groups() if g]
            candidate = groups[0] if groups else match.group(0)
            norm = _normalize_date_candidate(candidate)
            if norm:
                return norm
    return None


def detect_supplier(text: str, hints: Mapping[str, Sequence[str]]) -> Optional[str]:
    if not text or not hints:
        return None
    lower = text.lower()
    best_supplier = None
    best_score = 0
    for supplier, keywords in hints.items():
        score = 0
        for keyword in keywords or []:
            if not keyword:
                continue
            if keyword.lower() in lower:
                score += 1
        if score > best_score:
            best_supplier = supplier
            best_score = score
    return best_supplier


def extract_supplier_name(
    text: str,
    patterns: Mapping[str, Sequence[str]],
    supplier_hint: Optional[str] = None,
) -> Optional[str]:
    if not text or not patterns:
        return None

    search_order: List[str] = []
    if supplier_hint:
        search_order.append(supplier_hint)
    for key in patterns.keys():
        if key not in search_order:
            search_order.append(key)

    for key in search_order:
        for pattern in patterns.get(key, []) or []:
            if not pattern:
                continue
            try:
                regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            except re.error:
                continue
            match = regex.search(text)
            if not match:
                continue
            if match.lastindex:
                for idx in range(1, match.lastindex + 1):
                    group = match.group(idx)
                    if group:
                        candidate = group.strip()
                        if candidate:
                            return candidate
            candidate = match.group(0).strip()
            if candidate:
                return candidate
    return None


def analyze_pdf(
    pdf_path: PathLike,
    *,
    patterns_path: Optional[PathLike] = None,
    config: Optional[Mapping[str, object]] = None,
    patterns: Optional[Mapping[str, object]] = None,
) -> Dict[str, object]:
    cfg = load_config(config)
    pats = load_patterns(patterns if patterns is not None else patterns_path)
    text, method = extract_text_from_pdf(
        pdf_path,
        use_ocr=bool(cfg.get("use_ocr", True)),
        poppler_path=str(cfg.get("poppler_path") or "") or None,
        tesseract_cmd=str(cfg.get("tesseract_cmd") or "") or None,
        tesseract_lang=str(cfg.get("tesseract_lang") or "deu+eng"),
    )
    invoice_no = extract_invoice_no(text, pats.get("invoice_number_patterns", []) or [])
    invoice_date = extract_date(text, pats.get("date_patterns", []) or [])
    supplier_hint = detect_supplier(text, pats.get("supplier_hints", {}) or {})
    supplier_name = extract_supplier_name(
        text,
        pats.get("supplier_patterns", {}) or {},
        supplier_hint,
    )

    unknown_dir_name = str(cfg.get("unknown_dir_name") or DEFAULT_CONFIG["unknown_dir_name"])
    supplier_candidate = supplier_name or supplier_hint
    supplier_value = str(supplier_candidate or unknown_dir_name)

    supplier_detected = bool(supplier_candidate)
    validation_status = "ok" if (invoice_no and invoice_date and supplier_detected) else "needs_review"
    result: Dict[str, object] = {
        "source": str(pdf_path),
        "invoice_no": invoice_no,
        "invoice_date": invoice_date,
        "supplier": supplier_value,
        "supplier_key": supplier_hint,
        "supplier_name": supplier_name,
        "supplier_detected": supplier_detected,
        "text_method": method,
        "text_length": len(text),
        "validation_status": validation_status,
    }
    return result


def process_pdf(
    pdf_path: PathLike,
    *,
    config_path: Optional[PathLike] = None,
    patterns_path: Optional[PathLike] = None,
    config: Optional[Mapping[str, object]] = None,
    patterns: Optional[Mapping[str, object]] = None,
    simulate: Optional[bool] = None,
) -> Dict[str, object]:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF nicht gefunden: {path}")

    cfg = load_config(config if config is not None else config_path)
    pats = load_patterns(patterns if patterns is not None else patterns_path)

    analysis = analyze_pdf(path, config=cfg, patterns=pats)

    unknown_dir_name = str(cfg.get("unknown_dir_name") or DEFAULT_CONFIG["unknown_dir_name"])
    output_dir = Path(str(cfg.get("output_dir") or DEFAULT_CONFIG["output_dir"]))

    supplier_folder = _sanitize_component(analysis.get("supplier", "")) or _sanitize_component(unknown_dir_name) or "unbekannt"
    target_dir = output_dir / supplier_folder

    date_value = analysis.get("invoice_date") or datetime.now().strftime("%Y-%m-%d")
    supplier_value = supplier_folder
    invoice_no = analysis.get("invoice_no") or ""

    fmt = str(cfg.get("output_filename_format") or DEFAULT_CONFIG["output_filename_format"])
    values = {
        "date": date_value,
        "supplier": supplier_value,
        "invoice_no": invoice_no,
        "original_name": path.stem,
    }
    try:
        filename = fmt.format(**values)
    except KeyError:
        fallback_fmt = DEFAULT_CONFIG["output_filename_format"]
        filename = str(fallback_fmt).format(**values)
    filename = _ensure_filename(filename)

    target_path = _unique_path(target_dir, filename)

    effective_simulate = simulate if simulate is not None else bool(cfg.get("dry_run", False))
    moved = False
    if not effective_simulate:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target_path))
        moved = True

    result = dict(analysis)
    result.update(
        {
            "target": str(target_path),
            "destination": str(target_path),
            "output_path": str(target_path),
            "dest": str(target_path),
            "target_path": str(target_path),
            "destination_path": str(target_path),
            "resolved_path": str(target_path),
            "moved_path": str(target_path),
            "status": result.get("validation_status"),
            "simulate": effective_simulate,
            "moved": moved,
            "original_filename": path.name,
            "supplier": supplier_value,
        }
    )
    return result


def process_all(
    config_path: Optional[PathLike] = None,
    patterns_path: Optional[PathLike] = None,
    *,
    stop_fn: Optional[Callable[[], bool]] = None,
    progress_fn: Optional[Callable[[int, int, str, object], None]] = None,
    log_csv_path: Optional[PathLike] = None,
    config: Optional[Mapping[str, object]] = None,
    patterns: Optional[Mapping[str, object]] = None,
    simulate: Optional[bool] = None,
) -> None:
    cfg = load_config(config if config is not None else config_path)
    pats = load_patterns(patterns if patterns is not None else patterns_path)

    input_dir = Path(str(cfg.get("input_dir") or DEFAULT_CONFIG["input_dir"]))
    output_dir = Path(str(cfg.get("output_dir") or DEFAULT_CONFIG["output_dir"]))
    unknown_dir_name = str(cfg.get("unknown_dir_name") or DEFAULT_CONFIG["unknown_dir_name"])
    unknown_dir = output_dir / (_sanitize_component(unknown_dir_name) or "unbekannt")

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    unknown_dir.mkdir(parents=True, exist_ok=True)

    effective_simulate = simulate if simulate is not None else bool(cfg.get("dry_run", False))

    files = sorted(p for p in input_dir.glob("*.pdf") if p.is_file())
    total = len(files)

    csv_path = Path(str(log_csv_path or cfg.get("csv_log_path") or "")).expanduser()
    csv_file = None
    csv_writer = None
    if csv_path and csv_path.name:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = csv_path.open("a", encoding="utf-8", newline="")
        csv_writer = csv.writer(csv_file, delimiter=";")
        if csv_path.stat().st_size == 0:
            csv_writer.writerow(
                [
                    "timestamp",
                    "source",
                    "destination",
                    "invoice_no",
                    "supplier",
                    "invoice_date",
                    "status",
                ]
            )
            csv_file.flush()

    try:
        for idx, pdf in enumerate(files, start=1):
            if stop_fn and stop_fn():
                break
            try:
                result = process_pdf(
                    pdf,
                    config=cfg,
                    patterns=pats,
                    simulate=effective_simulate,
                )
            except Exception as exc:
                target_path = unknown_dir / pdf.name
                if not effective_simulate:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.move(str(pdf), str(target_path))
                    except Exception:
                        target_path = pdf
                result = {
                    "source": str(pdf),
                    "invoice_no": None,
                    "invoice_date": None,
                    "supplier": unknown_dir_name,
                    "validation_status": "fail",
                    "status": "fail",
                    "target_path": str(target_path),
                    "destination": str(target_path),
                    "error": str(exc),
                }
            if progress_fn:
                try:
                    progress_fn(idx, total, str(pdf), SimpleNamespace(**result))
                except Exception:
                    pass
            if csv_writer:
                csv_writer.writerow(
                    [
                        datetime.now().isoformat(timespec="seconds"),
                        str(pdf),
                        result.get("destination") or result.get("target_path"),
                        result.get("invoice_no"),
                        result.get("supplier"),
                        result.get("invoice_date"),
                        result.get("validation_status") or result.get("status"),
                    ]
                )
                csv_file.flush()
    finally:
        if csv_file:
            csv_file.close()


__all__ = [
    "load_config",
    "load_patterns",
    "extract_text_from_pdf",
    "extract_invoice_no",
    "extract_date",
    "detect_supplier",
    "extract_supplier_name",
    "analyze_pdf",
    "process_pdf",
    "process_all",
]
