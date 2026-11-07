"""Valida identidad, archivos y estructura sin modificar entradas."""

import argparse
import csv
import io
import json
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


def read_batch(directory, expected_batch_id=None, expected_files=None):
    """Lee y valida un lote sin manifiesto; devuelve identidad, bytes y conteos."""
    directory = Path(directory)
    check(
        directory.is_dir() and not directory.is_symlink(),
        "DQ002", "Directorio de lote ausente o enlace simbólico",
    )
    batch_id = directory.name
    check(
        bool(batch_id.strip()) and batch_id not in {".", ".."}
        and "/" not in batch_id and "\\" not in batch_id,
        "DQ001", "Identidad de lote inválida",
    )
    if expected_batch_id is not None:
        check(
            batch_id == expected_batch_id,
            "DQ001", "Identidad diferente de la esperada",
        )

    paths = list(directory.iterdir())
    filenames = {path.name for path in paths}
    check(
        bool(filenames) and filenames <= ALLOWED,
        "DQ002", "Lote vacío o archivos no admitidos",
    )
    check(
        ("orders.csv" in filenames) == ("order_items.csv" in filenames),
        "DQ002", "Pedidos y líneas deben entregarse juntos",
    )
    if expected_files is not None:
        required = set(expected_files)
        check(
            bool(required) and required <= ALLOWED,
            "DQ001", "Conjunto esperado de archivos incompatible",
        )
        check(
            filenames == required,
            "DQ002", "Archivos diferentes de los esperados",
        )

    payloads = {}
    counts = {}
    for path in sorted(paths):
        check(
            path.is_file() and not path.is_symlink(),
            "DQ002", "Entrada no regular o enlace simbólico", path.name,
        )
        payload = path.read_bytes()
        counts[path.name] = parse_file(path.name, payload)
        payloads[path.name] = payload

    return batch_id, payloads, counts


def validate_transport(directory, expected_batch_id=None, expected_files=None):
    """Valida el lote sin manifiesto y devuelve identidad y conteos."""
    batch_id, _, counts = read_batch(
        directory, expected_batch_id, expected_files
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
    print("ALCANCE: identidad, archivos y estructura; reglas de negocio pendientes.")
    return 0 if report["status"] == "transport_validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
