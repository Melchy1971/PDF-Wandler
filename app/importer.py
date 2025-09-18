from pathlib import Path
from typing import List
from PIL import Image
import fitz  # PyMuPDF

def pdf_to_images(pdf_path: Path, dpi: int = 300) -> List[Image.Image]:
    doc = fitz.open(pdf_path)
    images = []
    for page in doc:
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    return images
