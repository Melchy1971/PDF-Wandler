import streamlit as st
from pathlib import Path
from .postprocess import process_file

st.title("Rechnungsablage – KI‑gestützt")
root = Path(st.text_input("Zielordner", "./ablage")).expanduser()
vendor_db = Path("app/vendor_db.yml")

files = st.file_uploader("PDF/Bilder auswählen", accept_multiple_files=True, type=["pdf","png","jpg","jpeg","tif","tiff"])

for f in files or []:
    tmp = Path(f"/tmp/{f.name}")
    tmp.write_bytes(f.read())
    res = process_file(tmp, root, vendor_db)
    st.write(res)
