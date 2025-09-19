
import os
import re
import sys
import shutil
import unicodedata
import pathlib
import json
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Callable

import yaml
import pdfplumber
from dateutil import parser as dateparser

# OCR/Scan-Support (werden nur benutzt, wenn use_ocr True ist)
try:
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import Image
except Exception:
    convert_from_path = None
    pytesseract = None
    Image = None

@dataclass
class InvoiceData:
    invoice_no: Optional[str]
    supplier: Optional[str]
    invoice_date: Optional[datetime]

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def normalize_supplier_name(name: str) -> str:
    if not name:
        return "unbekannt"
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_only = "".join([c for c in nfkd if not unicodedata.combining(c)])
    cleaned = re.sub(r"[^A-Za-z0-9\- ]+", "", ascii_only).strip()
    return cleaned or "unbekannt"

def safe_filename(s: str) -> str:
    s = s.replace(" ", "_")
    s = re.sub(r"[\\/:*?\"<>|]+", "-", s)
    return s

def extract_text_from_pdf(pdf_path: str, use_ocr: bool, poppler_path: Optional[str], tesseract_cmd: Optional[str], tesseract_lang: str = "deu+eng") -> str:
    text_chunks: List[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    text_chunks.append(t)
    except Exception as e:
        print(f"[WARN] pdfplumber konnte {pdf_path} nicht lesen: {e}")

    joined_text = "\n".join(text_chunks).strip()
    if joined_text:
        return joined_text

    if not use_ocr:
        return ""

    if convert_from_path is None or pytesseract is None:
        print("[WARN] OCR benötigt pdf2image + pytesseract. Bitte installieren/konfigurieren.")
        return ""

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
        ocr_chunks = []
        for img in images:
            txt = pytesseract.image_to_string(img, lang=tesseract_lang or "deu+eng") or ""
            if txt.strip():
                ocr_chunks.append(txt)
        return "\n".join(ocr_chunks).strip()
    except Exception as e:
        print(f"[WARN] OCR fehlgeschlagen für {pdf_path}: {e}")
        return ""

def load_patterns(patterns_yaml_path: str) -> Dict:
    with open(patterns_yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def extract_invoice_no(text: str, patterns: List[str]) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            candidate = m.group(1).strip()
            if len(candidate) >= 4:
                return candidate
    return None

def parse_date_soft(s: str) -> Optional[datetime]:
    for dayfirst in (True, False):
        try:
            dt = dateparser.parse(s, dayfirst=dayfirst, yearfirst=not dayfirst, fuzzy=True)
            if dt:
                return dt
        except Exception:
            continue
    return None

def extract_date(text: str, date_patterns: List[str]) -> Optional[datetime]:
    for pat in date_patterns:
        for m in re.finditer(pat, text):
            raw = m.group(1).strip()
            dt = parse_date_soft(raw)
            if dt:
                return dt
    tokens = re.findall(r"[0-9./\-]{8,10}", text)
    for tok in tokens:
        dt = parse_date_soft(tok)
        if dt:
            return dt
    return None

def detect_supplier(text: str, supplier_hints: Dict[str, List[str]]) -> Optional[str]:
    lower = text.lower()
    best_match = None
    best_len = 0
    for supplier, hints in supplier_hints.items():
        for h in hints:
            if h.lower() in lower and len(h) > best_len:
                best_match = supplier
                best_len = len(h)
    if not best_match:
        m = re.search(r"(?im)^(.*?(gmbh|ag|kg|ug|gbr|inc|ltd|co\.?|firma).{0,40})$", text)
        if m:
            best_match = m.group(1)
    return best_match

def ollama_enrich(text: str, host: str, model: str, missing_fields: List[str]) -> Dict[str, Optional[str]]:
    try:
        import requests
    except ImportError:
        print("[INFO] 'requests' nicht installiert; Ollama-Fallback übersprungen.")
        return {}

    system = (
        "Du extrahierst strukturierte Rechnungsdaten als JSON. Felder: "
        "invoice_no (string), supplier (string), date (YYYY-MM-DD). "
        "Antworte NUR mit JSON. Wenn unsicher, null."
    )
    user = (
        "Textauszug einer Rechnung:\n"
        f"---\n{text[:6000]}\n---\n"
        f"Fehlende Felder: {', '.join(missing_fields)}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }

    try:
        resp = requests.post(f"{host}/v1/chat/completions", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        try:
            j = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.S)
            j = json.loads(m.group(0)) if m else {}
        return {
            "invoice_no": j.get("invoice_no"),
            "supplier": j.get("supplier"),
            "date": j.get("date"),
        }
    except Exception as e:
        print(f"[INFO] Ollama-Fallback fehlgeschlagen: {e}")
        return {}

def extract_fields_for_file(pdf_path: str, cfg: Dict, pats: Dict) -> InvoiceData:
    txt = extract_text_from_pdf(
        pdf_path,
        use_ocr=cfg.get("use_ocr", True),
        poppler_path=cfg.get("poppler_path"),
        tesseract_cmd=cfg.get("tesseract_cmd"),
        tesseract_lang=cfg.get("tesseract_lang", "deu+eng"),
    )

    inv_no = extract_invoice_no(txt, pats.get("invoice_number_patterns", []))
    inv_date = extract_date(txt, pats.get("date_patterns", []))
    supplier = detect_supplier(txt, pats.get("supplier_hints", {}))

    missing = []
    if inv_no is None:
        missing.append("invoice_no")
    if supplier is None:
        missing.append("supplier")
    if inv_date is None:
        missing.append("date")

    if missing and cfg.get("use_ollama", False):
        o = ollama_enrich(
            text=txt,
            host=cfg["ollama"]["host"],
            model=cfg["ollama"]["model"],
            missing_fields=missing,
        )
        if inv_no is None and o.get("invoice_no"):
            inv_no = o["invoice_no"]
        if supplier is None and o.get("supplier"):
            supplier = o["supplier"]
        if inv_date is None and o.get("date"):
            try:
                inv_date = dateparser.parse(o["date"])
            except Exception:
                pass

    return InvoiceData(invoice_no=inv_no, supplier=supplier, invoice_date=inv_date)

def build_target_path(data: InvoiceData, output_dir: str, unknown_dir_name: str) -> Tuple[str, str]:
    if data.invoice_date and data.supplier and data.invoice_no:
        date_str = data.invoice_date.strftime("%Y-%m-%d")
        supplier_clean = normalize_supplier_name(data.supplier)
        filename = f"{date_str}_{supplier_clean}_Re-{safe_filename(data.invoice_no)}.pdf"
        year = data.invoice_date.strftime("%Y")
        folder = os.path.join(output_dir, year, supplier_clean)
    else:
        filename = f"{datetime.now().strftime('%Y-%m-%d')}_unbekannt_Re-unknown.pdf"
        folder = os.path.join(output_dir, unknown_dir_name)
    ensure_dir(folder)
    return folder, filename

def avoid_collision(path: str) -> str:
    if not os.path.exists(path):
        return path
    base = pathlib.Path(path)
    stem = base.stem
    suffix = base.suffix
    i = 2
    while True:
        candidate = base.with_name(f"{stem}({i}){suffix}")
        if not candidate.exists():
            return str(candidate)
        i += 1

def append_csv(csv_path: str, row: Dict[str, str]) -> None:
    import csv
    new_file = not os.path.exists(csv_path)
    ensure_dir(os.path.dirname(csv_path))
    with open(csv_path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "timestamp", "source_file", "target_file", "invoice_no", "supplier", "date", "method"
        ])
        if new_file:
            writer.writeheader()
        writer.writerow(row)

def is_pdf(path: str) -> bool:
    return path.lower().endswith(".pdf")

def process_all(cfg_path: str, patterns_path: str,
                stop_fn: Optional[Callable[[], bool]] = None,
                progress_fn: Optional[Callable[[int, int, str, Optional[InvoiceData]], None]] = None) -> None:
    """
    Orchestriert: Dateien lesen, extrahieren, umbenennen, verschieben.
    - stop_fn(): soll True zurückgeben, wenn der Prozess sanft abbrechen soll
    - progress_fn(i, n, filename, data): Fortschritt melden (1-basiert)
    """
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    input_dir = cfg["input_dir"]
    output_dir = cfg["output_dir"]
    unknown_dir = cfg.get("unknown_dir_name", "unbekannt")
    dry_run = cfg.get("dry_run", False)
    csv_log_path = cfg.get("csv_log_path")

    pats = load_patterns(patterns_path)

    ensure_dir(output_dir)
    ensure_dir(os.path.join(output_dir, unknown_dir))

    all_entries = sorted(os.listdir(input_dir)) if os.path.isdir(input_dir) else []
    files = [os.path.join(input_dir, f) for f in all_entries if is_pdf(f)]
    total = len(files)
    if total == 0:
        print("[INFO] Keine PDF-Dateien gefunden.")
        return

    for idx, fpath in enumerate(files, start=1):
        if stop_fn and stop_fn():
            print("[INFO] Stop angefordert – Abbruch nach aktuellem Schritt.")
            break
        print(f"\n=== Verarbeite: {os.path.basename(fpath)} ({idx}/{total}) ===")
        data: Optional[InvoiceData] = None
        try:
            data = extract_fields_for_file(fpath, cfg, pats)
            print(f"  → Rechnungsnummer: {data.invoice_no}")
            print(f"  → Lieferant:      {data.supplier}")
            print(f"  → Rechnungsdatum: {data.invoice_date.strftime('%Y-%m-%d') if data.invoice_date else None}")

            target_folder, target_name = build_target_path(data, output_dir, unknown_dir)
            target_path = os.path.join(target_folder, target_name)
            target_path = avoid_collision(target_path)

            if dry_run:
                print(f"  (Dry-Run) Ziel: {target_path}")
                method = "dry"
            else:
                shutil.move(fpath, target_path)
                print(f"  ✓ Verschoben nach: {target_path}")
                method = "text/ocr/ollama"

            if csv_log_path:
                append_csv(csv_log_path, {
                    "timestamp": datetime.now().isoformat(timespec='seconds'),
                    "source_file": os.path.basename(fpath),
                    "target_file": os.path.basename(target_path),
                    "invoice_no": data.invoice_no or "",
                    "supplier": data.supplier or "",
                    "date": data.invoice_date.strftime('%Y-%m-%d') if data.invoice_date else "",
                    "method": method,
                })

        except Exception as e:
            unk_folder = os.path.join(output_dir, unknown_dir)
            ensure_dir(unk_folder)
            target_path = avoid_collision(os.path.join(
                unk_folder,
                f"{datetime.now().strftime('%Y-%m-%d')}_unbekannt_Re-error.pdf"
            ))
            if not dry_run:
                try:
                    shutil.move(fpath, target_path)
                except Exception as e2:
                    print(f"  ! Konnte Datei nicht verschieben (zusätzlicher Fehler): {e2}")
            print(f"  ! Fehler: {e}")
            print(f"  → Datei nach 'unbekannt' verschoben: {target_path}")
            if csv_log_path:
                append_csv(csv_log_path, {
                    "timestamp": datetime.now().isoformat(timespec='seconds'),
                    "source_file": os.path.basename(fpath),
                    "target_file": os.path.basename(target_path),
                    "invoice_no": "",
                    "supplier": "",
                    "date": "",
                    "method": "error",
                })
        finally:
            if progress_fn:
                try:
                    progress_fn(idx, total, os.path.basename(fpath), data)
                except Exception:
                    pass

if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    pats_path = sys.argv[2] if len(sys.argv) > 2 else "patterns.yaml"
    process_all(cfg_path, pats_path)
