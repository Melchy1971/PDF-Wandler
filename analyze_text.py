import re
import logging
from typing import Dict
from fuzzywuzzy import fuzz, process

def analyze_text(text: str) -> Dict[str, str]:
    # Erweiterte Muster für Firmennamen, die auch Abkürzungen und Sonderzeichen berücksichtigen
    company_name_patterns = [
        r"\b[A-Z][a-z]+\s[A-Z][a-z]+\s(GmbH|AG|KG)\b",  # Beispiel: Müller Meier GmbH, Müller Meier AG, Müller Meier KG
        r"\b[A-Z][a-z]+[-\s][A-Z][a-z]+\s(GmbH|AG|KG)\b",  # Beispiel: Müller-Meier GmbH, Müller-Meier AG, Müller-Meier KG
        r"\b[A-Z][a-z]+\sund\s[A-Z][a-z]+\s(GmbH|AG|KG)\b",  # Beispiel: Müller und Meier GmbH, Müller und Meier AG, Müller und Meier KG
        r"\b[A-Z]+\s[A-Z]+\s(GmbH|AG|KG)\b",  # Beispiel: MM GmbH, MM AG, MM KG
        r"\b[A-Z]+\s&\s[A-Z]+\s(GmbH|AG|KG)\b",  # Beispiel: M & M GmbH, M & M AG, M & M KG
        r"\b(Amazo|EnBW|Zaberfeld|Microsoft)\b"  # Spezielle Firmennamen
    ]

    # Muster für Datum, Rechnungsnummer, Bestellnummer, Angebotsnummer und Kundennummer
    date_pattern = r"\b\d{2}\.\d{2}\.\d{4}\b"
    invoice_number_pattern = r"Rechnungsnummer:\s*\d+"
    order_number_pattern = r"Bestellnummer:\s*\d+"
    offer_number_pattern = r"Angebotsnummer:\s*\d+"
    customer_number_pattern = r"Kundennummer:\s*\d+"

    company_names = []
    for pattern in company_name_patterns:
        company_names.extend(re.findall(pattern, text))

    dates = re.findall(date_pattern, text)
    invoice_numbers = re.findall(invoice_number_pattern, text)
    order_numbers = re.findall(order_number_pattern, text)
    offer_numbers = re.findall(offer_number_pattern, text)
    customer_numbers = re.findall(customer_number_pattern, text)

    # Fehlertolerante Verarbeitung (Fuzzy Matching)
    unique_company_names = list(set(company_names))
    if not unique_company_names:
        company_name = "Unbekannt"
    else:
        best_match = process.extractOne("GmbH", unique_company_names, scorer=fuzz.ratio)
        company_name = best_match[0] if best_match and best_match[1] > 80 else unique_company_names[0]

    # Bestimmen der Nummer, die verwendet werden soll
    number = "000000"
    if invoice_numbers:
        number = invoice_numbers[0].split(":")[1].strip()
    elif order_numbers:
        number = order_numbers[0].split(":")[1].strip()
    elif offer_numbers:
        number = offer_numbers[0].split(":")[1].strip()
    elif customer_numbers:
        number = customer_numbers[0].split(":")[1].strip()

    logging.info("Text analysiert und Informationen extrahiert.")
    return {
        "company_name": company_name,
        "date": dates[0] if dates else "0000.00.00",
        "number": number
    }