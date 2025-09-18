from pathlib import Path
from datetime import date as date_cls
from .models import ExtractedInvoice
from .parsing import find_invoice_date, find_invoice_no, guess_supplier, load_vendor_db
from .importer import pdf_to_images
from .ocr import preprocess, ocr_with_boxes
from .routing import build_filename, target_folder, move_with_collision_avoid

def extract_fields(ocr_text: str, ocr_df, vendor_db_path: Path) -> ExtractedInvoice:
    inv_date, c_date = find_invoice_date(ocr_text)
    inv_no, c_no = find_invoice_no(ocr_text)
    vendor_list = load_vendor_db(vendor_db_path)
    supplier, c_sup = guess_supplier(ocr_df, ocr_text, vendor_list)
    conf = (c_date + c_no + c_sup) / 3
    return ExtractedInvoice(
        supplier=supplier,
        invoice_no=inv_no,
        invoice_date=inv_date,
        confidence=conf,
        raw_text=ocr_text,
    )

def process_file(src: Path, root: Path, vendor_db: Path) -> dict:
    from PIL import Image
    if src.suffix.lower() == ".pdf":
        pages = pdf_to_images(src)
    else:
        pages = [Image.open(src)]
    best = None
    for p in pages:
        img = preprocess(p)
        o = ocr_with_boxes(img)
        rec = extract_fields(o["text"], o["df"], vendor_db)
        if (best is None) or (rec.confidence > best.confidence):
            best = rec
    new_name = build_filename(date_cls.today(), best.supplier, best.invoice_date, src.suffix)
    dst_dir = target_folder(root, best.supplier, best.invoice_date)
    final_path = move_with_collision_avoid(src, dst_dir, new_name)
    return {
        "final_path": str(final_path),
        "supplier": best.supplier,
        "invoice_no": best.invoice_no,
        "invoice_date": str(best.invoice_date) if best.invoice_date else None,
        "confidence": round(best.confidence, 3)
    }
