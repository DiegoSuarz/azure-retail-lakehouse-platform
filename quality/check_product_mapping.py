"""Valida las asociaciones educativas entre productos locales y externos."""

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quality.api_extraction_input import ExtractionError, read_extraction
from quality.dummyjson_rules import evaluate_dummyjson
from quality.reference_data import load_initial_reference

COLUMNS = [
    "source_system", "external_product_id", "product_id",
    "mapping_type", "mapping_note",
]


def positive_id(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        identifier = int(value)
        if identifier > 0:
            return identifier
    return None


def evaluate_mapping(payload, local_ids, external_ids):
    try:
        reader = csv.DictReader(
            io.StringIO(payload.decode("utf-8"), newline=""), strict=True
        )
        if reader.fieldnames != COLUMNS:
            raise ExtractionError("DQ016", "Encabezado del mapeo incompatible")
        rows = list(reader)
    except (UnicodeError, csv.Error) as error:
        raise ExtractionError("DQ016", f"CSV incompatible: {error}") from error

    if not rows:
        raise ExtractionError("DQ016", "Archivo de mapeo vacío")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ExtractionError("DQ016", "Cantidad de columnas incompatible")

    local_counts = Counter(
        identifier for row in rows
        if (identifier := positive_id(row["product_id"])) is not None
    )
    external_counts = Counter(
        identifier for row in rows
        if (identifier := positive_id(row["external_product_id"])) is not None
    )
    results = []

    for number, row in enumerate(rows, 1):
        errors = []

        def issue(field, message):
            errors.append({"code": "DQ016", "field": field, "message": message})

        local_id = positive_id(row["product_id"])
        external_id = positive_id(row["external_product_id"])

        if row["source_system"] != "dummyjson":
            issue("source_system", "Fuente distinta de dummyjson")
        if row["mapping_type"] != "synthetic_demo":
            issue("mapping_type", "Tipo de asociación incompatible")
        if not row["mapping_note"].strip():
            issue("mapping_note", "Explicación educativa ausente")

        for field, identifier, reference, counts in (
            ("product_id", local_id, local_ids, local_counts),
            ("external_product_id", external_id, external_ids, external_counts),
        ):
            if identifier is None:
                issue(field, "Identificador no entero positivo")
            else:
                if identifier not in reference:
                    issue(field, "Producto inexistente en la referencia validada")
                if counts[identifier] > 1:
                    issue(field, "Producto asociado más de una vez")

        results.append({
            "record_number": number,
            "business_key": {
                "product_id": local_id,
                "external_product_id": external_id,
            },
            "status": "rejected" if errors else "accepted",
            "errors": errors,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mapping", type=Path,
        default=ROOT / "sources/reference/product_external_mapping.csv",
    )
    parser.add_argument("--dummyjson-run-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    mapping_path = args.mapping.resolve()
    report_path = args.report.resolve()
    reference_dir = args.dummyjson_run_dir.resolve()
    if report_path.exists():
        parser.error("El informe ya existe.")
    if report_path == mapping_path or report_path.is_relative_to(reference_dir):
        parser.error("El informe debe estar fuera de las entradas.")

    report = {
        "schema_version": 1,
        "processing_run_id": str(uuid4()),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "product_external_mapping",
        "mapping_path": str(mapping_path),
        "mapping_sha256": None,
        "dummyjson_ingestion_run_id": None,
        "status": "blocked",
        "incorporation_allowed": False,
        "records": None,
        "reconciliation": "not_evaluated",
        "errors": [],
        "rejected_records": [],
    }

    try:
        payload = mapping_path.read_bytes()
        report["mapping_sha256"] = hashlib.sha256(payload).hexdigest()
        manifest, responses, payloads = read_extraction(reference_dir)
        products = evaluate_dummyjson(manifest, responses, payloads)
        if any(row["status"] != "accepted" for row in products):
            raise ExtractionError("DQ016", "Catálogo externo con registros rechazados")
        report["dummyjson_ingestion_run_id"] = manifest["ingestion_run_id"]

        reference = load_initial_reference()
        local_ids = {int(row["product_id"]) for row in reference["products"]}
        external_ids = {
            row["values"]["external_product_id"] for row in products
        }
        results = evaluate_mapping(payload, local_ids, external_ids)
        rejected = [row for row in results if row["status"] == "rejected"]
        report.update({
            "status": "blocked" if rejected else "validated",
            "incorporation_allowed": not rejected,
            "records": {
                "read": len(results),
                "accepted": len(results) - len(rejected),
                "rejected": len(rejected),
            },
            "reconciliation": "passed",
            "rejected_records": rejected,
        })
    except ExtractionError as error:
        report["errors"].append({"code": error.code, "message": str(error)})
    except (OSError, ValueError, RuntimeError) as error:
        report["errors"].append({
            "code": "DQ016", "message": f"Referencia o entrada inválida: {error}",
        })

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    print(f"RESULTADO: {report['status']}")
    print(f"REGISTROS: {report['records']}")
    print(f"INFORME: {report_path}")
    return 0 if report["incorporation_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
