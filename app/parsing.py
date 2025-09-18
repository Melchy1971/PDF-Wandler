import re
from datetime import date
from dateutil import parser as dateparser
import yaml
from pathlib import Path

RE_DATE = re.compile(r"\b(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})\b")
RE_INVNO = re.compile(r"(?i)(rechnungs\s*nr\.?|rechnungsnummer|invoice\s*no\.?|rechnung\s*#|rechnungnr\.?)[\s:]*([A-Z0-9\-\./]{4,})")
LABELS_DATE = re.compile(r"(?i)(rechnungsdatum|invoice date|re\.?-datum|datum)\W{0,10}")

def parse_date_candidates(text: str):
    for m in RE_DATE.finditer(text):
        try:
            yield dateparser.parse(m.group(0), dayfirst=True, yearfirst=False).date()
        except Exception:
            continue

def find_invoice_date(text: str):
    for m in LABELS_DATE.finditer(text):
        tail = text[m.end(): m.end()+40]
        for d in parse_date_candidates(tail):
            return d, 0.9
    cand = [d for d in parse_date_candidates(text) if (2000 <= d.year <= 2100)]
    if cand:
        cand.sort(reverse=True)
        return cand[0], 0.6
    return None, 0.0

def find_invoice_no(text: str):
    m = RE_INVNO.search(text)
    if m:
        return m.group(2).strip(".:,; "), 0.85
    loose = re.findall(r"\b[A-Z0-9]{2,5}[-/][A-Z0-9]{2,6}[-/][0-9]{2,6}\b", text)
    if loose:
        return loose[0], 0.5
    return None, 0.0

def load_vendor_db(path: Path):
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        return data.get("vendors", [])
    except Exception:
        return []

def guess_supplier(ocr_df, text: str, vendors):
    candidate = text[:1500]
    if ocr_df is not None and len(ocr_df) > 0 and 'top' in ocr_df:
        top = ocr_df[ocr_df['top'] < (ocr_df['top'].max()*0.25)]
        if len(top) > 0 and 'text' in top:
            candidate = " ".join(top['text'].dropna().tolist())

    for v in vendors:
        for p in v.get('patterns', []):
            if re.search(p, candidate, re.IGNORECASE):
                return v['name'], 0.9

    lines = [ln.strip() for ln in candidate.splitlines() if ln.strip()]
    for ln in lines[:15]:
        if re.search(r"(?i)\b(gmbh|ag|kg|ug|mbh)\b", ln):
            return ln, 0.7
    for ln in text.splitlines()[:20]:
        if len(ln) > 3 and not re.search(r"(?i)rechnung|invoice|kunde|empfänger|empfaenger", ln):
            return ln.strip(), 0.4
    return None, 0.0
