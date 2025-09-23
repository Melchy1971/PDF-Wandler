#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, time, shutil, sys
from pathlib import Path

try:
    import sorter
except Exception as e:
    print(f"[Hotfolder] sorter.py konnte nicht importiert werden: {e}", file=sys.stderr)
    sorter = None

def is_locked(path: Path) -> bool:
    try:
        s1 = path.stat().st_size
        time.sleep(0.15)
        s2 = path.stat().st_size
        return s1 != s2
    except Exception:
        return True

def process_one(pdf: Path, cfg_path: str, patterns_path: str, out_ok: Path, out_err: Path) -> None:
    try:
        if sorter and hasattr(sorter, "process_pdf"):
            res = sorter.process_pdf(str(pdf), config_path=cfg_path, patterns_path=patterns_path, simulate=False)
            if isinstance(res, str) and Path(res).exists():
                print(f"[Hotfolder] OK: {pdf.name} -> {res}")
            else:
                target = out_ok / pdf.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(pdf), str(target))
                print(f"[Hotfolder] OK (fallback move): {pdf.name} -> {target}")
        else:
            target = out_ok / pdf.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(pdf), str(target))
            print(f"[Hotfolder] OK (no sorter): {pdf.name} -> {target}")
    except Exception as e:
        target = out_err / pdf.name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(pdf), str(target))
        except Exception:
            pass
        print(f"[Hotfolder] FEHLER: {pdf.name}: {e}", file=sys.stderr)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inbox", required=True, help="Eingangsordner")
    ap.add_argument("--done", dest="done", required=True, help="Ausgangsordner (OK)")
    ap.add_argument("--err", dest="err", required=True, help="Fehlerordner")
    ap.add_argument("--config", dest="config", default="config.yaml")
    ap.add_argument("--patterns", dest="patterns", default="patterns.yaml")
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    inbox = Path(args.inbox)
    out_ok = Path(args.done)
    out_err = Path(args.err)
    inbox.mkdir(parents=True, exist_ok=True)
    out_ok.mkdir(parents=True, exist_ok=True)
    out_err.mkdir(parents=True, exist_ok=True)

    print(f"[Hotfolder] Starte. Inbox={inbox} OK={out_ok} ERR={out_err} Interval={args.interval}s")
    try:
        while True:
            try:
                files = sorted(p for p in inbox.glob("*.pdf"))
                for pdf in files:
                    if is_locked(pdf):
                        continue
                    process_one(pdf, args.config, args.patterns, out_ok, out_err)
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("[Hotfolder] Stop (KeyboardInterrupt)")
                break
            except Exception as e:
                print(f"[Hotfolder] Laufzeitfehler: {e}", file=sys.stderr)
                time.sleep(args.interval)
    finally:
        print("[Hotfolder] Ende")

if __name__ == "__main__":
    main()
