"""Genera informe y cuarentena local para pedidos CSV nuevos."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from new_order_rules import evaluate_new_orders
from reference_data import load_initial_reference
from validate_batch_transport import TransportError

ERROR_TYPE = pa.struct([
    pa.field("code", pa.string()),
    pa.field("field", pa.string()),
    pa.field("message", pa.string()),
])

SCHEMA = pa.schema([
    pa.field("source_system", pa.string()),
    pa.field("entity", pa.string()),
    pa.field("ingestion_run_id", pa.string()),
    pa.field("processing_run_id", pa.string()),
    pa.field("batch_id", pa.string()),
    pa.field("source_file", pa.string()),
    pa.field("record_number", pa.int64()),
    pa.field("business_key_json", pa.string()),
    pa.field("reference_content_json", pa.string()),
    pa.field("raw_record", pa.string()),
    pa.field("status", pa.string()),
    pa.field("errors", pa.list_(ERROR_TYPE)),
    pa.field("evaluated_at", pa.timestamp("us", tz="UTC")),
])


def write_quarantine(output, result, processing_id, ingestion_id, evaluated):
    files = []
    for entity, summary in result["entities"].items():
        rejected = [
            record for record in summary["records"]
            if record["status"] in {"rejected", "conflict"}
        ]
        if not rejected:
            continue

        rows = [{
            "source_system": "synthetic",
            "entity": entity,
            "ingestion_run_id": ingestion_id,
            "processing_run_id": processing_id,
            "batch_id": result["batch_id"],
            "source_file": record["source_file"],
            "record_number": record["record_number"],
            "business_key_json": json.dumps(
                record["business_key"], sort_keys=True,
            ),
            "reference_content_json": record.get("reference_content_json"),
            "raw_record": record["raw_record"],
            "status": record["status"],
            "errors": record["errors"],
            "evaluated_at": evaluated,
        } for record in rejected]

        path = output / f"{entity}_quarantine.parquet"
        pq.write_table(
            pa.Table.from_pylist(rows, schema=SCHEMA),
            path, compression="snappy",
        )
        files.append({
            "path": path.name,
            "row_count": len(rows),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ingestion-run-id")
    args = parser.parse_args()

    if args.ingestion_run_id:
        try:
            UUID(args.ingestion_run_id)
        except ValueError:
            parser.error("--ingestion-run-id debe ser un UUID válido.")

    output = args.output_dir.resolve()
    source = args.batch_dir.resolve()
    if output.exists():
        parser.error("La salida ya existe; no se sobrescribirá.")
    if output.is_relative_to(source):
        parser.error("La salida debe estar fuera del lote.")

    processing_id = str(uuid4())
    evaluated = datetime.now(timezone.utc)
    report = {
        "schema_version": 1,
        "source_system": "synthetic",
        "input_directory": str(source),
        "ingestion_run_id": args.ingestion_run_id,
        "processing_run_id": processing_id,
        "evaluated_at": evaluated.isoformat(),
        "scope": "orders_csv_with_initial_reference",
        "status": "blocked",
        "records_processed": None,
        "errors": [],
        "quarantine_files": [],
    }

    reference = load_initial_reference()
    try:
        result = evaluate_new_orders(source, reference)
    except TransportError as error:
        result = None
        report["errors"].append({
            "code": error.code,
            "filename": error.filename,
            "message": str(error),
        })
    except ValueError as error:
        # Las entradas sin pedidos CSV quedan fuera de este evaluador.
        raise SystemExit(f"ALCANCE NO EVALUADO: {error}")

    output.mkdir(parents=True, exist_ok=False)

    if result is not None:
        summaries = {}
        for entity, summary in result["entities"].items():
            if summary["read"] != sum(
                summary[key] for key in ("accepted", "rejected", "conflict", "duplicate")
            ):
                raise RuntimeError(f"Reconciliación incorrecta: {entity}")
            summaries[entity] = {
                key: summary[key]
                for key in ("read", "accepted", "rejected", "conflict", "duplicate")
            }

        report.update({
            "batch_id": result["batch_id"],
            "status": "completed_for_scope",
            "entities": summaries,
            "records_processed": sum(
                summary["read"] for summary in summaries.values()
            ),
            "events_evaluated": False,
            "event_count_not_evaluated": result["event_count_not_evaluated"],
            "reconciliation": "passed",
        })
        report["quarantine_files"] = write_quarantine(
            output, result, processing_id, args.ingestion_run_id, evaluated,
        )

    with (output / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    print(f"RESULTADO: {report['status']}")
    for entity, summary in report.get("entities", {}).items():
        print(f"{entity}: {summary}")
    print(f"ARCHIVOS DE CUARENTENA: {len(report['quarantine_files'])}")
    print(f"INFORME: {output / 'report.json'}")
    print("ALCANCE: pedidos CSV contra referencia inicial; no publica en Azure ni modifica Silver.")
    return 1 if result is None else 0


if __name__ == "__main__":
    raise SystemExit(main())
