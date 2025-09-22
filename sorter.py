from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency error
    raise RuntimeError("PyYAML is required to load configuration files") from exc

# Optional dependencies -----------------------------------------------------
try:  # pragma: no cover - optional dependency
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - dependency missing
    fitz = None

try:  # pragma: no cover - optional dependency
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:  # pragma: no cover - dependency missing
    pdfminer_extract_text = None

try:  # pragma: no cover - optional dependency
    from pdf2image import convert_from_path
except Exception:  # pragma: no cover - dependency missing
    convert_from_path = None

try:  # pragma: no cover - optional dependency
    import pytesseract
except Exception:  # pragma: no cover - dependency missing
    pytesseract = None

try:  # pragma: no cover - optional dependency
    import requests  # noqa: F401 - imported for side effects in original project
except Exception:  # pragma: no cover - dependency missing
    requests = None  # type: ignore


LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_FILENAME_FORMAT = "{date}_{supplier_safe}_{invoice_no_safe}_{hash_short}.pdf"
DEFAULT_UNKNOWN_SUPPLIER = "unknown"
DEFAULT_TESSERACT_LANG = "deu+eng"


# ---------------------------------------------------------------------------
# Dataclasses & public API helpers
# ---------------------------------------------------------------------------
@dataclass
class ExtractResult:
    """Container for the outcome of :func:`process_pdf`."""

    source_file: str
    target_file: Optional[str]
    invoice_no: Optional[str]
    supplier: Optional[str]
    invoice_date: Optional[str]
    method: Optional[str]
    hash_md5: Optional[str]
    confidence: float
    validation_status: str
    gross: Optional[float] = None
    net: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"YAML file does not contain a mapping: {path}")
        return data


def load_config(config: Any = None) -> Dict[str, Any]:
    """Return configuration as dictionary.

    ``config`` may already be a mapping, a path to a YAML file or ``None``.
    ``None`` returns an empty dictionary.
    """

    if config is None:
        return {}
    if isinstance(config, dict):
        return dict(config)
    path = Path(config)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    cfg = _load_yaml(path)
    cfg.setdefault("input_dir", str(Path(path).parent))
    return cfg


def _merge_pattern_dict(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, list):
            dest = target.setdefault(key, [])
            for item in value:
                if item not in dest:
                    dest.append(item)
        elif isinstance(value, dict):
            dest = target.setdefault(key, {})
            if not isinstance(dest, dict):
                target[key] = dest = {}
            _merge_pattern_dict(dest, value)
        else:
            target[key] = value


def load_patterns(patterns: Any = None) -> Dict[str, Any]:
    """Load pattern configuration.

    Accepts a dict, a path to a YAML file, or a directory containing pattern
    files. Supplier specific definitions inside ``suppliers/*.yaml`` are
    collected into the ``"suppliers"`` key.
    """

    result: Dict[str, Any] = {"suppliers": {}}

    def handle_file(path: Path, supplier: Optional[str] = None) -> None:
        try:
            data = _load_yaml(path)
        except Exception as exc:
            raise RuntimeError(f"Failed to read pattern file {path}: {exc}") from exc
        if supplier:
            suppliers = result.setdefault("suppliers", {})
            sup_dict = suppliers.setdefault(supplier, {})
            _merge_pattern_dict(sup_dict, data)
        else:
            _merge_pattern_dict(result, data)

    if patterns is None:
        default_file = Path("patterns.yaml")
        if default_file.exists():
            handle_file(default_file)
        return result

    if isinstance(patterns, dict):
        _merge_pattern_dict(result, patterns)
        return result

    path = Path(patterns)
    if path.is_file():
        handle_file(path)
        # auto-load sibling supplier folder if present
        suppliers_dir = path.parent / "suppliers"
        if suppliers_dir.is_dir():
            for sub in sorted(suppliers_dir.glob("*.yaml")):
                handle_file(sub, sub.stem.replace("_", " "))
        return result

    if not path.is_dir():
        raise FileNotFoundError(f"Pattern source not found: {path}")

    for entry in sorted(path.glob("*.yaml")):
        handle_file(entry)
    suppliers_dir = path / "suppliers"
    if suppliers_dir.is_dir():
        for sub in sorted(suppliers_dir.glob("*.yaml")):
            handle_file(sub, sub.stem.replace("_", " "))
    return result


