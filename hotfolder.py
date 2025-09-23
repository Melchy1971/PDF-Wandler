#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable, Optional, Union

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

def _load_unknown_dir_name(cfg_path: str) -> str:
    default = "unbekannt"
    if not cfg_path:
        return default
    try:
        import yaml  # type: ignore
    except Exception:
        return default
    try:
        with open(cfg_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if isinstance(data, dict):
            value = data.get("unknown_dir_name")
            if isinstance(value, str):
                value = value.strip()
                if value:
                    return value
    except FileNotFoundError:
        return default
    except Exception as exc:
        print(
            f"[Hotfolder] Hinweis: unknown_dir_name konnte nicht aus {cfg_path} gelesen werden: {exc}",
            file=sys.stderr,
        )
    return default


def _possible_path_values(result: object) -> Iterable[Union[str, Path]]:
    if isinstance(result, (str, Path)):
        yield result
        return
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
        if isinstance(first, (str, Path)):
            yield first
    if isinstance(result, dict):  # type: ignore[arg-type]
        for key in (
            "target",
            "destination",
            "output_path",
            "path",
            "dest",
            "target_path",
            "destination_path",
            "resolved_path",
            "moved_path",
        ):
            value = result.get(key)  # type: ignore[index]
            if isinstance(value, (str, Path)):
                yield value
        return
    for key in (
        "target",
        "destination",
        "output_path",
        "path",
        "dest",
        "target_path",
        "destination_path",
        "resolved_path",
        "moved_path",
    ):
        if hasattr(result, key):
            value = getattr(result, key)
            if isinstance(value, (str, Path)):
                yield value


def _resolve_target_path(result: object) -> Optional[Path]:
    for candidate in _possible_path_values(result):
        text = str(candidate).strip()
        if text:
            return Path(text)
    return None


def _extract_status_hint(result: object) -> str:
    def _clean(value: object) -> Optional[str]:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    if isinstance(result, dict):  # type: ignore[arg-type]
        for key in ("status", "validation_status", "result", "state"):
            val = _clean(result.get(key))  # type: ignore[index]
            if val:
                return val
    for key in ("status", "validation_status", "result", "state"):
        if hasattr(result, key):
            val = _clean(getattr(result, key))
            if val:
                return val
    return _clean(result) or ""


def _move_to(pdf: Path, target_dir: Path, label: str, reason: Optional[str] = None) -> None:
    target = target_dir / pdf.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdf), str(target))
    suffix = f" ({reason})" if reason else ""
    print(f"[Hotfolder] {label}: {pdf.name} -> {target}{suffix}")


def process_one(
    pdf: Path,
    cfg_path: str,
    patterns_path: str,
    out_ok: Path,
    out_err: Path,
    out_unknown: Path,
) -> None:
    try:
        if sorter and hasattr(sorter, "process_pdf"):
            res = sorter.process_pdf(
                str(pdf), config_path=cfg_path, patterns_path=patterns_path, simulate=False
            )
            target = _resolve_target_path(res)
            if target is not None:
                print(f"[Hotfolder] OK: {pdf.name} -> {target}")
                return
            reason = _extract_status_hint(res) or "kein Zielpfad"
            _move_to(pdf, out_unknown, "UNKNOWN", reason)
        else:
            _move_to(pdf, out_unknown, "UNKNOWN", "sorter.process_pdf nicht verfügbar")
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
    unknown_dir_name = _load_unknown_dir_name(args.config)
    out_unknown = out_ok / unknown_dir_name
    inbox.mkdir(parents=True, exist_ok=True)
    out_ok.mkdir(parents=True, exist_ok=True)
    out_err.mkdir(parents=True, exist_ok=True)
    out_unknown.mkdir(parents=True, exist_ok=True)

    print(
        f"[Hotfolder] Starte. Inbox={inbox} OK={out_ok} UNKNOWN={out_unknown} ERR={out_err} Interval={args.interval}s"
    )
    try:
        while True:
            try:
                files = sorted(p for p in inbox.glob("*.pdf"))
                for pdf in files:
                    if is_locked(pdf):
                        continue
                    process_one(pdf, args.config, args.patterns, out_ok, out_err, out_unknown)
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
