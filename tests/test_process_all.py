import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sorter


def test_process_all_processes_pdf_and_PDF(tmp_path, monkeypatch):
    input_dir = tmp_path / "inbox"
    output_dir = tmp_path / "processed"
    input_dir.mkdir()
    output_dir.mkdir()

    lowercase_pdf = input_dir / "doc1.pdf"
    uppercase_pdf = input_dir / "doc2.PDF"
    ignored_file = input_dir / "ignore.txt"

    for path in (lowercase_pdf, uppercase_pdf, ignored_file):
        path.write_text("dummy")

    processed_files = []

    def fake_process_pdf(pdf_path, **kwargs):
        processed_files.append(Path(pdf_path).name)
        return {
            "destination": str(output_dir / Path(pdf_path).name),
            "validation_status": "ok",
            "status": "ok",
        }

    monkeypatch.setattr(sorter, "process_pdf", fake_process_pdf)

    stop_calls = 0

    def stop_fn():
        nonlocal stop_calls
        stop_calls += 1
        return False

    progress_calls = []

    def progress_fn(idx, total, path, result):
        progress_calls.append(
            SimpleNamespace(idx=idx, total=total, path=Path(path).name, destination=result.destination)
        )

    sorter.process_all(
        config={
            "input_dir": str(input_dir),
            "output_dir": str(output_dir),
            "dry_run": True,
            "csv_log_path": "",
        },
        patterns={},
        stop_fn=stop_fn,
        progress_fn=progress_fn,
    )

    assert processed_files == ["doc1.pdf", "doc2.PDF"]
    assert all(call.total == 2 for call in progress_calls)
    assert [call.path for call in progress_calls] == ["doc1.pdf", "doc2.PDF"]
    assert stop_calls == len(processed_files)
    assert "ignore.txt" not in processed_files
