"""Lee referencias iniciales comprobando su integridad."""

import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITIES = {"categories", "products", "customers", "orders", "order_items"}


def load_initial_reference(directory=None):
    directory = Path(directory) if directory else ROOT / "data/initial"
    manifest = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    expected_files = {f"{name}.csv" for name in ENTITIES}
    if set(manifest["files"]) != expected_files:
        raise RuntimeError("Referencia inicial: inventario incompatible")

    datasets = {}
    for name in sorted(ENTITIES):
        filename = f"{name}.csv"
        payload = (directory / filename).read_bytes()
        metadata = manifest["files"][filename]
        if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
            raise RuntimeError(f"Referencia inicial: hash incorrecto en {filename}")

        reader = csv.DictReader(
            io.StringIO(payload.decode("utf-8"), newline="")
        )
        rows = list(reader)
        if len(rows) != metadata["row_count"]:
            raise RuntimeError(f"Referencia inicial: conteo incorrecto en {filename}")
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise RuntimeError(f"Referencia inicial: estructura incorrecta en {filename}")
        datasets[name] = rows

    return datasets
