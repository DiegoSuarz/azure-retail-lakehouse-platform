"""Evalúa eventos contra una referencia fija y conserva sus resultados."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from check_new_orders import SCHEMA
from event_reference import KEYS, initial_context, after_batch_001_context
from event_rules import canonical, evaluate_event
from record_rules import issue
from validate_batch_transport import validate_transport, TransportError

EVENT_SCHEMA = SCHEMA.append(pa.field("event_id", pa.string()))
STATUSES = ("accepted", "rejected", "conflict", "pending", "duplicate")


def evaluate_file(path, metadata, context):
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
        raise TransportError("DQ002", "Archivo cambió durante la evaluación", path.name)

    records = []
    id_groups = defaultdict(list)
    sequence_groups = defaultdict(list)

    for number, line in enumerate(payload.decode("utf-8").splitlines(keepends=True), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        result = evaluate_event(event, context)
        record = {
            **result, "source_file": str(path), "record_number": number,
            "raw_record": line, "_event": event,
        }
        index = len(records)
        records.append(record)

        identifier = result["event_id"]
        try:
            UUID(identifier)
        except (ValueError, TypeError, AttributeError):
            continue
        id_groups[identifier].append(index)

        entity = result["entity"]
        key = result["business_key"]
        sequence = event.get("event_sequence")
        if (
            entity in ("customers", "products", "orders")
            and isinstance(key, dict)
            and type(sequence) is int and sequence > 0
        ):
            sequence_groups[(entity, key[KEYS[entity]], sequence)].append(index)

    for groups, field in ((id_groups, "event_id"), (sequence_groups, "event_sequence")):
        for indexes in groups.values():
            contents = (
                {canonical(records[index]["_event"]) for index in indexes}
                if field == "event_id"
                else {records[index]["event_id"] for index in indexes}
            )
            if len(contents) <= 1:
                continue
            for index in indexes:
                record = records[index]
                other = next(
                    candidate for candidate in indexes
                    if (
                        canonical(records[candidate]["_event"]) != canonical(record["_event"])
                        if field == "event_id"
                        else records[candidate]["event_id"] != record["event_id"]
                    )
                )
                record["status"] = "conflict"
                record["reference_content_json"] = canonical(records[other]["_event"])
                issue(
                    record["errors"], "DQ011", field,
                    "Identidad contradictoria dentro del mismo lote",
                )

    seen_accepted = set()
    for record in records:
        content = canonical(record.pop("_event"))
        if record["status"] == "accepted":
            if content in seen_accepted:
                record["status"] = "duplicate"
            else:
                seen_accepted.add(content)
    return records


def write_outputs(output, records, report, evaluated):
    for filename, statuses, report_key in (
        ("events_quarantine.parquet", {"rejected", "conflict"}, "quarantine_files"),
        ("events_pending.parquet", {"pending"}, "pending_files"),
    ):
        selected = [record for record in records if record["status"] in statuses]
        if not selected:
            continue

        rows = [{
            "source_system": "synthetic",
            "entity": record["entity"],
            "ingestion_run_id": report["ingestion_run_id"],
            "processing_run_id": report["processing_run_id"],
            "batch_id": report["batch_id"],
            "source_file": record["source_file"],
            "record_number": record["record_number"],
            "business_key_json": json.dumps(record["business_key"], sort_keys=True),
            "reference_content_json": record["reference_content_json"],
            "raw_record": record["raw_record"],
            "status": record["status"],
            "errors": record["errors"],
            "evaluated_at": evaluated,
            "event_id": record["event_id"],
        } for record in selected]

        path = output / filename
        pq.write_table(
            pa.Table.from_pylist(rows, schema=EVENT_SCHEMA),
            path, compression="snappy",
        )
        report[report_key].append({
            "path": filename,
            "row_count": len(rows),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline", choices=("initial", "after_batch_001"), required=True)
    parser.add_argument("--ingestion-run-id")
    args = parser.parse_args()

    if args.ingestion_run_id:
        try:
            UUID(args.ingestion_run_id)
        except ValueError:
            parser.error("ingestion_run_id debe ser un UUID válido.")

    source = args.batch_dir.resolve()
    output = args.output_dir.resolve()
    if output.exists() or output.is_relative_to(source):
        parser.error("La salida debe ser nueva y estar fuera del lote.")

    evaluated = datetime.now(timezone.utc)
    report = {
        "schema_version": 1,
        "processing_run_id": str(uuid4()),
        "ingestion_run_id": args.ingestion_run_id,
        "source_system": "synthetic",
        "input_directory": str(source),
        "baseline": args.baseline,
        "evaluated_at": evaluated.isoformat(),
        "scope": "events_against_fixed_reference",
        "state_modified": False,
        "status": "blocked",
        "records_processed": None,
        "errors": [],
        "quarantine_files": [],
        "pending_files": [],
    }

    records = None
    try:
        batch_id, counts = validate_transport(source)
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        if "changes.jsonl" not in manifest["files"]:
            parser.error("El lote no contiene eventos JSONL.")

        context = (
            initial_context() if args.baseline == "initial"
            else after_batch_001_context()
        )
        records = evaluate_file(
            source / "changes.jsonl", manifest["files"]["changes.jsonl"], context,
        )
        classifications = Counter(record["status"] for record in records)
        summary = {
            "read": len(records),
            **{status: classifications[status] for status in STATUSES},
        }
        if summary["read"] != sum(summary[status] for status in STATUSES):
            raise RuntimeError("Reconciliación de eventos incorrecta")
        if summary["read"] != counts["changes.jsonl"]:
            raise TransportError("DQ003", "Conteo cambió durante la evaluación", "changes.jsonl")

        report.update({
            "batch_id": batch_id,
            "status": "completed_for_scope",
            "records_processed": len(records),
            "events": summary,
            "csv_records_not_evaluated": sum(
                count for filename, count in counts.items() if filename.endswith(".csv")
            ),
            "reconciliation": "passed",
        })
    except TransportError as error:
        report["errors"].append({
            "code": error.code, "filename": error.filename, "message": str(error),
        })

    output.mkdir(parents=True, exist_ok=False)
    if records is not None and report["status"] == "completed_for_scope":
        write_outputs(output, records, report, evaluated)

    with (output / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    print(f"RESULTADO: {report['status']}")
    print(f"EVENTOS: {report.get('events')}")
    print(f"INFORME: {output / 'report.json'}")
    print("ALCANCE: evaluación local; no aplica eventos ni publica en Azure.")
    return 0 if report["status"] == "completed_for_scope" else 1


if __name__ == "__main__":
    raise SystemExit(main())
