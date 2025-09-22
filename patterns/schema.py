from pydantic import BaseModel, Field, validator
from typing import List, Optional
import re


class SupplierPattern(BaseModel):
    name: str
    hints: List[str] = Field(default_factory=list)
    invoice_no: str
    date: str
    total: Optional[str] = None
    iban: Optional[str] = None
    whitelist: List[str] = Field(default_factory=list)

    @validator("invoice_no", "date", "total", "iban", pre=True, always=True)
    def _compile_regex(cls, v):
        if v is None:
            return v
        re.compile(v)
        return v
