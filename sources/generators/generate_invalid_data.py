"""Genera casos inválidos aislados para los escenarios S13–S20."""

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from generate_initial_data import CUTOFF, money, timestamp, write_csv
from generate_incremental_data import make_event, read_initial, write_json


def read_csv(path):
    import csv

    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_case(root, scenario, baseline, reason, orders=None, items=None,
               events=None, corrupt_hash=False):
    directory = root / "invalid" / scenario
    directory.mkdir(parents=True)
    files = {}

    for filename, rows in (
        ("orders.csv", orders),
        ("order_items.csv", items),
    ):
        if rows is not None:
            files[filename] = {
                "row_count": len(rows),
                "sha256": write_csv(directory / filename, rows),
            }

    if events is not None:
        path = directory / "changes.jsonl"
        path.write_text(
            "".join(
                json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
                for event in events
            ),
            encoding="utf-8",
        )
        files["changes.jsonl"] = {
            "row_count": len(events),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    if corrupt_hash:
        files["changes.jsonl"]["sha256"] = "0" * 64

    write_json(directory / "manifest.json", {
        "schema_version": 1,
        "batch_id": f"invalid_{scenario.lower()}",
        "created_at": timestamp(CUTOFF + timedelta(days=1)),
        "files": files,
    })
    return {
        "scenario": scenario,
        "directory": f"invalid/{scenario}",
        "baseline": baseline,
        "expected_outcome": reason,
        "must_not_change_accepted_state": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-dir", type=Path, default=Path("data/initial"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/incremental")
    )
    args = parser.parse_args()
    root = args.output_dir
    if (root / "invalid").exists() or (root / "invalid-expectations.json").exists():
        parser.error("Ya existe una salida de casos inválidos.")

    datasets, _ = read_initial(args.initial_dir)
    first = root / "functional" / "batch_001"
    manifest = json.loads(
        (first / "manifest.json").read_text(encoding="utf-8")
    )
    for filename, metadata in manifest["files"].items():
        payload = (first / filename).read_bytes()
        if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
            parser.error(f"Archivo funcional modificado: {filename}")

    events = [
        json.loads(line)
        for line in (first / "changes.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    customer_event = next(event for event in events if event["entity"] == "customers")
    new_orders = read_csv(first / "orders.csv")
    new_items = read_csv(first / "order_items.csv")
    cases = []

    conflicting = deepcopy(customer_event)
    conflicting["after"]["first_name"] += "_conflict"
    cases.append(write_case(
        root, "S13", "after_batch_001", "event_id_conflict",
        events=[conflicting],
    ))

    conflicting = deepcopy(customer_event)
    conflicting["event_id"] = str(uuid5(NAMESPACE_URL, "arlp/v1/invalid/S14"))
    cases.append(write_case(
        root, "S14", "after_batch_001", "entity_key_sequence_conflict",
        events=[conflicting],
    ))

    cancelled = min(
        (row for row in datasets["orders"] if row["status"] == "cancelled"),
        key=lambda row: row["order_id"],
    )
    cases.append(write_case(
        root, "S15", "initial", "invalid_status_transition",
        events=[make_event(
            "S15", "orders", cancelled, {"status": "confirmed"}, 10
        )],
    ))

    bad_items = deepcopy(new_items)
    bad_items[0]["product_id"] = max(
        row["product_id"] for row in datasets["products"]
    ) + 1
    cases.append(write_case(
        root, "S16", "initial", "missing_product_reference",
        orders=deepcopy(new_orders), items=bad_items,
    ))

    from decimal import Decimal

    bad_items = deepcopy(new_items)
    bad_items[0]["discount_amount"] = money(
        int(bad_items[0]["quantity"]) * Decimal(bad_items[0]["unit_price"]) + 1
    )
    cases.append(write_case(
        root, "S17", "initial", "discount_exceeds_gross",
        orders=deepcopy(new_orders), items=bad_items,
    ))

    cases.append(write_case(
        root, "S18", "initial", "manifest_hash_mismatch",
        events=[deepcopy(customer_event)], corrupt_hash=True,
    ))

    pending = min(
        (row for row in datasets["orders"] if row["status"] == "pending"),
        key=lambda row: row["order_id"],
    )
    repeated = deepcopy(pending)
    repeated["status"] = "confirmed"
    repeated["updated_at"] = timestamp(CUTOFF + timedelta(hours=10))
    old_items = [
        deepcopy(row) for row in datasets["order_items"]
        if row["order_id"] == pending["order_id"]
    ]
    cases.append(write_case(
        root, "S19", "initial", "existing_order_content_conflict",
        orders=[repeated], items=old_items,
    ))

    other_customer = next(
        row["customer_id"] for row in datasets["customers"]
        if row["customer_id"] != pending["customer_id"]
    )
    cases.append(write_case(
        root, "S20", "initial", "stable_attribute_changed",
        events=[make_event(
            "S20", "orders", pending,
            {"status": "confirmed", "customer_id": other_customer}, 10,
        )],
    ))

    write_json(root / "invalid-expectations.json", {
        "schema_version": 1,
        "cases": cases,
        "processing_verified": False,
    })
    for case in cases:
        print(f"GENERADO: {case['scenario']} — {case['expected_outcome']}")


if __name__ == "__main__":
    main()
