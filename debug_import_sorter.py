# Diagnose-Skript: prüft Import und Funktionen der sorter.py
import sys, importlib, traceback

print("Python:", sys.version)
print("sys.path[0:5]:", sys.path[0:5])

try:
    sorter = importlib.import_module("sorter")
    print("sorter importiert von:", getattr(sorter, "__file__", "<unknown>"))
    for name in ("extract_text_from_pdf","analyze_pdf","process_pdf","process_all"):
        print(f"{name} vorhanden?", hasattr(sorter, name))
except Exception as e:
    print("IMPORTFEHLER:", e)
    traceback.print_exc()
