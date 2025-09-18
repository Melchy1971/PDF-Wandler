from fastapi import FastAPI, UploadFile, File
from pathlib import Path
from .postprocess import process_file

app = FastAPI()

@app.post("/ingest")
async def ingest(file: UploadFile = File(...), out_root: str = "./ablage"):
    tmp = Path(f"/tmp/{file.filename}")
    tmp.write_bytes(await file.read())
    res = process_file(tmp, Path(out_root), Path("app/vendor_db.yml"))
    return res
