
from __future__ import annotations

import os, re, csv, json, hashlib, shutil
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Dict, List, Callable, Set

# Optional libs
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:
    pdfminer_extract_text = None

try:
    from pdf2image import convert_from_path
except Exception:
    convert_from_path = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import requests
except Exception:
    requests = None

try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
except Exception:
    rl_canvas = None

try:
    from pypdf import PdfReader, PdfWriter
except Exception:
    PdfReader = None

DEFAULT_OUTPUT_FILENAME_FORMAT = "{date}_{supplier_safe}_Re-{date}"

@dataclass
class ExtractResult:
    source_file: str
    target_file: Optional[str]
    invoice_no: Optional[str]
    supplier: Optional[str]
    invoice_date: Optional[str]  # ISO YYYY-MM-DD
    method: str                   # 'text' | 'ocr' | 'ollama' | 'duplicate'
    hash_md5: str
    confidence: float             # 0..1
    validation_status: str        # 'ok' | 'needs_review' | 'fail' | 'duplicate'
    gross: Optional[float] = None
    net: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None
    message: Optional[str] = None

def ensure_dir(p: str):
    if p and not os.path.exists(p):
        os.makedirs(p, exist_ok=True)

def md5_of_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def load_patterns(patterns_path: str) -> Dict:
    import yaml, glob
    with open(patterns_path, 'r', encoding='utf-8') as f:
        base = yaml.safe_load(f) or {}
    profiles = {}
    sup_dir = os.path.join(os.path.dirname(patterns_path), 'suppliers')
    if os.path.isdir(sup_dir):
        for fp in sorted(glob.glob(os.path.join(sup_dir, '*.yaml'))):
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    data = yaml.safe_load(fh) or {}
                name = os.path.splitext(os.path.basename(fp))[0]
                profiles[name] = data
            except Exception:
                pass
    base['supplier_profiles'] = profiles
    return base

def extract_invoice_no(text: str, patterns: List[str]) -> Optional[str]:
    for rx in patterns or []:
        m = re.search(rx, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1) if m.groups() else m.group(0)
    return None

def extract_date(text: str, patterns: List[str]) -> Optional[str]:
    for rx in patterns or []:
        m = re.search(rx, text, re.IGNORECASE | re.MULTILINE)
        if not m: continue
        s = m.group(1) if m.groups() else m.group(0)
        s = s.strip().replace(' ', '').replace('\n','')
        fmts = ('%d.%m.%Y','%Y-%m-%d','%d-%m-%Y','%d/%m/%Y','%m/%d/%Y')
        for fmt in fmts:
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except Exception:
                pass
    return None

def detect_supplier(text: str, hints: Dict[str, List[str]]) -> Optional[str]:
    best = None; best_score = 0
    low = text.lower()
    for supplier, words in (hints or {}).items():
        score = 0
        for w in words or []:
            if w.lower() in low:
                score += 1
        if score > best_score:
            best_score = score; best = supplier
    return best

def _to_float(num_s: str) -> Optional[float]:
    if not num_s: return None
    s = num_s.strip().replace(' ', '')
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try: return float(s)
    except Exception: return None

def extract_amounts(text: str, pats: Dict):
    gross = net = tax = None; currency = None
    rxs = pats or {}
    def find_first(rx_list: List[str]) -> Optional[float]:
        for rx in rx_list or []:
            m = re.search(rx, text, re.IGNORECASE | re.MULTILINE)
            if m:
                return _to_float(m.group(1) if m.groups() else m.group(0))
        return None
    gross = find_first(rxs.get('total_gross_patterns', []))
    net   = find_first(rxs.get('total_net_patterns', []))
    tax   = find_first(rxs.get('tax_amount_patterns', []))
    if re.search(r'\bEUR\b|€', text, re.IGNORECASE): currency = 'EUR'
    elif re.search(r'\bUSD\b|\$', text, re.IGNORECASE): currency = 'USD'
    if gross is None and net is not None and tax is not None: gross = net + tax
    if net   is None and gross is not None and tax is not None: net = gross - tax
    if tax   is None and gross is not None and net  is not None: tax = max(0.0, gross - net)
    return gross, net, tax, currency