def _safe_name(value: Optional[str]) -> str:
    if not value:
        return DEFAULT_UNKNOWN_SUPPLIER
    value = str(value).strip()
    if not value:
        return DEFAULT_UNKNOWN_SUPPLIER
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    cleaned = cleaned.strip("_._-")
    return cleaned or DEFAULT_UNKNOWN_SUPPLIER


def _sanitize_filename(name: str) -> str:
    name = name.replace("\x00", "")
    for sep in (os.sep, os.path.altsep):
        if sep:
            name = name.replace(sep, "_")
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return "output"
    return name[:180]


def _iter_output_filename_presets(presets: Any) -> Iterable[str]:
    if isinstance(presets, dict):
        for value in presets.values():
            if isinstance(value, str):
                candidate = value.strip()
                if candidate:
                    yield candidate
    elif isinstance(presets, Sequence) and not isinstance(presets, (str, bytes)):
        for item in presets:
            if isinstance(item, str):
                candidate = item.strip()
                if candidate:
                    yield candidate
            elif isinstance(item, dict):
                for key in ("pattern", "format", "template", "value"):
                    val = item.get(key)
                    if isinstance(val, str):
                        candidate = val.strip()
                        if candidate:
                            yield candidate
                            break
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                candidate = item[1]
                if isinstance(candidate, str):
                    candidate = candidate.strip()
                    if candidate:
                        yield candidate


def _resolve_output_filename_format(cfg: Dict[str, Any]) -> str:
    if isinstance(cfg, dict):
        fmt = cfg.get("output_filename_format")
        if isinstance(fmt, str) and fmt.strip():
            return fmt.strip()
        presets = cfg.get("output_filename_formats")
        for candidate in _iter_output_filename_presets(presets):
            return candidate
    return DEFAULT_OUTPUT_FILENAME_FORMAT


def _format_output_filename(fmt: str, meta: Dict[str, Any]) -> str:
    fmt = (fmt or DEFAULT_OUTPUT_FILENAME_FORMAT).strip()
    if not fmt:
        fmt = DEFAULT_OUTPUT_FILENAME_FORMAT

    safe_meta: Dict[str, Any] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (int, float)):
            safe_meta[key] = value
        else:
            safe_meta[key] = str(value)

    try:
        rendered = fmt.format_map(_FormatDict(safe_meta))
    except Exception:
        rendered = DEFAULT_OUTPUT_FILENAME_FORMAT.format_map(_FormatDict(safe_meta))

    rendered = _sanitize_filename(rendered)
    if not rendered.lower().endswith(".pdf"):
        rendered += ".pdf"
    return rendered


class _FormatDict(dict):
    def __missing__(self, key):  # pragma: no cover - trivial fallback
        return ""


def _first_match(text: str, patterns: Optional[Iterable[str]]) -> Optional[str]:
    if not text:
        return None
    for pat in patterns or []:
        try:
            match = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        except re.error as exc:
            LOGGER.warning("Invalid regex '%s': %s", pat, exc)
            continue
        if match:
            if match.groups():
                for group in match.groups():
                    if group:
                        return group.strip()
            return match.group(0).strip()
    return None


