"""Sorter-Modul mit OCR-Unterstützung und Metadaten-Extraktion."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml


@dataclass
class AnalysisResult:
    source: str
    supplier: Optional[str]
    invoice_no: Optional[str]
    invoice_date: Optional[str]
    method: str
    validation_status: str
    missing_fields: List[str]
    text_length: int
    status_reason: Optional[str] = None


def _read_yaml(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    cfg_path = Path(path)
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
        if isinstance(data, dict):
            return data
    return {}


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    return _read_yaml(config_path)


def load_patterns(patterns_path: Optional[str]) -> Dict[str, Any]:
    data = _read_yaml(patterns_path)
    data.setdefault("invoice_number_patterns", [])
    data.setdefault("date_patterns", [])
    data.setdefault("supplier_hints", {})
    return data


def _unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _extract_with_module(path: Path) -> Tuple[str, str]:
    text = ""
    method = ""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(path)
        try:
            parts = [page.get_text("text") for page in doc]
        finally:
            doc.close()
        text = "\n".join(parts)
        method = "pymupdf"
        if text.strip():
            return text, method
    except Exception:
        pass

    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        text = "\n".join(parts)
        method = "pypdf2"
    except Exception:
        text = ""
        method = ""
    return text, method


def _run_ocr(
    path: Path,
    lang: str,
    poppler_path: Optional[str],
    tesseract_cmd: Optional[str],
    max_pages: int = 3,
) -> Tuple[str, str]:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception:
        return "", ""

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        images = convert_from_path(
            str(path),
            dpi=300,
            first_page=1,
            last_page=max_pages,
            poppler_path=poppler_path or None,
        )
    except Exception:
        return "", ""

    texts: List[str] = []
    for img in images:
        try:
            texts.append(pytesseract.image_to_string(img, lang=lang or "deu"))
        except Exception:
            continue
    joined = "\n".join(t.strip() for t in texts if t.strip())
    return joined, "ocr" if joined else ""


def extract_text_from_pdf(
    pdf_path: str,
    use_ocr: bool = True,
    poppler_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
    tesseract_lang: str = "deu+eng",
    min_text_length: int = 80,
) -> Tuple[str, str]:
    path = Path(pdf_path)
    base_text, method = _extract_with_module(path)
    base_text = base_text or ""
    text = base_text.strip()
    if text and len(text) >= min_text_length:
        return base_text, method or "pymupdf"

    if not use_ocr:
        return base_text, method or ""

    ocr_text, ocr_method = _run_ocr(path, tesseract_lang, poppler_path, tesseract_cmd)
    if ocr_text:
        combined_method = method + "+ocr" if method else "ocr"
        combined_text = base_text + "\n" + ocr_text if base_text else ocr_text
        return combined_text, combined_method
    return base_text, method or ""


def extract_invoice_no(text: str, patterns: Sequence[str]) -> Optional[str]:
    if not text:
        return None
    for pattern in patterns:
        try:
            regex = re.compile(pattern, flags=re.IGNORECASE | re.UNICODE)
        except re.error:
            continue
        match = regex.search(text)
        if match:
            value = match.group(1).strip()
            value = re.sub(r"\s+", "", value)
            return value or None
    return None


def _normalize_year(year: int) -> int:
    if year < 100:
        return 2000 + year if year < 50 else 1900 + year
    return year


def _normalize_date_value(raw: str) -> Optional[str]:
    raw = raw.strip()
    if not raw:
        return None
    cleaned = raw.replace("/", ".").replace("-", ".")
    parts = [p for p in cleaned.split(".") if p]
    if len(parts) != 3:
        return None
    if len(parts[0]) == 4:
        year = _normalize_year(int(parts[0]))
        month = int(parts[1])
        day = int(parts[2])
    else:
        day = int(parts[0])
        month = int(parts[1])
        year = _normalize_year(int(parts[2]))
    try:
        dt = datetime(year, month, day)
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d")


def extract_date(text: str, patterns: Sequence[str]) -> Optional[str]:
    if not text:
        return None
    for pattern in patterns:
        try:
            regex = re.compile(pattern, flags=re.IGNORECASE | re.UNICODE)
        except re.error:
            continue
        match = regex.search(text)
        if match:
            candidate = match.group(1)
            normalized = _normalize_date_value(candidate)
            if normalized:
                return normalized
    return None


def detect_supplier(text: str, hints: Dict[str, Iterable[str]]) -> Optional[str]:
    if not text:
        return None
    haystack = text.lower()
    for supplier, keywords in hints.items():
        for keyword in keywords or []:
            if keyword and keyword.lower() in haystack:
                return supplier
    return None


def _sanitize_component(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r"[\\/:*?\"<>|]", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("._")


def analyze_pdf(
    pdf_path: str,
    *,
    patterns_path: Optional[str] = None,
    patterns: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> AnalysisResult:
    cfg = config or {}
    pats = patterns or load_patterns(patterns_path)

    use_ocr = bool(cfg.get("use_ocr", True))
    poppler_path = cfg.get("poppler_path")
    tesseract_cmd = cfg.get("tesseract_cmd")
    tesseract_lang = cfg.get("tesseract_lang", "deu+eng")

    text, method = extract_text_from_pdf(
        pdf_path,
        use_ocr=use_ocr,
        poppler_path=poppler_path,
        tesseract_cmd=tesseract_cmd,
        tesseract_lang=tesseract_lang,
    )

    invoice_no = extract_invoice_no(text, pats.get("invoice_number_patterns", []))
    invoice_date = extract_date(text, pats.get("date_patterns", []))
    supplier = detect_supplier(text, pats.get("supplier_hints", {}))

    missing = []
    if not supplier:
        missing.append("supplier")
    if not invoice_no:
        missing.append("invoice_no")
    if not invoice_date:
        missing.append("invoice_date")

    if not text.strip():
        missing.append("text")
        status = "fail"
        reason = "Kein Text extrahiert"
    elif missing:
        status = "needs_review"
        reason = ", ".join(_unique_preserve_order(missing))
    else:
        status = "ok"
        reason = None

    return AnalysisResult(
        source=str(pdf_path),
        supplier=supplier,
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        method=method or "",
        validation_status=status,
        missing_fields=_unique_preserve_order(missing),
        text_length=len(text),
        status_reason=reason,
    )


def _build_target_path(
    pdf: Path,
    cfg: Dict[str, Any],
    analysis: AnalysisResult,
) -> Tuple[Path, str]:
    output_dir = Path(cfg.get("output_dir") or "processed")
    unknown_name = cfg.get("unknown_dir_name") or "unbekannt"

    supplier_component = _sanitize_component(analysis.supplier) or unknown_name
    target_dir = output_dir / supplier_component
    target_dir.mkdir(parents=True, exist_ok=True)

    filename_format = cfg.get("output_filename_format")
    data = {
        "supplier": _sanitize_component(analysis.supplier) or "unknown",
        "invoice_no": _sanitize_component(analysis.invoice_no) or "unknown",
        "date": analysis.invoice_date or "unknown",
        "original_name": pdf.stem,
    }
    if not filename_format:
        filename_format = "{date}_{supplier}_{invoice_no}.pdf"

    try:
        filename = filename_format.format(**data)
    except Exception:
        filename = pdf.name
    else:
        filename = filename.strip()
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        filename = re.sub(r"[\\/:*?\"<>|]", "_", filename)
        filename = re.sub(r"_+", "_", filename).strip("._") or pdf.stem + ".pdf"

    target_path = target_dir / filename
    counter = 1
    while target_path.exists():
        candidate = target_dir / f"{target_path.stem}_{counter}{target_path.suffix}"
        counter += 1
        target_path = candidate
    return target_path, supplier_component


def process_pdf(
    pdf_path: str,
    *,
    config_path: Optional[str] = None,
    patterns_path: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    patterns: Optional[Dict[str, Any]] = None,
    simulate: Optional[bool] = None,
) -> Dict[str, Any]:
    pdf = Path(pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(pdf_path)

    cfg = dict(load_config(config_path))
    if config:
        cfg.update(config)
    pats = patterns or load_patterns(patterns_path)

    if simulate is None:
        simulate = bool(cfg.get("dry_run", False))

    analysis = analyze_pdf(str(pdf), patterns=pats, config=cfg)

    output_dir = Path(cfg.get("output_dir") or "processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path, supplier_component = _build_target_path(pdf, cfg, analysis)

    moved_path = str(target_path)
    error: Optional[str] = None

    if not simulate:
        try:
            pdf.rename(target_path)
        except Exception:
            # rename can fail across volumes – fall back to copy + unlink
            import shutil

            try:
                shutil.copy2(str(pdf), str(target_path))
                pdf.unlink()
            except Exception as exc:
                error = str(exc)
    status = analysis.validation_status
    if error:
        status = "fail"
        moved_path = str(pdf)

    result = {
        "source": str(pdf_path),
        "target": moved_path,
        "moved_path": moved_path,
        "destination": moved_path,
        "supplier": analysis.supplier,
        "supplier_folder": supplier_component,
        "invoice_no": analysis.invoice_no,
        "invoice_date": analysis.invoice_date,
        "validation_status": status,
        "status": status,
        "missing_fields": analysis.missing_fields,
        "status_reason": analysis.status_reason,
        "method": analysis.method,
        "simulation": bool(simulate),
    }
    if error:
        result["error"] = error
        result["status_reason"] = error
    return result


def process_all(
    config_path: Optional[str],
    patterns_path: Optional[str],
    stop_fn: Optional[Callable[[], bool]] = None,
    progress_fn: Optional[Callable[[int, int, str, Any], None]] = None,
) -> List[Dict[str, Any]]:
    cfg = load_config(config_path)
    pats = load_patterns(patterns_path)

    input_dir = Path(cfg.get("input_dir") or "inbox")
    output_dir = Path(cfg.get("output_dir") or "processed")
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    total = len(files)

    csv_writer = None
    csv_file = None
    csv_path = cfg.get("csv_log_path")
    if csv_path:
        path = Path(csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = path.open("a", encoding="utf-8", newline="")
        csv_writer = csv.writer(csv_file, delimiter=";")
        if path.stat().st_size == 0:
            csv_writer.writerow(
                [
                    "src",
                    "target",
                    "supplier",
                    "invoice_no",
                    "date",
                    "total",
                    "iban",
                    "status",
                    "method",
                    "ts",
                ]
            )

    results: List[Dict[str, Any]] = []
    try:
        for idx, pdf in enumerate(files, start=1):
            if stop_fn and stop_fn():
                break
            try:
                res = process_pdf(
                    str(pdf),
                    config=cfg,
                    patterns=pats,
                    simulate=None,
                )
            except Exception as exc:
                res = {
                    "source": str(pdf),
                    "target": str(pdf),
                    "supplier": None,
                    "invoice_no": None,
                    "invoice_date": None,
                    "validation_status": "fail",
                    "missing_fields": ["exception"],
                    "status_reason": str(exc),
                    "method": "",
                    "error": str(exc),
                }
            results.append(res)
            if progress_fn:
                try:
                    progress_fn(idx, total, str(pdf), SimpleNamespace(**res))
                except Exception:
                    pass
            if csv_writer:
                csv_writer.writerow(
                    [
                        res.get("source"),
                        res.get("target"),
                        res.get("supplier"),
                        res.get("invoice_no"),
                        res.get("invoice_date"),
                        "",
                        "",
                        res.get("validation_status"),
                        res.get("method"),
                        datetime.now().isoformat(timespec="seconds"),
                    ]
                )
        return results
    finally:
        if csv_file:
            csv_file.close()
