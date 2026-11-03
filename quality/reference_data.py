"""Lee los cinco CSV iniciales y comprueba su estructura básica."""

import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITIES = {"categories", "products", "customers", "orders", "order_items"}


def load_initial_reference(directory=None):
    directory = Path(directory) if directory else ROOT / "data/initial"
    expected_files = {f"{name}.csv" for name in ENTITIES}
    if {path.name for path in directory.glob("*.csv")} != expected_files:
        raise RuntimeError("Referencia inicial: conjunto CSV incompatible")

    datasets = {}
    for name in sorted(ENTITIES):
        filename = f"{name}.csv"
        payload = (directory / filename).read_bytes()
        reader = csv.DictReader(
            io.StringIO(payload.decode("utf-8"), newline="")
        )
        rows = list(reader)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise RuntimeError(f"Referencia inicial: cabecera incorrecta en {filename}")
        if not rows:
            raise RuntimeError(f"Referencia inicial vacía: {filename}")
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise RuntimeError(f"Referencia inicial: estructura incorrecta en {filename}")
        datasets[name] = rows

    return datasets