def _normalize_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    replacements = value.replace("/", ".").replace("-", ".").replace(" ", ".")
    parts = [p for p in replacements.split(".") if p]
    try:
        if len(parts) == 3:
            if len(parts[0]) == 4:  # Y-M-D
                year, month, day = parts
            else:  # D-M-Y
                day, month, year = parts
            dt = date(int(year), int(month), int(day))
            return dt.isoformat()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def _year_from_iso(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(datetime.fromisoformat(value).year)
    except Exception:
        try:
            return str(date.fromisoformat(value).year)
        except Exception:
            return ""


def _parse_amount(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    cleaned = value.replace(".", "").replace(" ", "").replace("€", "").replace("EUR", "").strip()
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _detect_currency(text: str) -> Optional[str]:
    text_lower = text.lower()
    if "eur" in text_lower or "€" in text:
        return "EUR"
    if "$" in text_lower:
        return "USD"
    if "gbp" in text_lower or "£" in text:
        return "GBP"
    return None


def _detect_supplier_with_hints(text: str, hints: Dict[str, Iterable[str]]) -> Optional[str]:
    lower = text.lower()
    best_supplier = None
    best_score = -1
    for supplier, supplier_hints in (hints or {}).items():
        score = 0
        for hint in supplier_hints or []:
            if str(hint).lower() in lower:
                score += 1
        if score > best_score and score > 0:
            best_score = score
            best_supplier = supplier
    return best_supplier


def _collect_invoice_whitelist(patterns: Dict[str, Any], supplier: Optional[str]) -> List[str]:
    whitelist: List[str] = []
    invoice_map = (patterns.get("whitelist", {}) or {}).get("invoice_numbers", {})
    if isinstance(invoice_map, dict):
        for key in (supplier, "*", "default", "all"):
            if key and key in invoice_map and isinstance(invoice_map[key], list):
                whitelist.extend(invoice_map[key])
    suppliers = patterns.get("suppliers", {})
    if supplier and supplier in suppliers:
        sup_whitelist = suppliers[supplier].get("whitelist", {})
        if isinstance(sup_whitelist, dict):
            inv_numbers = sup_whitelist.get("invoice_numbers", {})
            if isinstance(inv_numbers, dict):
                for pats in inv_numbers.values():
                    if isinstance(pats, list):
                        whitelist.extend(pats)
    return whitelist


def _invoice_matches_whitelist(invoice_no: Optional[str], whitelist: Sequence[str]) -> bool:
    if not invoice_no:
        return True
    if not whitelist:
        return True
    for pat in whitelist:
        try:
            if re.fullmatch(pat, invoice_no):
                return True
        except re.error:
            continue
    return False


def _compute_md5(path: str, chunk_size: int = 1024 * 1024) -> str:
    md5 = hashlib.md5()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def _ensure_unique_filename(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for idx in range(1, 1000):
        candidate = path.with_name(f"{stem}_{idx}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to create unique filename for {path}")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------
def extract_text_from_pdf(
    pdf_path: str,
    *,
    use_ocr: bool = True,
    poppler_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
    tesseract_lang: str = DEFAULT_TESSERACT_LANG,
) -> Tuple[str, str]:
    """Extract text from *pdf_path* using available backends."""

    errors: List[str] = []

    if fitz is not None:
        try:
            text_parts: List[str] = []
            with fitz.open(pdf_path) as doc:  # pragma: no cover - requires optional dep
                for page in doc:
                    text_parts.append(page.get_text("text"))
            text = "\n".join(text_parts)
            if text.strip():
                return text, "pymupdf"
        except Exception as exc:  # pragma: no cover - optional dep
            errors.append(f"PyMuPDF: {exc}")

    if pdfminer_extract_text is not None:
        try:
            text = pdfminer_extract_text(pdf_path)  # pragma: no cover - optional dep
            if text and text.strip():
                return text, "pdfminer"
        except Exception as exc:  # pragma: no cover - optional dep
            errors.append(f"pdfminer: {exc}")

    if use_ocr and convert_from_path is not None and pytesseract is not None:
        try:  # pragma: no cover - optional dep
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
            text_pages = [pytesseract.image_to_string(img, lang=tesseract_lang or DEFAULT_TESSERACT_LANG) for img in images]
            text = "\n".join(text_pages)
            if text.strip():
                return text, "ocr"
        except Exception as exc:
            errors.append(f"ocr: {exc}")

    message = "; ".join(errors) if errors else "no extraction backend available"
    raise RuntimeError(f"Failed to extract text from {pdf_path}: {message}")


# ---------------------------------------------------------------------------
# Analysis logic
# ---------------------------------------------------------------------------
def analyze_pdf(
    pdf_path: str,
    cfg: Any = None,
    patterns: Any = None,
) -> Dict[str, Any]:
    """Analyse a PDF and return extracted metadata."""

    cfg_dict = load_config(cfg)
    patterns_dict = load_patterns(patterns)

    pdf_path = str(pdf_path)
    use_ocr = bool(cfg_dict.get("use_ocr", True))
    poppler_path = cfg_dict.get("poppler_path")
    tesseract_cmd = cfg_dict.get("tesseract_cmd")
    tesseract_lang = cfg_dict.get("tesseract_lang") or DEFAULT_TESSERACT_LANG

    text, method = extract_text_from_pdf(
        pdf_path,
        use_ocr=use_ocr,
        poppler_path=poppler_path,
        tesseract_cmd=tesseract_cmd,
        tesseract_lang=tesseract_lang,
    )

    supplier = _detect_supplier_with_hints(text, patterns_dict.get("supplier_hints", {}))
    suppliers_map = patterns_dict.get("suppliers", {}) or {}

    invoice_no = _first_match(text, patterns_dict.get("invoice_number_patterns"))
    date_raw = _first_match(text, patterns_dict.get("date_patterns"))
    gross_raw = _first_match(text, patterns_dict.get("total_gross_patterns"))
    net_raw = _first_match(text, patterns_dict.get("total_net_patterns"))
    tax_raw = _first_match(text, patterns_dict.get("tax_amount_patterns"))

    if supplier and supplier in suppliers_map:
        supplier_patterns = suppliers_map.get(supplier, {})
    else:
        supplier_patterns = None

    # Try supplier specific patterns when not yet found
    if suppliers_map:
        for sup_name, sup_patterns in suppliers_map.items():
            if not invoice_no:
                invoice_candidate = _first_match(text, sup_patterns.get("invoice_number_patterns"))
                if invoice_candidate:
                    invoice_no = invoice_candidate
                    supplier = supplier or sup_name
            if not date_raw:
                date_candidate = _first_match(text, sup_patterns.get("date_patterns"))
                if date_candidate:
                    date_raw = date_candidate
            if not gross_raw:
                gross_candidate = _first_match(text, sup_patterns.get("total_gross_patterns"))
                if gross_candidate:
                    gross_raw = gross_candidate
            if not net_raw:
                net_candidate = _first_match(text, sup_patterns.get("total_net_patterns"))
                if net_candidate:
                    net_raw = net_candidate
            if not tax_raw:
                tax_candidate = _first_match(text, sup_patterns.get("tax_amount_patterns"))
                if tax_candidate:
                    tax_raw = tax_candidate

    date_iso = _normalize_date(date_raw)
    gross = _parse_amount(gross_raw)
    net = _parse_amount(net_raw)
    tax = _parse_amount(tax_raw)
    currency = _detect_currency(text)

    today = date.today()
    validation_max_days = cfg_dict.get("validation_max_days", 370)
    status = "ok"
    reason = ""

    whitelist_patterns = _collect_invoice_whitelist(patterns_dict, supplier)
    if not _invoice_matches_whitelist(invoice_no, whitelist_patterns):
        status = "invalid_invoice_number"
        reason = "invoice number not allowed by whitelist"

    if status == "ok" and validation_max_days and validation_max_days > 0 and date_iso:
        try:
            invoice_dt = date.fromisoformat(date_iso)
            if invoice_dt > today + timedelta(days=1):
                status = "date_in_future"
                reason = "invoice date lies in the future"
            elif (today - invoice_dt).days > int(validation_max_days):
                status = "date_out_of_range"
                reason = "invoice date outside configured range"
        except Exception:
            pass

    required_fields = [invoice_no, supplier, date_iso]
    filled = sum(1 for item in required_fields if item)
    confidence = filled / len(required_fields) if required_fields else 0.0
    if status != "ok":
        confidence = min(confidence, 0.5)

    text_preview = "\n".join(text.splitlines()[:80])

    md5 = _compute_md5(pdf_path)
    base_name = Path(pdf_path).name
    base_stem = Path(pdf_path).stem

    target_subdir = supplier or cfg_dict.get("unknown_dir_name") or DEFAULT_UNKNOWN_SUPPLIER
    target_subdir_safe = _safe_name(target_subdir)
    output_dir = cfg_dict.get("output_dir")
    if output_dir:
        target_dir = str(Path(output_dir) / target_subdir_safe)
    else:
        target_dir = str(Path(pdf_path).parent / target_subdir_safe)

    result = {
        "text": text,
        "text_preview": text_preview,
        "invoice_no": invoice_no,
        "supplier": supplier,
        "date": date_iso,
        "method": method,
        "confidence": float(confidence),
        "status": status,
        "validation_status": status,
        "message": reason,
        "gross": gross,
        "net": net,
        "tax": tax,
        "gross_raw": gross_raw,
        "net_raw": net_raw,
        "tax_raw": tax_raw,
        "currency": currency,
        "hash_md5": md5,
        "hash_short": md5[:8],
        "original_name": base_stem,
        "original_name_safe": _safe_name(base_stem),
        "target_subdir": target_subdir,
        "target_subdir_safe": target_subdir_safe,
        "target_dir": target_dir,
        "year": _year_from_iso(date_iso),
        "date_year": _year_from_iso(date_iso),
        "original_name_ext": base_name,
    }
    return result


def stamp_pdf_with_front_page(source: str, target: str, meta: Dict[str, Any]) -> None:
    """Create a simple one-page cover sheet with metadata and append the PDF.

    If PyMuPDF is not available the file is simply copied.
    """

    if fitz is None:  # pragma: no cover - requires optional dependency
        shutil.copy2(source, target)
        return

    doc = fitz.open()
    page = doc.new_page()
    lines = ["Rechnung", ""]
    for key in ("supplier", "invoice_no", "date", "gross", "net", "tax"):
        if meta.get(key):
            value = meta[key]
            if isinstance(value, float):
                value = f"{value:.2f}"
            lines.append(f"{key}: {value}")
    page.insert_text((72, 72), "\n".join(lines), fontsize=12)

    try:
        with fitz.open(source) as src:  # pragma: no cover - optional dep
            doc.insert_pdf(src)
    except Exception:
        shutil.copy2(source, target)
        doc.close()
        return

    doc.save(target)
    doc.close()


def _append_csv(csv_path: str, result: ExtractResult) -> None:
    path = Path(csv_path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        if not exists:
            writer.writerow([
                "timestamp",
                "source",
                "target",
                "supplier",
                "invoice_no",
                "date",
                "status",
                "confidence",
            ])
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            result.source_file,
            result.target_file or "",
            result.supplier or "",
            result.invoice_no or "",
            result.invoice_date or "",
            result.validation_status,
            f"{result.confidence:.2f}",
        ])


# ---------------------------------------------------------------------------
# Processing logic
# ---------------------------------------------------------------------------
def process_pdf(
    pdf_path: str,
    cfg: Any = None,
    patterns: Any = None,
    *,
    simulate: Optional[bool] = None,
    dry_run: Optional[bool] = None,
    stamp_pdf: bool = False,
    csv_log_path: Optional[str] = None,
    write_side_effects: bool = True,
) -> ExtractResult:
    """Process a single PDF and optionally copy it to the configured target."""

    cfg_dict = load_config(cfg)
    patterns_dict = load_patterns(patterns)

    pdf_path = str(pdf_path)
    analysis = analyze_pdf(pdf_path, cfg_dict, patterns_dict)

    md5 = analysis.get("hash_md5") or _compute_md5(pdf_path)
    supplier = analysis.get("supplier") or DEFAULT_UNKNOWN_SUPPLIER
    invoice_no = analysis.get("invoice_no")
    date_iso = analysis.get("date")
    status = analysis.get("validation_status") or analysis.get("status") or "ok"
    confidence = float(analysis.get("confidence") or 0.0)

    simulate_flag = simulate if simulate is not None else None
    if dry_run is None:
        dry = bool(cfg_dict.get("dry_run", False)) if simulate_flag is None else simulate_flag
    else:
        dry = dry_run

    base_path = Path(pdf_path)
    base_name = base_path.name
    base_stem = base_path.stem

    output_dir = Path(cfg_dict.get("output_dir") or base_path.parent)
    target_subdir = analysis.get("target_subdir") or supplier or DEFAULT_UNKNOWN_SUPPLIER
    target_subdir_safe = _safe_name(target_subdir)
    target_dir = output_dir / target_subdir_safe

    fmt = _resolve_output_filename_format(cfg_dict)
    filename_meta = {
        "date": date_iso or "",
        "year": _year_from_iso(date_iso),
        "date_year": _year_from_iso(date_iso),
        "supplier": supplier,
        "supplier_safe": _safe_name(supplier),
        "invoice_no": invoice_no or "",
        "invoice_no_safe": _safe_name(invoice_no),
        "status": status,
        "validation_status": status,
        "method": analysis.get("method") or "",
        "confidence": confidence,
        "gross": analysis.get("gross"),
        "gross_value": analysis.get("gross"),
        "net": analysis.get("net"),
        "net_value": analysis.get("net"),
        "tax": analysis.get("tax"),
        "tax_value": analysis.get("tax"),
        "currency": analysis.get("currency") or "",
        "hash_md5": md5,
        "hash_short": md5[:8],
        "original_name": base_stem,
        "original_name_safe": _safe_name(base_stem),
        "target_dir": str(target_dir),
        "target_subdir": target_subdir,
        "target_subdir_safe": target_subdir_safe,
    }

    target_file = target_dir / _format_output_filename(fmt, filename_meta)

    if write_side_effects and not dry:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = _ensure_unique_filename(target_file)
        if stamp_pdf:
            try:
                stamp_pdf_with_front_page(pdf_path, str(target_file), analysis)
            except Exception as exc:
                LOGGER.warning("Stamping PDF failed (%s), falling back to copy", exc)
                shutil.copy2(pdf_path, target_file)
        else:
            shutil.copy2(pdf_path, target_file)
    else:
        target_file = target_file  # type: ignore[assignment]

    result = ExtractResult(
        source_file=pdf_path,
        target_file=str(target_file) if not dry else None,
        invoice_no=invoice_no,
        supplier=supplier,
        invoice_date=date_iso,
        method=analysis.get("method"),
        hash_md5=md5,
        confidence=confidence,
        validation_status=status,
        gross=analysis.get("gross"),
        net=analysis.get("net"),
        tax=analysis.get("tax"),
        currency=analysis.get("currency"),
        message=analysis.get("message"),
    )

    if csv_log_path:
        try:
            _append_csv(csv_log_path, result)
        except Exception as exc:
            LOGGER.warning("Failed to append CSV log '%s': %s", csv_log_path, exc)

    return result


def process_all(
    cfg: Any,
    patterns: Any = None,
    *,
    stop_callback: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, int, str, ExtractResult], None]] = None,
    simulate: Optional[bool] = None,
) -> List[ExtractResult]:
    """Process all PDFs in the configured input directory."""

    cfg_dict = load_config(cfg)
    patterns_dict = load_patterns(patterns)

    input_dir = Path(cfg_dict.get("input_dir") or ".")
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    pdf_paths = sorted(p for p in input_dir.glob("*.pdf") if p.is_file())
    total = len(pdf_paths)
    results: List[ExtractResult] = []

    csv_path = cfg_dict.get("csv_log_path")
    dry_run_cfg = bool(cfg_dict.get("dry_run", False))

    for index, pdf_file in enumerate(pdf_paths, start=1):
        if stop_callback and stop_callback():
            LOGGER.info("Processing aborted by stop callback at %s", pdf_file)
            break
        result = process_pdf(
            str(pdf_file),
            cfg_dict,
            patterns_dict,
            simulate=simulate if simulate is not None else dry_run_cfg,
            csv_log_path=csv_path,
        )
        results.append(result)
        if progress_callback:
            progress_callback(index, total, str(pdf_file), result)
        else:
            LOGGER.info("Processed %s -> %s", pdf_file.name, result.target_file or "<dry-run>")

    return results


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Process invoice PDFs")
    parser.add_argument("config", nargs="?", default="config.yaml", help="Path to the configuration YAML")
    parser.add_argument("patterns", nargs="?", default="patterns.yaml", help="Path to the pattern YAML or directory")
    parser.add_argument("--dry-run", action="store_true", help="Do not copy files, only analyse")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.dry_run:
        cfg["dry_run"] = True

    process_all(cfg, args.patterns)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI execution
    raise SystemExit(main())
