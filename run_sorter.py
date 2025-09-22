import json
from pathlib import Path
import typer

try:
    from sorter import process_pdf, analyze_pdf
except Exception as e:
    raise SystemExit(
        "run_sorter.py erwartet process_pdf(input, ...) und analyze_pdf(input, ...) in sorter.py"
    ) from e

app = typer.Typer(help="PDF-Wandler CLI – Analyse, Umbenennen, Hotfolder-Steuerung")


@app.command()
def analyze(
    input: str = typer.Argument(..., help="Pfad zur PDF oder zu einem Ordner"),
    config: str = typer.Option("config.yaml", help="Konfiguration"),
    patterns: str = typer.Option("patterns.yaml", help="Musterdefinitionen"),
    json_out: str = typer.Option(None, help="Pfad für JSON-Export der Metadaten"),
):
    """Extrahiert Metadaten (Rechnungsnummer, Datum, etc.)."""
    meta = analyze_pdf(Path(input), config, patterns)
    if json_out:
        Path(json_out).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        typer.echo(json.dumps(meta, ensure_ascii=False, indent=2))


@app.command()
def rename(
    input: str = typer.Argument(..., help="Pfad zur PDF oder zu einem Ordner"),
    config: str = typer.Option("config.yaml"),
    patterns: str = typer.Option("patterns.yaml"),
    dry_run: bool = typer.Option(False, help="Nur vorschlagen, keine Dateien verschieben"),
):
    """Benennt um und verschiebt – oder zeigt mit --dry-run nur das Ziel an."""
    result = process_pdf(Path(input), config, patterns, simulate=dry_run)
    typer.echo(result)


@app.command()
def hotfolder(
    inbox: str = typer.Option("inbox", help="Eingangsordner"),
    done: str = typer.Option("processed", help="Ablage erfolgreicher Eingänge"),
    err: str = typer.Option("error", help="Ablage fehlerhafter Eingänge"),
    config: str = typer.Option("config.yaml"),
    patterns: str = typer.Option("patterns.yaml"),
):
    """Startet den Hotfolder-Dienst im Vordergrund."""
    from hotfolder import run_hotfolder

    run_hotfolder(inbox, done, err, config, patterns)


if __name__ == "__main__":
    app()
