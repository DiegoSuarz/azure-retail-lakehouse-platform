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
    existing_ids = {int(row["order_id"]) for row in reference["orders"]}

    # Esta etapa no debe aceptar claves existentes sin compararlas.
    reused = {
        record["_values"]["order_id"] for record in orders
        if record["_values"]["order_id"] in existing_ids
    }
    if reused:
        raise ValueError(
            "Comparación con pedidos existentes pendiente para las claves: "
            + ", ".join(map(str, sorted(reused)))
        )

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
            record["status"] = "rejected" if record["errors"] else "accepted"

        accepted = sum(record["status"] == "accepted" for record in records)
        result[entity] = {
            "read": len(records),
            "accepted": accepted,
            "rejected": len(records) - accepted,
            "records": records,
        }

    return {
        "batch_id": batch_id,
        "scope": "new_orders_only",
        "events_evaluated": False,
        "event_count_not_evaluated": counts.get("changes.jsonl", 0),
        "entities": result,
    }
