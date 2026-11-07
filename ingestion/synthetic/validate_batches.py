"""Comprueba los lotes funcionales antes de publicarlos en Bronze."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quality"))

from validate_batch_transport import read_batch, TransportError

BATCHES = ("batch_001", "batch_002", "batch_003", "batch_004")
ALLOWED_FILES = {"orders.csv", "order_items.csv", "changes.jsonl"}


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def count_rows(filename, payload):
    text = payload.decode("utf-8")
    if filename.endswith(".csv"):
        reader = csv.reader(io.StringIO(text, newline=""))
        header = next(reader, None)
        require(bool(header), f"Encabezado ausente: {filename}")
        rows = list(reader)
        require(
            all(len(row) == len(header) for row in rows),
            f"Cantidad de columnas incorrecta: {filename}",
        )
        return len(rows)

    events = [
        json.loads(line) for line in text.splitlines() if line.strip()
    ]
    require(
        all(isinstance(event, dict) for event in events),
        f"Eventos JSON inválidos: {filename}",
    )
    return len(events)


def validate_batch(directory):
    """Valida datos y calcula una referencia temporal para la preparación."""
    directory = Path(directory)
    try:
        batch_id, payloads, counts = read_batch(
            directory, expected_batch_id=directory.name
        )
    except TransportError as error:
        raise SystemExit(f"FAIL: {error.code}: {error}") from error

    files = {}
    for filename, payload in payloads.items():
        files[filename] = {
            "row_count": counts[filename],
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        print(f"PASS: {batch_id}/{filename}")

    return {"batch_id": batch_id, "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("data/incremental/functional"),
    )
    args = parser.parse_args()

    for batch_id in BATCHES:
        directory = args.source_dir / batch_id
        require(directory.is_dir(), f"Lote ausente: {batch_id}")
        validate_batch(directory)

    print("PASS: cuatro lotes preparados para la ingesta.")
    print("ALCANCE: integridad de transporte; no publica archivos en Azure.")


if __name__ == "__main__":
    main()
