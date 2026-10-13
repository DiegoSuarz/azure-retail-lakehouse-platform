"""Genera informe y cuarentena local de una extracción de API."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quality.api_extraction_input import ExtractionError, read_extraction
from quality.bcrpdata_rules import evaluate_bcrpdata
from quality.dummyjson_rules import evaluate_dummyjson

SCHEMA = pa.schema([
    pa.field("source_system", pa.string()),
    pa.field("entity", pa.string()),
    pa.field("ingestion_run_id", pa.string()),
    pa.field("processing_run_id", pa.string()),
    pa.field("source_file", pa.string()),
    pa.field("source_sha256", pa.string()),
    pa.field("record_number", pa.int64()),
    pa.field("record_pointer", pa.string()),
    pa.field("business_key_json", pa.string()),
    pa.field("raw_response", pa.string()),
    pa.field("status", pa.string()),
    pa.field("errors", pa.list_(pa.struct([
        pa.field("code", pa.string()),
        pa.field("field", pa.string()),
        pa.field("message", pa.string()),
    ]))),
    pa.field("evaluated_at", pa.timestamp("us", tz="UTC")),
])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source_dir = args.run_dir.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        parser.error("La carpeta de salida ya existe.")
    if output.is_relative_to(source_dir):
        parser.error("La salida debe estar fuera de la extracción.")

    processing_id = str(uuid4())
    evaluated_at = datetime.now(timezone.utc)
    report = {
        "schema_version": 1,
        "processing_run_id": processing_id,
        "evaluated_at": evaluated_at.isoformat(),
        "input_path": str(source_dir),
        "scope": "preserved_api_extraction",
        "source_system": None,
        "ingestion_run_id": None,
        "status": "blocked",
        "records_processed": None,
        "records": None,
        "reconciliation": "not_evaluated",
        "manifest_controls": "not_evaluated",
        "availability": None,
        "errors": [],
        "quarantine_files": [],
    }
    manifest = None
    records = None
    payloads = None

    try:
        manifest, responses, payloads = read_extraction(source_dir)
        source = manifest["source_system"]
        report["source_system"] = source
        report["ingestion_run_id"] = manifest["ingestion_run_id"]

        evaluator = (
            evaluate_dummyjson if source == "dummyjson"
            else evaluate_bcrpdata
        )
        records = evaluator(manifest, responses, payloads)
        counts = Counter(row["status"] for row in records)
        if set(counts) - {"accepted", "rejected"}:
            raise ExtractionError("DQ017", "Clasificación inesperada")
        if len(records) != counts["accepted"] + counts["rejected"]:
            raise ExtractionError("DQ017", "Conteos no reconciliados")

        report.update({
            "status": "completed_for_scope",
            "records_processed": len(records),
            "records": {
                "read": len(records),
                "accepted": counts["accepted"],
                "rejected": counts["rejected"],
            },
            "reconciliation": "passed",
            "manifest_controls": (
                "passed" if counts["rejected"] == 0
                else "not_fully_validated"
            ),
        })
        if source == "bcrpdata":
            report["availability"] = {
                "available": sum(row["available"] is True for row in records),
                "unavailable": sum(row["available"] is False for row in records),
                "not_evaluated": sum(row["available"] is None for row in records),
            }
    except ExtractionError as error:
        report["errors"].append({
            "code": error.code,
            "message": str(error),
        })

    output.mkdir(parents=True, exist_ok=False)

    if report["status"] == "completed_for_scope":
        source = manifest["source_system"]
        entity = "products" if source == "dummyjson" else "exchange_rates"
        quarantine = []
        for record in records:
            if record["status"] != "rejected":
                continue
            relative = record["source_file"]
            payload = payloads[relative]
            position = record["record_number"]
            array_name = "products" if source == "dummyjson" else "periods"
            quarantine.append({
                "source_system": source,
                "entity": entity,
                "ingestion_run_id": manifest["ingestion_run_id"],
                "processing_run_id": processing_id,
                "source_file": str(source_dir / relative),
                "source_sha256": hashlib.sha256(payload).hexdigest(),
                "record_number": position,
                "record_pointer": f"/{array_name}/{position - 1}",
                "business_key_json": json.dumps(
                    record["business_key"], ensure_ascii=False,
                ),
                "raw_response": payload.decode("utf-8"),
                "status": record["status"],
                "errors": record["errors"],
                "evaluated_at": evaluated_at,
            })

        if quarantine:
            path = output / f"{entity}_quarantine.parquet"
            pq.write_table(
                pa.Table.from_pylist(quarantine, schema=SCHEMA),
                path, compression="snappy",
            )
            content = path.read_bytes()
            report["quarantine_files"].append({
                "path": path.name,
                "row_count": len(quarantine),
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })

    report_path = output / "report.json"
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    print(f"RESULTADO: {report['status']}")
    print(f"REGISTROS: {report['records']}")
    if report["availability"] is not None:
        print(f"DISPONIBILIDAD: {report['availability']}")
    for error in report["errors"]:
        print(f"{error['code']}: {error['message']}")
    print(f"ARCHIVOS DE CUARENTENA: {len(report['quarantine_files'])}")
    print(f"INFORME: {report_path}")
    return 0 if report["status"] == "completed_for_scope" else 1


if __name__ == "__main__":
    raise SystemExit(main())
