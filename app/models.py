from pydantic import BaseModel, Field
from datetime import date
from typing import Optional

class ExtractedInvoice(BaseModel):
    supplier: Optional[str] = Field(None, description="Lieferant/Absender")
    invoice_no: Optional[str]
    invoice_date: Optional[date]
    confidence: float = 0.0
    source_file: str = ""
    page: int = 1
    raw_text: str = ""
