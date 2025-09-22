 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/sorter.py b/sorter.py
index e1b5e25e52bce7100b046f7abfaac2643bce01bb..924984b72730264fd9632291257978dc400665dd 100644
--- a/sorter.py
+++ b/sorter.py
@@ -1,32 +1,32 @@
 
 from __future__ import annotations
 
 import os, re, csv, json, hashlib, shutil
 from dataclasses import dataclass
 from datetime import datetime, date
-from typing import Optional, Dict, List, Callable, Set
+from typing import Optional, Dict, List, Callable, Set, Any
 
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
diff --git a/sorter.py b/sorter.py
index e1b5e25e52bce7100b046f7abfaac2643bce01bb..924984b72730264fd9632291257978dc400665dd 100644
--- a/sorter.py
+++ b/sorter.py
@@ -376,50 +376,95 @@ def _safe_name(s: str) -> str:
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
 
 
+def _iter_output_filename_presets(presets: Any):
+    if isinstance(presets, dict):
+        for value in presets.values():
+            if isinstance(value, str):
+                cand = value.strip()
+                if cand:
+                    yield cand
+    elif isinstance(presets, list):
+        for item in presets:
+            if isinstance(item, str):
+                cand = item.strip()
+                if cand:
+                    yield cand
+            elif isinstance(item, dict):
+                candidate = (
+                    item.get('pattern')
+                    or item.get('format')
+                    or item.get('template')
+                    or item.get('value')
+                )
+                if isinstance(candidate, str):
+                    cand = candidate.strip()
+                    if cand:
+                        yield cand
+            elif isinstance(item, (list, tuple)) and len(item) >= 2:
+                candidate = item[1]
+                if isinstance(candidate, str):
+                    cand = candidate.strip()
+                    if cand:
+                        yield cand
+
+
+def _resolve_output_filename_format(cfg: Dict[str, Any]) -> str:
+    if isinstance(cfg, dict):
+        fmt = cfg.get('output_filename_format')
+        if isinstance(fmt, str):
+            fmt_str = fmt.strip()
+            if fmt_str:
+                return fmt_str
+        presets = cfg.get('output_filename_formats')
+        for candidate in _iter_output_filename_presets(presets):
+            return candidate
+    return DEFAULT_OUTPUT_FILENAME_FORMAT
+
+
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
diff --git a/sorter.py b/sorter.py
index e1b5e25e52bce7100b046f7abfaac2643bce01bb..924984b72730264fd9632291257978dc400665dd 100644
--- a/sorter.py
+++ b/sorter.py
@@ -529,51 +574,51 @@ def process_file(pdf_path: str, cfg: Dict, patterns: Dict, seen_hashes: Optional
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
-    fmt = cfg.get('output_filename_format')
+    fmt = _resolve_output_filename_format(cfg)
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
 
EOF
)