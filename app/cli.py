import typer
from pathlib import Path
import pandas as pd
from .postprocess import process_file

app = typer.Typer(help="KI‑gestützte Rechnungsablage")

@app.command()
def ingest(input_dir: Path, out_root: Path, vendor_db: Path = Path("app/vendor_db.yml")):
    rows = []
    out_root.mkdir(parents=True, exist_ok=True)
    for p in input_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".pdf",".png",".jpg",".jpeg",".tif",".tiff"}:
            try:
                res = process_file(p, out_root, vendor_db)
                rows.append({"source": str(p), **res})
            except Exception as e:
                rows.append({"source": str(p), "error": str(e)})
    if rows:
        df = pd.DataFrame(rows)
        log = out_root / "audit_log.csv"
        if log.exists():
            df0 = pd.read_csv(log)
            df = pd.concat([df0, df], ignore_index=True)
        df.to_csv(log, index=False)
        typer.echo(f"Protokoll → {log}")

if __name__ == "__main__":
    app()
