"""Construye referencias explícitas para probar la calidad de eventos."""

import csv
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path

from new_order_rules import evaluate_new_orders
from reference_data import ROOT, load_initial_reference
from validate_batch_transport import validate_transport

KEYS = {
    "categories": "category_id",
    "products": "product_id",
    "customers": "customer_id",
    "orders": "order_id",
}
INTEGER_FIELDS = {
    "category_id", "product_id", "customer_id",
    "order_id", "line_number", "quantity",
}


def normalized_row(row):
    result = {}
    for field, value in row.items():
        if field in INTEGER_FIELDS:
            result[field] = int(value)
        elif field == "is_active":
            if value not in {"0", "1"}:
                raise RuntimeError("Referencia con is_active inválido")
            result[field] = value == "1"
        else:
            result[field] = value
    return result


def initial_context():
    datasets = load_initial_reference()
    records = {}
    for entity, key in KEYS.items():
        records[entity] = {}
        for row in datasets[entity]:
            normalized = normalized_row(row)
            identifier = normalized[key]
            if identifier in records[entity]:
                raise RuntimeError(f"Clave repetida en referencia: {entity}")
            records[entity][identifier] = normalized

    return {
        "baseline": "initial",
        "records": records,
        "event_history": {},
        "sequence_history": {},
        "last_sequence": {},
    }


def verified_payload(directory, filename, metadata):
    payload = (directory / filename).read_bytes()
    if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
        raise RuntimeError(f"Referencia modificada: {filename}")
    return payload


def after_batch_001_context():
    context = initial_context()
    directory = ROOT / "data/incremental/functional/batch_001"
    validate_transport(directory)
    manifest = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    expectations = json.loads(
        (ROOT / "data/incremental/expectations.json").read_text(encoding="utf-8")
    )
    initial_manifest = json.loads(
        (ROOT / "data/initial/manifest.json").read_text(encoding="utf-8")
    )
    if expectations["baseline_files"] != initial_manifest["files"]:
        raise RuntimeError("Las expectativas corresponden a otra referencia")

    evaluation = evaluate_new_orders(directory, load_initial_reference())
    for summary in evaluation["entities"].values():
        if summary["accepted"] != summary["read"]:
            raise RuntimeError("Los pedidos del lote de referencia no son válidos")

    payload = verified_payload(
        directory, "orders.csv", manifest["files"]["orders.csv"],
    )
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""))
    for row in reader:
        record = normalized_row(row)
        identifier = record["order_id"]
        if identifier in context["records"]["orders"]:
            raise RuntimeError("Pedido nuevo colisiona con referencia inicial")
        context["records"]["orders"][identifier] = record

    payload = verified_payload(
        directory, "changes.jsonl", manifest["files"]["changes.jsonl"],
    )
    events = [
        json.loads(line) for line in payload.decode("utf-8").splitlines()
        if line.strip()
    ]
    expected_records = {}
    for entry in expectations["expected_final_records"]:
        entity = entry["entity"]
        identifier = entry["business_key"][KEYS[entity]]
        key = (entity, identifier)
        if key in expected_records:
            raise RuntimeError("Expectativa de estado final repetida")
        expected_records[key] = entry["after"]

    observed = set()
    for event in events:
        entity = event["entity"]
        identifier = event["business_key"][KEYS[entity]]
        key = (entity, identifier)
        sequence_key = (*key, event["event_sequence"])

        if key in observed or event["event_sequence"] != 1:
            raise RuntimeError("Lote de referencia incompatible con esta fixture")
        if event["event_id"] in context["event_history"]:
            raise RuntimeError("Evento repetido en referencia")
        if event["after"] != expected_records.get(key):
            raise RuntimeError("Evento no coincide con la expectativa de M2")
        if identifier not in context["records"][entity]:
            raise RuntimeError("Registro ausente en referencia")

        context["records"][entity][identifier] = deepcopy(expected_records[key])
        context["event_history"][event["event_id"]] = deepcopy(event)
        context["sequence_history"][sequence_key] = event["event_id"]
        context["last_sequence"][key] = 1
        observed.add(key)

    if observed != set(expected_records):
        raise RuntimeError("Expectativas de estado final incompletas")
    if len(events) != expectations["unique_event_count"]:
        raise RuntimeError("Cantidad de eventos diferente de las expectativas")

    context["baseline"] = "after_batch_001"
    return context
