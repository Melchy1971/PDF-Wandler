import re
import logging
from datetime import datetime
from typing import Dict
from fuzzywuzzy import fuzz, process

# Definierte Regex-Muster für die Erkennung
COMPANY_KEYWORDS = ["GmbH", "GBr", "OHG", "AG", "KG", "UG", "e.K.", "e.V."]
DATE_PATTERN = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
NUMBER_PATTERNS = [
    re.compile(r"Rechnung\s*Nr\.?:?\s*(\w+-\w+-\w+-\w+-\w+)", re.IGNORECASE),
    re.compile(r"Rechnungsnummer[:\s]*(\w+-\w+-\w+-\w+-\w+)", re.IGNORECASE),
    re.compile(r"Rechnung\s*Nr\.?:?\s*(\d+)", re.IGNORECASE),
    re.compile(r"Rechnungsnummer[:\s]*(\d+)", re.IGNORECASE),
]

def extract_company_name(text):
    """Extrahiert Firmennamen basierend auf bekannten Endungen (z. B. GmbH, AG, KG)."""
    try:
        pattern = re.compile(rf"(.*?)\s+(?:{'|'.join(map(re.escape, COMPANY_KEYWORDS))})", re.IGNORECASE)
        match = pattern.search(text)
        return match.group(1).strip() if match else "Unbekannt"
    except Exception as e:
        logging.error(f"Fehler bei der Firmennamensuche: {e}")
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
    """Findet das erste gültige Datum im Text."""
    try:
        matches = DATE_PATTERN.findall(text)
        for match in matches:
            parsed_date = detect_date(match)
            if parsed_date:
                return parsed_date
        return ""
    except Exception as e:
        logging.error(f"Fehler bei der Datumsextraktion: {e}")
        return ""

def extract_invoice_number(text):
    """Sucht nach der ersten passenden Rechnungsnummer."""
    try:
        for pattern in NUMBER_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return ""
    except Exception as e:
        logging.error(f"Fehler bei der Rechnungsnummer-Extraktion: {e}")
        return ""

def analyze_text(text: str) -> Dict[str, str]:
    """
    Analysiert den Text und extrahiert relevante Informationen (Firma, Datum, Rechnungsnummer).
    """
    if not text or len(text) < 10:  # Falls der Text leer oder zu kurz ist
        logging.warning("Leerer oder ungültiger Text zur Analyse erhalten.")
        return {"company_name": "Unbekannt", "date": "", "number": ""}

    try:
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