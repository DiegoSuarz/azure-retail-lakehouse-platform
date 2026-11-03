"""Genera lotes incrementales reproducibles a partir del conjunto inicial."""

import argparse
import csv
import hashlib
import json
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from generate_initial_data import CUTOFF, money, timestamp, write_csv

TABLES = ("categories", "products", "customers", "orders", "order_items")
INTEGER_FIELDS = {
    "category_id", "product_id", "customer_id", "order_id",
    "line_number", "quantity",
}


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_initial(directory):
    expected_files = {f"{table}.csv" for table in TABLES}
    if {path.name for path in directory.glob("*.csv")} != expected_files:
        raise ValueError("Conjunto inicial CSV incompatible.")
    files = {}

    datasets = {}
    for table in TABLES:
        filename = f"{table}.csv"
        path = directory / filename
        payload = path.read_bytes()
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
        if not reader.fieldnames or not rows:
            raise ValueError(f"Archivo inicial vacío: {filename}")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Cabecera inicial duplicada: {filename}")
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError(f"Estructura inicial incorrecta: {filename}")
        files[filename] = {
            "row_count": len(rows),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

        for row in rows:
            for field in INTEGER_FIELDS.intersection(row):
                row[field] = int(row[field])
            if "is_active" in row:
                if row["is_active"] not in {"0", "1"}:
                    raise ValueError("is_active inicial inválido.")
                row["is_active"] = row["is_active"] == "1"

        datasets[table] = rows

    status_counts = {}
    for order in datasets["orders"]:
        status = order["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    confirmed_ids = {
        row["order_id"] for row in datasets["orders"]
        if row["status"] == "confirmed"
    }
    confirmed_net = Decimal("0")
    confirmed_quantity = 0
    for row in datasets["order_items"]:
        if row["order_id"] in confirmed_ids:
            confirmed_net += (
                row["quantity"] * Decimal(row["unit_price"])
                - Decimal(row["discount_amount"])
            )
            confirmed_quantity += row["quantity"]

    return datasets, {
        "files": files,
        "controls": {
            "order_status_counts": status_counts,
            "net_amount_confirmed_orders": money(confirmed_net),
            "quantity_confirmed_orders": confirmed_quantity,
        },
    }


def make_event(scenario, entity, original, changes, hour, sequence=1):
    key_field = {
        "customers": "customer_id",
        "products": "product_id",
        "orders": "order_id",
    }[entity]
    event_time = timestamp(CUTOFF + timedelta(hours=hour))
    after = deepcopy(original)
    after.update(changes)
    after["updated_at"] = event_time

    identity = f"arlp/v1/{scenario}/{entity}/{original[key_field]}/{sequence}"
    return {
        "schema_version": 1,
        "event_id": str(uuid5(NAMESPACE_URL, identity)),
        "entity": entity,
        "operation": "update",
        "event_time": event_time,
        "event_sequence": sequence,
        "business_key": {key_field: original[key_field]},
        "after": after,
    }


def order_measures(items, order_id):
    lines = [row for row in items if row["order_id"] == order_id]
    net = sum(
        (
            row["quantity"] * Decimal(row["unit_price"])
            - Decimal(row["discount_amount"])
            for row in lines
        ),
        Decimal("0"),
    )
    return net, sum(row["quantity"] for row in lines)


def build_functional(datasets, initial_reference):
    customer = min(datasets["customers"], key=lambda row: row["customer_id"])
    products = sorted(datasets["products"], key=lambda row: row["product_id"])
    product, inactive_product = products[:2]

    def select_order(status):
        candidates = [
            row for row in datasets["orders"] if row["status"] == status
        ]
        if not candidates:
            raise ValueError(f"No existen pedidos iniciales {status}.")
        return min(candidates, key=lambda row: row["order_id"])

    pending = select_order("pending")
    confirmed = select_order("confirmed")
    first_id = max(row["order_id"] for row in datasets["orders"]) + 1
    created = timestamp(CUTOFF + timedelta(hours=1))

    orders = []
    items = []
    for offset, status in enumerate(("confirmed", "pending")):
        order_id = first_id + offset
        orders.append({
            "order_id": order_id,
            "customer_id": customer["customer_id"],
            "order_date": created,
            "status": status,
            "currency_code": "PEN",
            "created_at": created,
            "updated_at": created,
        })
        items.append({
            "order_id": order_id,
            "line_number": 1,
            "product_id": product["product_id"],
            "quantity": offset + 1,
            "unit_price": product["list_price"],
            "discount_amount": "0.00",
            "created_at": created,
            "updated_at": created,
        })

    city, region = (
        ("Arequipa", "Arequipa")
        if customer["city"] == "Lima"
        else ("Lima", "Lima")
    )
    events = [
        make_event(
            "S02", "customers", customer,
            {"city": city, "region": region}, 2,
        ),
        make_event(
            "S03", "products", product,
            {"list_price": money(Decimal(product["list_price"]) + 100)}, 3,
        ),
        make_event("S04", "orders", pending, {"status": "confirmed"}, 4),
        make_event("S05", "orders", confirmed, {"status": "cancelled"}, 5),
        make_event(
            "S06", "products", inactive_product, {"is_active": False}, 6,
        ),
        make_event("S07", "orders", orders[1], {"status": "confirmed"}, 7),
    ]

    pending_net, pending_quantity = order_measures(
        datasets["order_items"], pending["order_id"]
    )
    cancelled_net, cancelled_quantity = order_measures(
        datasets["order_items"], confirmed["order_id"]
    )
    new_measures = [order_measures(items, row["order_id"]) for row in orders]
    new_net = sum((value[0] for value in new_measures), Decimal("0"))
    new_quantity = sum(value[1] for value in new_measures)
    net_delta = new_net + pending_net - cancelled_net
    quantity_delta = new_quantity + pending_quantity - cancelled_quantity
    controls = initial_reference["controls"]

    expectations = {
        "schema_version": 1,
        "covered_scenarios": ["S01", "S02", "S03", "S04", "S05", "S06", "S07"],
        "delivery_order": ["functional/batch_001"],
        "baseline_files": initial_reference["files"],
        "new_order_ids": [row["order_id"] for row in orders],
        "new_order_count": len(orders),
        "new_line_count": len(items),
        "unique_event_count": len(events),
        "expected_final_records": [
            {
                "entity": event["entity"],
                "business_key": event["business_key"],
                "after": event["after"],
            }
            for event in events
        ],
        "expected_controls": {
            "order_count": len(datasets["orders"]) + len(orders),
            "line_count": len(datasets["order_items"]) + len(items),
            "confirmed_order_count": (
                controls["order_status_counts"]["confirmed"] + 2
            ),
            "confirmed_net_delta": money(net_delta),
            "confirmed_quantity_delta": quantity_delta,
            "confirmed_net_amount": money(
                Decimal(controls["net_amount_confirmed_orders"]) + net_delta
            ),
            "confirmed_quantity": (
                controls["quantity_confirmed_orders"] + quantity_delta
            ),
        },
        "historical_unit_prices_must_remain_unchanged": True,
        "processing_verified": False,
    }
    return orders, items, events, expectations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-dir", type=Path, default=Path("data/initial"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/incremental")
    )
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("La carpeta de salida no está vacía. Usa otra ubicación.")

    datasets, initial_reference = read_initial(args.initial_dir)
    orders, items, events, expectations = build_functional(
        datasets, initial_reference
    )

    batch_dir = args.output_dir / "functional" / "batch_001"
    batch_dir.mkdir(parents=True, exist_ok=True)
    for filename, rows in (
        ("orders.csv", orders),
        ("order_items.csv", items),
    ):
        write_csv(batch_dir / filename, rows)

    event_path = batch_dir / "changes.jsonl"
    event_path.write_text(
        "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )

    write_json(args.output_dir / "expectations.json", expectations)

    print("GENERADO: functional/batch_001")
    print(f"Pedidos nuevos: {len(orders)}")
    print(f"Líneas nuevas: {len(items)}")
    print(f"Eventos únicos: {len(events)}")
    print(json.dumps(expectations["expected_controls"], indent=2))


if __name__ == "__main__":
    main()