def extract_text_from_pdf(path: str, use_ocr: bool, poppler_path: Optional[str], tesseract_cmd: Optional[str], tesseract_lang: str = 'deu+eng'):
    text = None
    if fitz:
        try:
            doc = fitz.open(path)
            parts = [page.get_text('text') for page in doc]
            text = '\n'.join(parts).strip()
            if text and len(text) > 20:
                return text, 'text'
        except Exception:
            pass
    if not text and pdfminer_extract_text:
        try:
            text = pdfminer_extract_text(path) or ''
            text = text.strip()
            if text and len(text) > 20:
                return text, 'text'
        except Exception:
            pass
    if use_ocr and pytesseract and convert_from_path:
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        imgs = convert_from_path(path, dpi=300, poppler_path=poppler_path)
        ocr_texts = []
        for img in imgs:
            ocr_texts.append(pytesseract.image_to_string(img, lang=tesseract_lang or 'deu+eng'))
        return '\n'.join(ocr_texts), 'ocr'
    return (text or ''), 'text'

def _date_is_recent(iso_s: Optional[str], max_days: int = 370) -> bool:
    if not iso_s: return False
    try:
        d = datetime.fromisoformat(iso_s).date()
        return (date.today() - d).days <= max_days
    except Exception:
        return False

def compute_confidence(text: str, inv: Optional[str], dt_iso: Optional[str], sup: Optional[str], gross: Optional[float], validation_max_days: int = 370) -> float:
    score = 0.0
    if inv: score += 0.35
    if validation_max_days and validation_max_days > 0:
        if dt_iso and _date_is_recent(dt_iso, validation_max_days):
            score += 0.25
    else:
        if dt_iso: score += 0.2  # Archivmodus: Datum vorhanden zählt, Frische egal
    if sup: score += 0.2
    if len(text) > 200: score += 0.1
    if gross is not None: score += 0.1
    return max(0.0, min(1.0, score))

def validate_fields(inv: Optional[str], dt_iso: Optional[str], sup: Optional[str], patterns: Dict,
                    gross: Optional[float], net: Optional[float], tax: Optional[float], currency: Optional[str],
                    enable_amount_validation: bool = True, validation_max_days: int = 370):
    # Datum prüfen (abschaltbar über validation_max_days <= 0)
    if validation_max_days and validation_max_days > 0:
        if not _date_is_recent(dt_iso, validation_max_days):
            return 'fail', f'Datum nicht plausibel (älter als {validation_max_days} Tage).'
    # Whitelist pro Lieferant
    wl = (patterns or {}).get('whitelist', {}).get('invoice_numbers', {})
    if sup and wl.get(sup):
        ok = any(inv and re.search(rx, inv) for rx in wl[sup])
        if not ok:
            return 'fail', f'Whitelist-Regel verletzt (Lieferant={sup}).'
    # Betragskonsistenz
    if enable_amount_validation and (gross is not None and net is not None and tax is not None):
        if abs((net + tax) - gross) > 0.02:
            return 'fail', 'Betragssumme inkonsistent (Netto + Steuer != Brutto).'
        if net > 0:
            rate = (gross - net) / net
            if abs(rate - 0.19) > 0.03 and abs(rate - 0.07) > 0.03:
                return 'needs_review', f'Ungewöhnlicher Steuersatz (~{rate*100:.1f}%).'
    if not inv or not sup:
        return 'needs_review', 'Felder unvollständig.'
    return 'ok', None

CSV_COLS = ['source_file','target_file','invoice_no','supplier','date','method','hash_md5','confidence','validation_status','gross','net','tax','currency']

