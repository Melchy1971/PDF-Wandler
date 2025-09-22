from typing import Optional, Tuple
from pathlib import Path
import re

import pikepdf


XML_HINTS = (
    "zugferd",
    "factur-x",
    "facturx",
    "xrechnung",
)


def extract_embedded_xml(pdf_path: Path) -> Optional[Tuple[str, bytes]]:
    """Gibt (name, xml_bytes) zurück, wenn eingebettete Rechnungs-XML gefunden wurde, sonst None."""
    with pikepdf.open(str(pdf_path)) as pdf:
        attachments = pdf.attachments
        for name, spec in attachments.items():
            lname = name.lower()
            if lname.endswith(".xml") or any(h in lname for h in XML_HINTS):
                data = spec.read_bytes()
                # Minimal-Heuristik: enthält ein übliches Rechnungs-Root-Element
                if b"CrossIndustryInvoice" in data or b"Invoice" in data or b"rsm:CrossIndustryInvoice" in data:
                    return name, data
    return None


def quick_invoice_fields(xml_bytes: bytes) -> dict:
    """Leichte Extraktion zentraler Felder. Für robuste Nutzung später Schema/XPath einsetzen."""
    txt = xml_bytes.decode("utf-8", errors="ignore")

    def grab(pattern, flags=re.I):
        m = re.search(pattern, txt, flags)
        return m.group(1).strip() if m else None

    return {
        "invoice_no": grab(r"<(?:\w+:)?DocumentReference[^>]*>.*?<(?:\w+:)?ID>(.*?)</(?:\w+:)?ID>", re.S | re.I)
        or grab(r"<(?:\w+:)?InvoiceNumber>(.*?)<", re.I),
        "date": grab(
            r"<(?:\w+:)?IssueDateTime[^>]*>.*?<(?:\w+:)?DateTimeString[^>]*>(.*?)<",
            re.S | re.I,
        )
        or grab(r"<(?:\w+:)?InvoiceDate>(.*?)<", re.I),
        "supplier": grab(
            r"<(?:\w+:)?SellerTradeParty[^>]*>.*?<(?:\w+:)?Name>(.*?)<",
            re.S | re.I,
        )
        or grab(r"<(?:\w+:)?AccountingSupplierParty[^>]*>.*?<(?:\w+:)?Name>(.*?)<", re.S | re.I),
        "total": grab(r"<(?:\w+:)?GrandTotalAmount[^>]*>([\d.,]+)<", re.I)
        or grab(r"<(?:\w+:)?PayableAmount[^>]*>([\d.,]+)<", re.I),
        "iban": grab(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7,}\b"),
    }
