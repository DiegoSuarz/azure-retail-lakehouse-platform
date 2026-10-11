"""Comprueba los lotes funcionales antes de publicarlos en Bronze."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

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
    manifest_path = directory / "manifest.json"
    require(manifest_path.is_file(), f"Manifiesto ausente: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    require(
        type(manifest.get("schema_version")) is int
        and manifest["schema_version"] == 1,
        f"Versión incorrecta: {directory.name}",
    )
    require(
        manifest.get("batch_id") == directory.name,
        f"Identidad incorrecta: {directory.name}",
    )
    files = manifest.get("files")
    require(
        isinstance(files, dict) and bool(files),
        f"Inventario vacío o inválido: {directory.name}",
    )
    require(
        set(files) <= ALLOWED_FILES,
        f"Archivos no admitidos: {directory.name}",
    )
    require(
        ("orders.csv" in files) == ("order_items.csv" in files),
        f"Pedidos y líneas deben entregarse juntos: {directory.name}",
    )

    actual = {path.name for path in directory.iterdir()}
    require(
        actual == set(files) | {"manifest.json"},
        f"Archivos ausentes o adicionales: {directory.name}",
    )

    for filename, metadata in files.items():
        require(
            isinstance(metadata, dict),
            f"Metadatos inválidos: {directory.name}/{filename}",
        )
        path = directory / filename
        require(path.is_file(), f"No es un archivo: {path}")
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        require(
            digest == metadata.get("sha256"),
            f"Hash incorrecto: {path}",
        )
        expected_count = metadata.get("row_count")
        require(
            type(expected_count) is int and expected_count >= 0,
            f"Conteo declarado inválido: {path}",
        )
        require(
            count_rows(filename, payload) == expected_count,
            f"Conteo diferente del manifiesto: {path}",
        )
        print(f"PASS: {directory.name}/{filename}")

    return manifest


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
