import re
import logging
from datetime import datetime
from typing import Dict
from fuzzywuzzy import fuzz, process
import dateutil.parser

# Definierte Regex-Muster für die Erkennung
COMPANY_KEYWORDS = ["GmbH", "GBr", "OHG", "AG", "KG", "UG", "e.K.", "e.V."]
DATE_PATTERN = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")

def extract_company_name(text):
    """
    Extrahiert Firmennamen basierend auf Keywords oder heuristischen Methoden.
    """
    try:
        company_keywords = ["GmbH", "GBr", "OHG", "AG", "KG", "UG", "e.K.", "e.V."]
        pattern = re.compile(rf"(.*?)\s+(?:{'|'.join(map(re.escape, company_keywords))})", re.IGNORECASE)

        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        
        # Alternativ: Suche nach typischen Firmenschlagwörtern
        alternative_patterns = [
            r"Firma\s*[:\-]?\s*(\w[\w\s&,-]+)",  # Firma: XYZ GmbH
            r"Company\s*[:\-]?\s*(\w[\w\s&,-]+)", # Company: XYZ Ltd.
        ]
        
        for pattern in alternative_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return "Unbekannt"
    
    except Exception as e:
        logging.error(f"Fehler bei der Firmennamen-Extraktion: {e}")
        return "Unbekannt"

def detect_date(date_str):
    """Versucht, ein Datum aus einem gegebenen String zu erkennen."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None

def extract_date(text):
    """
    Erkennt das erste passende Datum in einem Text mit einem KI-Fallback.
    """
    try:
        date_patterns = [
            r"\b\d{2}\.\d{2}\.\d{4}\b",  # 01.02.2024
            r"\b\d{4}-\d{2}-\d{2}\b",    # 2024-02-01
            r"\b\d{2}/\d{2}/\d{4}\b",    # 02/01/2024
            r"\b\d{1,2}\s+(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4}\b",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                parsed_date = detect_date(match.group())
                if parsed_date:
                    return parsed_date
        
        # KI-Fallback mit `dateutil.parser`
        return dateutil.parser.parse(text, fuzzy=True, dayfirst=True).strftime("%Y-%m-%d")

    except (ValueError, TypeError, Exception) as e:
        logging.error(f"Fehler bei der Datumsanalyse: {e}")
        return ""

def extract_invoice_number(text):
    """
    Sucht nach einer Rechnungsnummer mit flexibleren Mustern.
    """
    try:
        number_patterns = [
            r"Rechnung\s*Nr\.?:?\s*([\w-]+)",  # Standard: Rechnung Nr. 1234-5678
            r"Rechnungsnummer[:\s]*(\w+)",     # Alternativ: Rechnungsnummer: 123456
            r"Invoice\s*No\.?:?\s*([\w-]+)",   # Englisch: Invoice No. 1234-5678
        ]
        
        for pattern in number_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return ""  # Falls keine Rechnungsnummer gefunden wurde
    except Exception as e:
        logging.error(f"Fehler bei der Rechnungsnummer-Extraktion: {e}")
        return ""

def preprocess_text(text):
    """
    Bereinigt den Text für stabilere Analysen (z. B. OCR-Fehlerkorrektur).
    """
    try:
        # Ersetze verdächtige Zeichenkombinationen
        replacements = {
            r"\s+": " ",  # Mehrfache Leerzeichen entfernen
            r"\n+": " ",  # Mehrere Zeilenumbrüche in Leerzeichen umwandeln
            r"[^a-zA-Z0-9\s\.,:/\-]": "",  # Entferne Sonderzeichen, die nicht gebraucht werden
        }
        
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text)

        return text.strip()
    
    except Exception as e:
        logging.error(f"Fehler bei der Textvorbereitung: {e}")
        return text  # Falls Fehler, gib Originaltext zurück

def analyze_text(text: str) -> Dict[str, str]:
    """
    Hauptanalysefunktion zur Extraktion von Firmenname, Rechnungsnummer und Datum.
    """
    if not text or len(text) < 10:  # Falls der Text leer oder zu kurz ist
        logging.warning("Leerer oder ungültiger Text zur Analyse erhalten.")
        return {"company_name": "Unbekannt", "date": "", "number": ""}

    try:
        text = preprocess_text(text)  # Text vorher bereinigen
        company_name = extract_company_name(text)
        date = extract_date(text)
        invoice_number = extract_invoice_number(text)

        # Falls die Rechnungsnummer mit "AEU" beginnt, wird der Firmenname überschrieben (Amazon)
        if invoice_number.startswith("AEU"):
            company_name = "Amazon"

        return {
            "company_name": company_name,
            "date": date,
            "number": invoice_number
        }
    
    except Exception as e:
        logging.error(f"Fehler bei der Textanalyse: {e}")
        return {"company_name": "Unbekannt", "date": "", "number": ""}