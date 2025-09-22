import time
import shutil
import logging
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

try:
    # zentrale Verarbeitung – erwarte Funktion in sorter.py
    from sorter import process_pdf
except Exception as e:
    raise SystemExit("hotfolder.py erwartet eine process_pdf(pdf_path, ...) Funktion in sorter.py") from e


class PDFHandler(FileSystemEventHandler):
    def __init__(self, in_dir: Path, done_dir: Path, err_dir: Path, config_path: str, patterns_path: str):
        self.in_dir = Path(in_dir)
        self.done_dir = Path(done_dir)
        self.err_dir = Path(err_dir)
        self.config_path = config_path
        self.patterns_path = patterns_path

    def _wait_until_stable(self, path: Path, tries: int = 30, delay: float = 0.2) -> bool:
        """Warte kurz, bis eine neue Datei nicht mehr geschrieben wird."""
        last_size = -1
        for _ in range(tries):
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                return False
            if size == last_size:
                return True
            last_size = size
            time.sleep(delay)
        return True

    def on_created(self, event):
        if event.is_directory:
            return
        src = Path(event.src_path)
        if src.suffix.lower() != ".pdf":
            return

        if not self._wait_until_stable(src):
            logging.warning("Datei verschwand während Stabilisierung: %s", src)
            return

        try:
            # process_pdf soll den endgültigen Zielpfad (str/Path) zurückgeben
            out_path = process_pdf(src, self.config_path, self.patterns_path)
            self.done_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(self.done_dir / src.name))
            logging.info("verarbeitet: %s -> %s", src, out_path)
        except Exception as e:
            self.err_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(self.err_dir / src.name))
            logging.exception("Fehler bei %s: %s", src, e)


def run_hotfolder(in_dir, done_dir, err_dir, config="config.yaml", patterns="patterns.yaml"):
    in_dir = Path(in_dir)
    done_dir = Path(done_dir)
    err_dir = Path(err_dir)
    for p in (in_dir, done_dir, err_dir):
        p.mkdir(parents=True, exist_ok=True)

    handler = PDFHandler(in_dir, done_dir, err_dir, config, patterns)
    observer = Observer()
    observer.schedule(handler, str(in_dir), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Überwacht einen Eingangsordner und verarbeitet PDFs.")
    ap.add_argument("--in", dest="in_dir", default="inbox", help="Eingangsordner")
    ap.add_argument("--done", dest="done_dir", default="processed", help="Archivordner für erfolgreich verarbeitete Eingänge")
    ap.add_argument("--err", dest="err_dir", default="error", help="Ablage fehlerhafter Eingänge")
    ap.add_argument("--config", default="config.yaml", help="Pfad zur Konfiguration")
    ap.add_argument("--patterns", default="patterns.yaml", help="Pfad zu Musterdefinitionen")
    args = ap.parse_args()
    run_hotfolder(args.in_dir, args.done_dir, args.err_dir, args.config, args.patterns)
