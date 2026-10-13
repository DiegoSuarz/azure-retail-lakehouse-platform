"""Valida DQ001–DQ004 sin aplicar reglas de negocio ni modificar entradas."""

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

HEADERS = {
    "orders.csv": (
        "order_id,customer_id,order_date,status,currency_code,"
        "created_at,updated_at"
    ).split(","),
    "order_items.csv": (
        "order_id,line_number,product_id,quantity,unit_price,"
        "discount_amount,created_at,updated_at"
    ).split(","),
}
ALLOWED = set(HEADERS) | {"changes.jsonl"}


class TransportError(Exception):
    def __init__(self, code, message, filename=None):
        super().__init__(message)
        self.code = code
        self.filename = filename


def check(condition, code, message, filename=None):
    if not condition:
        raise TransportError(code, message, filename)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Campo JSON repetido: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Constante JSON inválida: {value}")


def parse_json(payload):
    return json.loads(
        payload,
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )


def parse_file(filename, payload):
    try:
        text = payload.decode("utf-8")
        if filename in HEADERS:
            reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            header = next(reader, None)
            check(
                header == HEADERS[filename], "DQ004",
                "Encabezado incompatible con el contrato", filename,
            )
            rows = list(reader)
            check(
                all(len(row) == len(header) for row in rows),
                "DQ004", "Cantidad de columnas incompatible", filename,
            )
            return len(rows)

        lines = [line for line in text.splitlines() if line.strip()]
        for line in lines:
            check(
                isinstance(parse_json(line), dict),
                "DQ004", "Cada evento debe ser un objeto JSON", filename,
            )
        return len(lines)
    except (UnicodeError, ValueError, csv.Error) as error:
        raise TransportError("DQ004", str(error), filename) from error


def validate_transport(directory, expected_batch_id=None):
    manifest_path = directory / "manifest.json"
    check(manifest_path.is_file(), "DQ001", "Manifiesto ausente")
    try:
        manifest = parse_json(manifest_path.read_bytes())
    except (UnicodeError, ValueError) as error:
        raise TransportError("DQ001", "Manifiesto JSON inválido") from error

    check(isinstance(manifest, dict), "DQ001", "Manifiesto no es un objeto")
    check(
        type(manifest.get("schema_version")) is int
        and manifest["schema_version"] == 1,
        "DQ001", "Versión de contrato incompatible",
    )
    batch_id = manifest.get("batch_id")
    check(
        isinstance(batch_id, str) and bool(batch_id.strip())
        and batch_id not in {".", ".."}
        and "/" not in batch_id and "\\" not in batch_id,
        "DQ001", "Identidad de lote inválida",
    )
    if expected_batch_id is not None:
        check(
            batch_id == expected_batch_id,
            "DQ001", "Identidad diferente de la esperada",
        )

    created = manifest.get("created_at")
    check(
        isinstance(created, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", created),
        "DQ001", "created_at debe ser UTC con milisegundos y sufijo Z",
    )
    try:
        datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError as error:
        raise TransportError("DQ001", "created_at contiene una fecha inválida") from error

    files = manifest.get("files")
    check(
        isinstance(files, dict) and bool(files) and set(files) <= ALLOWED,
        "DQ001", "Inventario vacío o archivos no admitidos",
    )
    check(
        ("orders.csv" in files) == ("order_items.csv" in files),
        "DQ001", "Pedidos y líneas deben entregarse juntos",
    )
    actual = {path.name for path in directory.iterdir()}
    check(
        actual == set(files) | {"manifest.json"},
        "DQ002", "Archivos ausentes o adicionales",
    )

    payloads = {}
    for filename, metadata in files.items():
        check(isinstance(metadata, dict), "DQ001", "Metadatos inválidos", filename)
        expected_hash = metadata.get("sha256")
        check(
            isinstance(expected_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_hash),
            "DQ002", "SHA-256 declarado inválido", filename,
        )
        expected_count = metadata.get("row_count")
        check(
            type(expected_count) is int and expected_count >= 0,
            "DQ003", "Conteo declarado inválido", filename,
        )
        path = directory / filename
        check(
            path.is_file() and not path.is_symlink(),
            "DQ002", "Archivo ausente o enlace simbólico", filename,
        )
        payload = path.read_bytes()
        check(
            hashlib.sha256(payload).hexdigest() == expected_hash,
            "DQ002", "Hash diferente del manifiesto", filename,
        )
        if "size_bytes" in metadata:
            check(
                type(metadata["size_bytes"]) is int
                and metadata["size_bytes"] == len(payload),
                "DQ002", "Tamaño diferente del manifiesto", filename,
            )
        payloads[filename] = payload

    counts = {}
    for filename, payload in payloads.items():
        counts[filename] = parse_file(filename, payload)
        check(
            counts[filename] == files[filename]["row_count"],
            "DQ003", "Conteo diferente del manifiesto", filename,
        )

    return batch_id, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--expected-batch-id")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if args.report.exists():
        parser.error("El informe ya existe; no se sobrescribirá.")

    directory = args.batch_dir.resolve()
    report_path = args.report.resolve()
    if report_path.is_relative_to(directory):
        parser.error("El informe debe guardarse fuera del lote.")

    report = {
        "schema_version": 1,
        "processing_run_id": str(uuid4()),
        "source_system": "synthetic",
        "input_directory": str(directory),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "transport_only",
        "status": "blocked",
        "business_rules_evaluated": False,
        "records_processed": None,
        "errors": [],
    }

    try:
        batch_id, counts = validate_transport(
            directory, args.expected_batch_id,
        )
        report.update({
            "batch_id": batch_id,
            "status": "transport_validated",
            "file_row_counts": counts,
        })
    except TransportError as error:
        report["errors"].append({
            "code": error.code,
            "filename": error.filename,
            "message": str(error),
        })
    except OSError as error:
        report["errors"].append({
            "code": "DQ002",
            "filename": None,
            "message": f"No se pudo leer la entrada: {error}",
        })

    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    print(f"RESULTADO: {report['status']}")
    for error in report["errors"]:
        print(f"{error['code']}: {error['message']}")
    print(f"INFORME: {args.report}")
    print("ALCANCE: integridad y estructura; reglas de negocio pendientes.")
    return 0 if report["status"] == "transport_validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
