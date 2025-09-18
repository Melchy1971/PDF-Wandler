from pathlib import Path
from datetime import date
from slugify import slugify

SAFE = lambda s: slugify(s or "unbekannt", lowercase=False)

def build_filename(today: date, supplier, invoice_date, ext: str) -> str:
    today_s = today.strftime("%Y-%m-%d")
    inv_s = invoice_date.strftime("%Y-%m-%d") if invoice_date else "0000-00-00"
    sup_s = SAFE(supplier)
    return f"{today_s}_{sup_s}_Re-{inv_s}{ext}"

def target_folder(root: Path, supplier, invoice_date) -> Path:
    year = (invoice_date.year if invoice_date else None)
    if not year:
        return root / "unbekannt"
    return root / str(year) / SAFE(supplier)

def move_with_collision_avoid(src: Path, dst_dir: Path, name: str) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    base, ext = Path(name).stem, Path(name).suffix
    candidate = dst_dir / name
    i = 1
    while candidate.exists():
        candidate = dst_dir / f"{base}_{i}{ext}"
        i += 1
    src.replace(candidate)
    return candidate
