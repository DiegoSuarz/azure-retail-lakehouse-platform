"""Valida el primer lote funcional y sus expectativas."""

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

INITIAL = Path("data/initial")
OUTPUT = Path("data/incremental")
BATCH = OUTPUT / "functional" / "batch_001"


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def controls(orders, items):
    confirmed = {
        key for key, row in orders.items() if row["status"] == "confirmed"
    }
    net = Decimal("0")
    quantity = 0
    for row in items:
        if int(row["order_id"]) in confirmed:
            units = int(row["quantity"])
            net += (
                units * Decimal(row["unit_price"])
                - Decimal(row["discount_amount"])
            )
            quantity += units
    return net, quantity, len(confirmed)


def main():
    expectations = json.loads(
        (OUTPUT / "expectations.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (BATCH / "manifest.json").read_text(encoding="utf-8")
    )
    cutoff = date("2026-10-01T00:00:00.000Z")

    for filename, metadata in expectations["baseline_files"].items():
        payload = (INITIAL / filename).read_bytes()
        require(
            hashlib.sha256(payload).hexdigest() == metadata["sha256"],
            f"Conjunto inicial modificado: {filename}",
        )

    require(manifest["schema_version"] == 1, "Versión del manifiesto")
    require(manifest["batch_id"] == "batch_001", "Identidad del lote")
    require(
        set(manifest["files"]) == {
            "orders.csv", "order_items.csv", "changes.jsonl"
        },
        "Archivos del lote",
    )

    new_orders = read_csv(BATCH / "orders.csv")
    new_items = read_csv(BATCH / "order_items.csv")
    events = [
        json.loads(line)
        for line in (BATCH / "changes.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    received = {
        "orders.csv": new_orders,
        "order_items.csv": new_items,
        "changes.jsonl": events,
    }
    for filename, rows in received.items():
        metadata = manifest["files"][filename]
        require(len(rows) == metadata["row_count"], f"Conteo: {filename}")
        require(
            hashlib.sha256((BATCH / filename).read_bytes()).hexdigest()
            == metadata["sha256"],
            f"Hash: {filename}",
        )

    customers = {
        int(row["customer_id"]): row
        for row in read_csv(INITIAL / "customers.csv")
    }
    products = {
        int(row["product_id"]): row
        for row in read_csv(INITIAL / "products.csv")
    }
    orders = {
        int(row["order_id"]): row
        for row in read_csv(INITIAL / "orders.csv")
    }
    initial_items = read_csv(INITIAL / "order_items.csv")
    before_net, before_quantity, before_count = controls(orders, initial_items)

    new_ids = [int(row["order_id"]) for row in new_orders]
    require(len(new_ids) == len(set(new_ids)), "Pedidos nuevos duplicados")
    require(set(new_ids).isdisjoint(orders), "Colisión con pedidos iniciales")

    for row in new_orders:
        require(int(row["customer_id"]) in customers, "Cliente inexistente")
        require(row["currency_code"] == "PEN", "Moneda inválida")
        require(
            row["status"] in {"pending", "confirmed", "cancelled"},
            "Estado inválido",
        )
        require(
            cutoff <= date(row["created_at"]) <= date(row["updated_at"]),
            "Fechas del pedido",
        )
        orders[int(row["order_id"])] = row

    line_keys = set()
    line_counts = Counter()
    for row in new_items:
        key = (int(row["order_id"]), int(row["line_number"]))
        require(key not in line_keys, "Línea duplicada")
        require(key[0] in new_ids and key[1] > 0, "Clave de línea inválida")
        require(int(row["product_id"]) in products, "Producto inexistente")
        quantity = int(row["quantity"])
        price = Decimal(row["unit_price"])
        discount = Decimal(row["discount_amount"])
        require(quantity > 0 and price > 0, "Cantidad o precio inválido")
        require(0 <= discount <= quantity * price, "Descuento inválido")
        require(
            date(orders[key[0]]["created_at"])
            <= date(row["created_at"])
            <= date(row["updated_at"]),
            "Fechas de línea",
        )
        line_keys.add(key)
        line_counts[key[0]] += 1
    require(set(line_counts) == set(new_ids), "Pedido nuevo sin líneas")

    entities = {"customers": customers, "products": products, "orders": orders}
    key_fields = {
        "customers": "customer_id",
        "products": "product_id",
        "orders": "order_id",
    }
    mutable = {
        "customers": {
            "first_name", "last_name", "email", "city", "region", "is_active"
        },
        "products": {
            "category_id", "product_name", "brand", "list_price", "is_active"
        },
        "orders": {"status"},
    }
    transitions = {
        ("pending", "confirmed"),
        ("pending", "cancelled"),
        ("confirmed", "cancelled"),
    }
    event_ids = set()
    sequences = {}
    final_records = []

    for event in events:
        require(event["schema_version"] == 1, "Versión de evento")
        require(event["operation"] == "update", "Operación de evento")
        UUID(event["event_id"])
        require(event["event_id"] not in event_ids, "Evento duplicado")
        event_ids.add(event["event_id"])

        entity = event["entity"]
        require(entity in entities, "Entidad inválida")
        field = key_fields[entity]
        require(set(event["business_key"]) == {field}, "Clave de evento")
        key = event["business_key"][field]
        require(type(key) is int and key in entities[entity], "Registro ausente")

        original = entities[entity][key]
        after = event["after"]
        require(set(after) == set(original), "Imagen incompleta")
        require(after[field] == key, "Clave de imagen diferente")

        sequence_key = (entity, key)
        sequence = event["event_sequence"]
        require(
            type(sequence) is int
            and sequence == sequences.get(sequence_key, 0) + 1,
            "Secuencia inválida",
        )
        event_time = date(event["event_time"])
        require(event_time >= cutoff, "Evento anterior al corte")
        require(event_time > date(original["updated_at"]), "Fecha de evento")
        require(after["updated_at"] == event["event_time"], "updated_at")

        for column in original:
            if column in mutable[entity] or column == "updated_at":
                continue
            require(
                str(after[column]) == str(original[column]),
                f"Atributo estable modificado: {entity}.{column}",
            )

        if entity == "orders":
            require(
                (original["status"], after["status"]) in transitions,
                "Transición inválida",
            )
        else:
            require(type(after["is_active"]) is bool, "is_active no booleano")
            if entity == "products":
                require(Decimal(after["list_price"]) > 0, "Precio de catálogo")

        entities[entity][key] = after
        sequences[sequence_key] = sequence
        final_records.append({
            "entity": entity,
            "business_key": event["business_key"],
            "after": after,
        })

    all_items = initial_items + new_items
    final_net, final_quantity, final_count = controls(orders, all_items)
    actual = {
        "order_count": len(orders),
        "line_count": len(all_items),
        "confirmed_order_count": final_count,
        "confirmed_net_delta": format(final_net - before_net, ".2f"),
        "confirmed_quantity_delta": final_quantity - before_quantity,
        "confirmed_net_amount": format(final_net, ".2f"),
        "confirmed_quantity": final_quantity,
    }
    require(actual == expectations["expected_controls"], "Totales esperados")
    require(
        final_records == expectations["expected_final_records"],
        "Estados finales esperados",
    )
    require(new_ids == expectations["new_order_ids"], "Identidades esperadas")
    require(len(new_orders) == expectations["new_order_count"], "Pedidos esperados")
    require(len(new_items) == expectations["new_line_count"], "Líneas esperadas")
    require(len(event_ids) == expectations["unique_event_count"], "Eventos esperados")
    require(
        expectations["covered_scenarios"]
        == [f"S{number:02d}" for number in range(1, 8)],
        "Cobertura declarada",
    )

    print("PASS: hashes y conteos del lote.")
    print("PASS: claves, relaciones y reglas de los pedidos nuevos.")
    print("PASS: imágenes, secuencias y transiciones de los seis eventos.")
    print("PASS: estados finales e importes reconciliados independientemente.")
    print("ALCANCE: primer lote funcional S01–S07; sin cambios en SQL Server.")


if __name__ == "__main__":
    main()
