"""Evalúa pedidos nuevos y propaga rechazos a sus líneas."""

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from record_rules import (
    parse_order, parse_item, check_customer, check_product,
    check_item_parent, issue,
)
from validate_batch_transport import validate_transport, TransportError


def read_records(directory, filename, metadata, parser, entity):
    path = directory / filename
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
        raise TransportError("DQ002", "Archivo cambió después de validarse", filename)

    text = payload.decode("utf-8")
    physical_lines = text.splitlines(keepends=True)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    header = next(reader)
    records = []

    start = reader.line_num
    for number, fields in enumerate(reader, 1):
        row = dict(zip(header, fields))
        values, errors = parser(row)
        records.append({
            "entity": entity,
            "source_file": str(path),
            "record_number": number,
            "raw_record": "".join(physical_lines[start:reader.line_num]),
            "errors": errors,
            "_values": values,
        })
        start = reader.line_num
    return records


def evaluate_new_orders(directory, reference):
    directory = Path(directory)
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    batch_id, counts = validate_transport(directory)

    if (directory / "manifest.json").read_bytes() != manifest_bytes:
        raise TransportError("DQ002", "Manifiesto cambió durante la validación")

    if "orders.csv" not in manifest["files"]:
        raise ValueError("Este evaluador requiere pedidos y líneas CSV.")

    orders = read_records(
        directory, "orders.csv", manifest["files"]["orders.csv"],
        parse_order, "orders",
    )
    items = read_records(
        directory, "order_items.csv", manifest["files"]["order_items.csv"],
        parse_item, "order_items",
    )
    customer_ids = {int(row["customer_id"]) for row in reference["customers"]}
    product_ids = {int(row["product_id"]) for row in reference["products"]}
    existing_orders = {
        int(row["order_id"]): row for row in reference["orders"]
    }
    existing_items = {}
    for row in reference["order_items"]:
        existing_items.setdefault(int(row["order_id"]), []).append(row)

    order_counts = Counter(
        record["_values"]["order_id"] for record in orders
        if record["_values"]["order_id"] is not None
    )
    item_counts = Counter(
        (record["_values"]["order_id"], record["_values"]["line_number"])
        for record in items
        if record["_values"]["order_id"] is not None
        and record["_values"]["line_number"] is not None
    )

    parents = {}
    for record in orders:
        values = record["_values"]
        check_customer(values, customer_ids, record["errors"])
        identifier = values["order_id"]
        if identifier is not None:
            if order_counts[identifier] > 1:
                issue(record["errors"], "DQ006", "order_id", "Clave repetida dentro del lote")
            elif identifier > 0:
                parents[identifier] = record

    grouped_items = {}
    for record in items:
        values = record["_values"]
        errors = record["errors"]
        identifier = values["order_id"]
        key = (identifier, values["line_number"])
        if None not in key and item_counts[key] > 1:
            issue(errors, "DQ006", "line_number", "Clave de línea repetida dentro del lote")
        check_product(values, product_ids, errors)
        parent = parents.get(identifier)
        check_item_parent(
            values, parent["_values"] if parent is not None else None, errors,
        )
        if identifier is not None and identifier > 0:
            grouped_items.setdefault(identifier, []).append(record)

    # Compara el pedido completo contra la referencia inicial.
    for record in orders:
        identifier = record["_values"]["order_id"]
        if identifier not in existing_orders or order_counts[identifier] != 1:
            continue

        original = existing_orders[identifier]
        original_lines = existing_items.get(identifier, [])
        lines = grouped_items.get(identifier, [])
        baseline_order = parse_order(original)[0]
        baseline_lines = {
            int(row["line_number"]): parse_item(row)[0]
            for row in original_lines
        }
        incoming_lines = {
            line["_values"]["line_number"]: line["_values"]
            for line in lines
        }
        same_content = (
            record["_values"] == baseline_order
            and len(lines) == len(incoming_lines)
            and incoming_lines == baseline_lines
        )

        cutoff_message = "Pedido nuevo anterior al corte"
        other_errors = [
            error for error in record["errors"]
            if not (
                error["code"] == "DQ009"
                and error["field"] == "created_at"
                and error["message"] == cutoff_message
            )
        ]

        record["reference_content_json"] = json.dumps({
            "order": original,
            "order_items": original_lines,
        }, ensure_ascii=False, sort_keys=True)

        if same_content and not other_errors and not any(line["errors"] for line in lines):
            # Una repetición completa no se interpreta como una inserción nueva.
            record["errors"] = []
            record["_classification"] = "duplicate"
            for line in lines:
                line["_classification"] = "duplicate"
        else:
            record["_classification"] = "conflict"
            issue(
                record["errors"], "DQ006", "order_id",
                "Pedido existente con contenido diferente o entrega incompatible",
            )
            for line in lines:
                line["reference_content_json"] = record["reference_content_json"]

    for record in orders:
        identifier = record["_values"]["order_id"]
        lines = grouped_items.get(identifier, []) if identifier is not None else []
        if not lines:
            issue(
                record["errors"], "DQ010", "order_id",
                "Pedido sin líneas incluidas en el lote",
            )
        elif any(line["errors"] for line in lines):
            issue(
                record["errors"], "DQ010", "order_id",
                "Pedido excluido por errores en sus líneas",
            )

    # Una cabecera inválida impide aceptar cualquiera de sus líneas.
    bad_order_ids = {
        record["_values"]["order_id"] for record in orders
        if record["errors"] and record["_values"]["order_id"] is not None
    }
    for record in items:
        if record["_values"]["order_id"] in bad_order_ids:
            issue(
                record["errors"], "DQ010", "order_id",
                "Línea excluida porque el pedido completo no es aceptable",
            )

    result = {}
    for entity, records in (("orders", orders), ("order_items", items)):
        for record in records:
            values = record.pop("_values")
            record["business_key"] = {"order_id": values["order_id"]}
            if entity == "order_items":
                record["business_key"]["line_number"] = values["line_number"]
            record["status"] = record.pop(
                "_classification", "rejected" if record["errors"] else "accepted",
            )

        classifications = Counter(record["status"] for record in records)
        result[entity] = {
            "read": len(records),
            **{
                status: classifications[status]
                for status in ("accepted", "rejected", "conflict", "duplicate")
            },
            "records": records,
        }

    return {
        "batch_id": batch_id,
        "scope": "orders_csv_with_initial_reference",
        "events_evaluated": False,
        "event_count_not_evaluated": counts.get("changes.jsonl", 0),
        "entities": result,
    }
