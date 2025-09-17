import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import os
import logging
import shutil
import threading
import queue
import json
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from hashlib import sha256

# 3rd‑party deps
import dateutil.parser  # pip install python-dateutil
from docx import Document  # pip install python-docx
from openpyxl import load_workbook  # pip install openpyxl

# local deps
from text_extraction import extract_text_from_pdf, extract_text_from_image

# -----------------------------
# Configuration & Logging
# -----------------------------
CONFIG_FILE = "config.json"
COMPANIES_FILE = "firmen.txt"
LOG_FILE = "app.log"

DEFAULT_CONFIG = {
    "DEFAULT_SOURCE_DIR": "",
    "BACKUP_DIR": "backup",
    "ALLOWED_EXTENSIONS": ["pdf", "png", "jpg", "jpeg", "docx", "xlsx", "eml"],
    "BATCH_SIZE": 10,
    "DATE_FORMATS": ["%Y.%m.%d", "%Y-%m-%d", "%d.%m.%Y"],
    "MAIN_TARGET_DIR": "",
    "LOG_LEVEL": "INFO",
    "FILENAME_PATTERN": "{date}_{company}_RE-{number}.{ext}",
    "DARK_MODE": False,
    "STRIP_LEGAL_SUFFIXES": True,
    "LEGAL_SUFFIXES": [
        "GmbH & Co. KG", "GmbH & Co KG", "GmbH & Co.KG",
        "UG (haftungsbeschränkt)", "UG", "GmbH", "AG", "KG", "OHG", "GbR", "e.K.", "e.V."
    ],
    "SUPPLIER_RULES": {
        "amazon": {
            "name": "Amazon",
            "match": r"\b(Amazon|AEU)\b",
            "invoice_pattern": r"AEU[\w-]+|\b\d{3}-\d{7}-\d{7}\b"
        },
        "telekom": {
            "name": "Telekom",
            "match": r"\b(Deutsche\s+Telekom|Telekom Deutschland|T-Mobile)\b",
            "invoice_pattern": r"\b[0-9]{12}\b"
        },
        "ikea": {
            "name": "IKEA",
            "match": r"\bIKEA\b",
            "invoice_pattern": r"\b\d{9}\b"
        }
    }
}