def append_csv(csv_path: str, row: Dict):
    ensure_dir(os.path.dirname(csv_path))
    file_exists = os.path.exists(csv_path)
    with open(csv_path, 'a', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        if not file_exists:
            w.writeheader()
        for k in CSV_COLS:
            if k not in row: row[k] = None
        w.writerow({k: row.get(k) for k in CSV_COLS})

def read_seen_hashes(csv_path: Optional[str]):
    seen = set()
    if not csv_path or not os.path.exists(csv_path):
        return seen
    try:
        with open(csv_path, 'r', encoding='utf-8', newline='') as f:
            r = csv.DictReader(f)
            for row in r:
                h = (row.get('hash_md5') or '').strip()
                if h:
                    seen.add(h)
    except Exception:
        pass
    return seen

def _ollama_available(host: str) -> bool:
    if not requests: return False
    try:
        r = requests.get(host.rstrip('/') + '/api/tags', timeout=2)
        return r.status_code == 200
    except Exception:
        return False

def build_prompt(body: str) -> str:
    parts = [
        "Du bist ein strenger Extraktor. Antworte NUR mit einem JSON-Objekt, ohne erklärenden Text.",
        "Extrahiere aus der folgenden Rechnung die Felder:",
        "invoice_no (string), supplier (string), date (YYYY-MM-DD), gross (number), net (number), tax (number), currency (string, e.g. EUR).",
        "Wenn ein Feld fehlt, gib null.",
        "Text:",
        '\"\"\"',
        body,
        '\"\"\"',
        "Gib ausschließlich JSON zurück."
    ]
    return "\\n".join(parts)

def ollama_extract(text: str, host: str, model: str, timeout: int = 30):
    if not requests: 
        return None
    try:
        url = host.rstrip('/') + '/api/generate'
        payload = {"model": model, "prompt": build_prompt(text[:20000]), "stream": False}
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json()
        out = data.get('response') or ''
        start = out.find('{'); end = out.rfind('}')
        if start == -1 or end == -1 or end <= start:
            return None
        js = out[start:end+1]
        return json.loads(js)
    except Exception:
        return None

def merge_llm(result: ExtractResult, js: dict):
    changed = False
    def get(key):
        v = js.get(key)
        return None if v in (None, '', 'null') else v
    inv = get('invoice_no') or result.invoice_no
    sup = get('supplier') or result.supplier
    dt = get('date') or result.invoice_date
    def _flt(x):
        try: 
            if isinstance(x, (int, float)): return float(x)
            if isinstance(x, str): return float(x.replace(',', '.'))
        except Exception: 
            return None
        return None
    gross = _flt(js.get('gross')) if js.get('gross') is not None else result.gross
    net   = _flt(js.get('net'))   if js.get('net')   is not None else result.net
    tax   = _flt(js.get('tax'))   if js.get('tax')   is not None else result.tax
    curr  = (js.get('currency') or '').strip() or result.currency
    if (inv, sup, dt, gross, net, tax, curr) != (result.invoice_no, result.supplier, result.invoice_date, result.gross, result.net, result.tax, result.currency):
        changed = True
    result.invoice_no, result.supplier, result.invoice_date = inv, sup, dt
    result.gross, result.net, result.tax, result.currency = gross, net, tax, curr or result.currency
    return result, changed

def _make_frontpage_pdf(tmp_path: str, meta: dict):
    if not rl_canvas:
        return False
    from reportlab.lib import colors
    c = rl_canvas.Canvas(tmp_path, pagesize=A4)
    w, h = A4
    c.setFillColor(colors.HexColor('#0f172a'))
    c.rect(0, h-80, w, 80, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont('Helvetica-Bold', 22)
    c.drawString(30, h-55, "Rechnungs-Deckblatt")
    c.setFillColor(colors.black); c.setFont('Helvetica', 12)
    y = h-120
    for label, key in [("Rechnungsnummer","invoice_no"),("Lieferant","supplier"),("Rechnungsdatum","date"),
                       ("Brutto","gross"),("Netto","net"),("Steuer","tax"),("Währung","currency")]:
        val = meta.get(key)
        c.drawString(30, y, f"{label}: {val if val is not None else '-'}"); y -= 20
    try:
        from reportlab.graphics.barcode import qr as rl_qr
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
        qr_payload = json.dumps(meta, ensure_ascii=False)
        qrobj = rl_qr.QrCodeWidget(qr_payload); b = 160
        d = Drawing(b, b); d.add(qrobj); renderPDF.draw(d, c, w-190, h-230)
    except Exception:
        pass
    c.setFont('Helvetica-Oblique', 9); c.setFillColor(colors.gray)
    c.drawString(30, 30, f"Erstellt: {datetime.now().isoformat(timespec='seconds')} • Invoice Sorter")
    c.showPage(); c.save(); return True

def stamp_pdf_with_front_page(original_pdf: str, out_pdf: str, meta: dict) -> bool:
    if not PdfReader or not rl_canvas:
        try: shutil.copy2(original_pdf, out_pdf); return True
        except Exception: return False
    try:
        tmp_cover = out_pdf + '.cover.tmp.pdf'; ok = _make_frontpage_pdf(tmp_cover, meta)
        if not ok: shutil.copy2(original_pdf, out_pdf); return True
        reader_cover = PdfReader(tmp_cover); reader_orig = PdfReader(original_pdf); writer = PdfWriter()
        for page in reader_cover.pages: writer.add_page(page)
        for page in reader_orig.pages: writer.add_page(page)
        with open(out_pdf, 'wb') as f: writer.write(f)
        try: os.remove(tmp_cover)
        except Exception: pass
        return True
    except Exception:
        return False

def _safe_name(s: str) -> str:
    s = s or 'unknown'
    s = re.sub(r'[^A-Za-z0-9_\-]+', '_', s)[:100]
    return s.strip('_') or 'unknown'

class _FormatDict(dict):
    """dict that returns empty string for missing keys (for str.format_map)."""

    def __missing__(self, key):  # pragma: no cover - trivial
        return ''


def _sanitize_filename(name: str) -> str:
    """Remove characters that are problematic for most filesystems."""

    name = name.replace('\x00', '')
    for sep in (os.sep, os.path.altsep):
        if sep:
            name = name.replace(sep, '_')
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    if not name:
        return 'output'
    # limit length but keep extension space for ".pdf"
    return name[:180]


def _format_output_filename(fmt: str, meta: Dict[str, str]) -> str:
    fmt = (fmt or DEFAULT_OUTPUT_FILENAME_FORMAT).strip()
    if not fmt:
        fmt = DEFAULT_OUTPUT_FILENAME_FORMAT

    meta_clean = _FormatDict()
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (int, float)):
            meta_clean[key] = value
        else:
            meta_clean[key] = str(value)

    try:
        rendered = fmt.format_map(meta_clean)
    except Exception:
        rendered = DEFAULT_OUTPUT_FILENAME_FORMAT.format_map(meta_clean)

    rendered = _sanitize_filename(rendered)
    if not rendered.lower().endswith('.pdf'):
        rendered += '.pdf'
    return rendered

def _year_from_iso(d: Optional[str]) -> str:
    try: return datetime.fromisoformat(d).strftime('%Y')
    except Exception: return datetime.now().strftime('%Y')

def _merge_supplier_overrides(pats: Dict, supplier: Optional[str]) -> Dict:
    if not supplier: return pats
    prof = (pats or {}).get('supplier_profiles', {}).get(supplier)
    if not prof: return pats
    merged = dict(pats)
    for key in ('invoice_number_patterns','date_patterns','total_gross_patterns','total_net_patterns','tax_amount_patterns','whitelist'):
        if key in prof:
            if isinstance(prof[key], list):
                merged[key] = prof[key] + list(pats.get(key, []) or [])
            elif isinstance(prof[key], dict):
                base = dict(pats.get(key, {}) or {}); base.update(prof[key]); merged[key] = base
    return merged

def _should_call_ollama(conf: float, status: str, trigger: str, threshold: float) -> bool:
    trigger = (trigger or 'on_low_conf').lower()
    if trigger == 'always': return True
    if trigger == 'on_fail': return status == 'fail'
    if trigger == 'on_low_conf': return (status != 'ok') or (conf < threshold)
    return False

def process_file(pdf_path: str, cfg: Dict, patterns: Dict, seen_hashes: Optional[Set[str]] = None, write_side_effects: bool = True) -> ExtractResult:
    input_dir = cfg.get('input_dir'); output_dir = cfg.get('output_dir')
    unknown_dir_name = cfg.get('unknown_dir_name', 'unbekannt')
    dry_run = bool(cfg.get('dry_run', False))
    csv_log_path = cfg.get('csv_log_path')
    use_ocr = bool(cfg.get('use_ocr', True))
    poppler_path = cfg.get('poppler_path'); tesseract_cmd = cfg.get('tesseract_cmd')
    tesseract_lang = cfg.get('tesseract_lang', 'deu+eng')
    stamp_pdf = bool(cfg.get('stamp_pdf', True))
    validation_max_days = int(cfg.get('validation_max_days', 370) or 0)

    use_ollama = bool(cfg.get('use_ollama', False))
    oll = cfg.get('ollama', {}) or {}
    oll_host = oll.get('host', 'http://localhost:11434')
    oll_model = oll.get('model', 'llama3')
    oll_timeout = int(oll.get('timeout', 30))
    oll_trigger = (oll.get('trigger') or 'on_low_conf').lower()
    oll_threshold = float(oll.get('conf_threshold', 0.65))

    md5 = md5_of_file(pdf_path)

    # Duplicate detection
    if seen_hashes is not None and md5 in seen_hashes:
        res = ExtractResult(
            source_file=pdf_path, target_file=None, invoice_no=None, supplier=None, invoice_date=None,
            method='duplicate', hash_md5=md5, confidence=0.0, validation_status='duplicate',
            message='Duplikat erkannt – kein erneutes Verschieben.'
        )
        if csv_log_path:
            append_csv(csv_log_path, {
                'source_file': pdf_path, 'target_file': None,
                'invoice_no': None, 'supplier': None, 'date': None, 'method': 'duplicate',
                'hash_md5': md5, 'confidence': 0.0, 'validation_status': 'duplicate',
                'gross': None, 'net': None, 'tax': None, 'currency': None
            })
        return res

    text, method = extract_text_from_pdf(pdf_path, use_ocr, poppler_path, tesseract_cmd, tesseract_lang)

    inv = extract_invoice_no(text, patterns.get('invoice_number_patterns', []))
    dt_iso = extract_date(text, patterns.get('date_patterns', []))
    sup = detect_supplier(text, patterns.get('supplier_hints', {}))

    eff_pats = _merge_supplier_overrides(patterns, sup)
    if not inv:    inv    = extract_invoice_no(text, eff_pats.get('invoice_number_patterns', []))
    if not dt_iso: dt_iso = extract_date(text, eff_pats.get('date_patterns', []))

    gross, net, tax, currency = extract_amounts(text, eff_pats)

    conf = compute_confidence(text, inv, dt_iso, sup, gross, validation_max_days)
    status, reason = validate_fields(inv, dt_iso, sup, eff_pats, gross, net, tax, currency,
                                     enable_amount_validation=True, validation_max_days=validation_max_days)

    used_ollama = False
    if use_ollama and _should_call_ollama(conf, status, oll_trigger, oll_threshold) and _ollama_available(oll_host):
        js = ollama_extract(text, oll_host, oll_model, timeout=oll_timeout)
        if js:
            tmp = ExtractResult(pdf_path, None, inv, sup, dt_iso, method, md5, conf, status, gross, net, tax, currency, reason)
            tmp, changed = merge_llm(tmp, js)
            inv, sup, dt_iso, gross, net, tax, currency = tmp.invoice_no, tmp.supplier, tmp.invoice_date, tmp.gross, tmp.net, tmp.tax, tmp.currency
            conf = compute_confidence(text, inv, dt_iso, sup, gross, validation_max_days)
            status, reason = validate_fields(inv, dt_iso, sup, eff_pats, gross, net, tax, currency,
                                             enable_amount_validation=True, validation_max_days=validation_max_days)
            if changed: used_ollama = True

    # Target dir
    if status == 'ok':
        y = _year_from_iso(dt_iso); target_dir = os.path.join(output_dir, y, _safe_name(sup))
    elif status == 'needs_review':
        target_dir = os.path.join(output_dir, 'review')
    else:
        target_dir = os.path.join(output_dir, unknown_dir_name)
    ensure_dir(target_dir)

    final_method = 'ollama' if used_ollama else method
    base_name = os.path.basename(pdf_path)
    base_stem, _ = os.path.splitext(base_name)
    target_subdir = os.path.basename(target_dir.rstrip(os.sep)) if target_dir else ''
    filename_meta = {
        'date': dt_iso or '0000-00-00',
        'year': _year_from_iso(dt_iso),
        'date_year': _year_from_iso(dt_iso),
        'supplier': sup or 'unknown',
        'supplier_safe': _safe_name(sup),
        'invoice_no': inv or '',
        'invoice_no_safe': _safe_name(inv),
        'status': status or '',
        'validation_status': status or '',
        'method': final_method or '',
        'confidence': f"{conf:.2f}",
        'gross': f"{gross:.2f}" if gross is not None else '',
        'gross_value': gross if gross is not None else '',
        'net': f"{net:.2f}" if net is not None else '',
        'net_value': net if net is not None else '',
        'tax': f"{tax:.2f}" if tax is not None else '',
        'tax_value': tax if tax is not None else '',
        'currency': currency or '',
        'hash_md5': md5,
        'hash_short': md5[:8],
        'original_name': base_stem,
        'original_name_safe': _safe_name(base_stem),
        'target_dir': target_dir,
        'target_subdir': target_subdir,
        'target_subdir_safe': _safe_name(target_subdir),
    }
    fmt = cfg.get('output_filename_format')
    new_name = _format_output_filename(fmt, filename_meta)
    target_file = os.path.join(target_dir, new_name)

    if write_side_effects and not dry_run:
        try:
            if stamp_pdf:
                meta = {
                    "invoice_no": inv, "supplier": sup, "date": dt_iso,
                    "gross": gross, "net": net, "tax": tax, "currency": currency,
                }
                stamp_pdf_with_front_page(pdf_path, target_file, meta)
            else:
                shutil.copy2(pdf_path, target_file)
        except Exception:
            target_file = os.path.join(target_dir, base_name)
            shutil.copy2(pdf_path, target_file)

    res = ExtractResult(
        source_file=pdf_path, target_file=target_file if not dry_run else None,
        invoice_no=inv, supplier=sup, invoice_date=dt_iso, method=final_method,
        hash_md5=md5, confidence=conf, validation_status=status,
        gross=gross, net=net, tax=tax, currency=currency, message=reason
    )

    if csv_log_path:
        append_csv(csv_log_path, {
            'source_file': pdf_path, 'target_file': res.target_file,
            'invoice_no': inv, 'supplier': sup, 'date': dt_iso, 'method': res.method,
            'hash_md5': md5, 'confidence': conf, 'validation_status': status,
            'gross': gross, 'net': net, 'tax': tax, 'currency': currency
        })

    return res

def iter_pdfs(input_dir: str):
    for root, _, files in os.walk(input_dir):
        for fn in files:
            if fn.lower().endswith('.pdf'):
                yield os.path.join(root, fn)

def process_all(config_path: str, patterns_path: str,
                stop_fn: Optional[Callable[[], bool]] = None,
                progress_fn: Optional[Callable[[int,int,str,Optional[ExtractResult]], None]] = None):
    import yaml
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}
    pats = load_patterns(patterns_path)

    seen = read_seen_hashes(cfg.get('csv_log_path'))

    files = list(iter_pdfs(cfg.get('input_dir','')))
    n = len(files)
    for i, pdf in enumerate(files, 1):
        if stop_fn and stop_fn(): break
        res = process_file(pdf, cfg, pats, seen_hashes=seen, write_side_effects=True)
        if progress_fn: progress_fn(i, n, os.path.basename(pdf), res)
        if res and res.hash_md5:
            seen.add(res.hash_md5)
