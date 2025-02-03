import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import logging
import os

def extract_text_from_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        logging.error(f"Datei {pdf_path} existiert nicht.")
        return ""
    try:
        text = ""
        with fitz.open(pdf_path) as document:
            for page_num in range(document.page_count):
                page = document.load_page(page_num)
                text += page.get_text()
        logging.info(f"Text aus PDF {pdf_path} extrahiert.")
        return text
    except fitz.FileDataError as e:
        logging.error(f"Dateifehler beim Extrahieren des Texts aus PDF {pdf_path}: {str(e)}")
    except Exception as e:
        logging.error(f"Unbekannter Fehler beim Extrahieren des Texts aus PDF {pdf_path}: {str(e)}")
    return ""

def extract_text_from_image(image_path):
    if not os.path.exists(image_path):
        logging.error(f"Datei {image_path} existiert nicht.")
        return ""
    try:
        allowed_extensions = ['.png', '.jpg', '.jpeg']
        if not any(image_path.lower().endswith(ext) for ext in allowed_extensions):
            logging.error(f"Ungültiges Dateiformat für Bild {image_path}")
            return ""
        
        with Image.open(image_path) as image:
            text = pytesseract.image_to_string(image)
        logging.info(f"Text aus Bild {image_path} extrahiert.")
        return text
    except pytesseract.TesseractError as e:
        logging.error(f"Tesseract-Fehler beim Extrahieren des Texts aus Bild {image_path}: {str(e)}")
    except Exception as e:
        logging.error(f"Unbekannter Fehler beim Extrahieren des Texts aus Bild {image_path}: {str(e)}")
    return ""