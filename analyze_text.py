import re
import logging
from typing import Dict, Optional
from fuzzywuzzy import fuzz, process

def analyze_text(text: str) -> Dict[str, str]:
    try:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Input text must be a non-empty string")
        
        company_name_patterns = [
            r"\b[A-Z][a-z]+\s[A-Z][a-z]+\s(GmbH|AG|KG)\b",
            r"\b[A-Z][a-z]+[-\s][A-Z][a-z]+\s(GmbH|AG|KG)\b",
            r"\b[A-Z][a-z]+\sund\s[A-Z][a-z]+\s(GmbH|AG|KG)\b",
            r"\b[A-Z]+\s[A-Z]+\s(GmbH|AG|KG)\b",
            r"\b[A-Z]+\s&\s[A-Z]+\s(GmbH|AG|KG)\b",
            r"\b(Amazo|EnBW|Zaberfeld|Microsoft)\b"
        ]

        date_pattern = r"\b\d{2}\.\d{2}\.\d{4}\b"
        number_patterns = {
            "invoice": r"Rechnungsnummer:\s*(\d+)",
            "order": r"Bestellnummer:\s*(\d+)",
            "offer": r"Angebotsnummer:\s*(\d+)",
            "customer": r"Kundennummer:\s*(\d+)"
        }

        company_names = []
        for pattern in company_name_patterns:
            company_names.extend(re.findall(pattern, text))
        
        dates = re.findall(date_pattern, text)
        numbers = {key: re.findall(pattern, text) for key, pattern in number_patterns.items()}

        unique_company_names = list(set(company_names))
        company_name = "Unbekannt"
        if unique_company_names:
            try:
                best_match = process.extractOne("GmbH", unique_company_names, scorer=fuzz.ratio)
                if best_match and best_match[1] > 80:
                    company_name = best_match[0]
                else:
                    company_name = unique_company_names[0]
            except Exception as e:
                logging.error(f"Error during fuzzy matching: {e}")
                company_name = unique_company_names[0]
        
        number: Optional[str] = None
        for key in ["invoice", "order", "offer", "customer"]:
            if numbers[key]:
                number = numbers[key][0]
                break
        number = number or "000000"
        
        logging.info("Text successfully analyzed.")
        return {
            "company_name": company_name,
            "date": dates[0] if dates else "0000.00.00",
            "number": number
        }
    except Exception as e:
        logging.error(f"Error analyzing text: {e}")
        return {"company_name": "Unbekannt", "date": "0000.00.00", "number": "000000"}
