"""
Minimaler Extraktions-Layer für dein Tool.
- Nutzt pdfminer.six für PDFs, falls installiert.
- Nutzt Pillow + pytesseract für Bilder, falls installiert.
- Fällt sonst still auf leeren Text zurück (das Hauptprogramm läuft trotzdem weiter).
"""

from typing import Optional

# --- PDF ---
try:
    from pdfminer.high_level import extract_text as _pdf_extract_text  # type: ignore
except Exception:  # ImportError oder andere Fehler
    _pdf_extract_text = None  # type: ignore

# --- OCR (Bilder) ---
try:
    from PIL import Image, ImageOps, ImageFilter  # type: ignore
except Exception:
    Image = None  # type: ignore
    ImageOps = None  # type: ignore
    ImageFilter = None  # type: ignore

try:
    import pytesseract  # type: ignore
except Exception:
    pytesseract = None  # type: ignore


def extract_text_from_pdf(path: str) -> str:
    """Extrahiert Text aus einem PDF. Gibt "" zurück, wenn pdfminer.six fehlt."""
    if _pdf_extract_text is None:
        return ""
    try:
        return _pdf_extract_text(path) or ""
    except Exception:
        # Fehler werden im Hauptprogramm geloggt; hier stiller Fallback.
        return ""


def _preprocess(img):
    """Einfache Vorverarbeitung für bessere OCR."""
    if ImageOps is None or ImageFilter is None:
        return img
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g)
    g = g.filter(ImageFilter.SHARPEN)
    return g


def extract_text_from_image(path: str) -> str:
    """Extrahiert Text aus einem Bild. Gibt "" zurück, wenn Pillow/pytesseract fehlt."""
    if Image is None or pytesseract is None:
        return ""
    try:
        with Image.open(path) as im:
            im = _preprocess(im)
            # DE/EN parallel – passe nach Bedarf an (z.B. nur "deu")
            txt = pytesseract.image_to_string(im, lang="deu+eng")
            return txt or ""
    except Exception:
        return ""
