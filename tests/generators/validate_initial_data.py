"""Valida los archivos iniciales sin modificar los datos."""

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path("data/initial")


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
tables = {}

for filename, metadata in manifest["files"].items():
    path = ROOT / filename
    require(
        hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"],
        f"Hash de {filename}",
    )
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == metadata["row_count"], f"Conteo de {filename}")
    tables[path.stem] = rows

require(
    set(tables) == {"categories", "products", "customers", "orders", "order_items"},
    "Conjunto de archivos",
)

keys = {}
for name, key in [
    ("categories", "category_id"),
    ("products", "product_id"),
    ("customers", "customer_id"),
    ("orders", "order_id"),
]:
    values = [int(row[key]) for row in tables[name]]
    require(all(value > 0 for value in values), f"Claves positivas: {name}")
    require(len(values) == len(set(values)), f"Claves únicas: {name}")
    keys[name] = set(values)

for name, field in [
    ("categories", "category_name"),
    ("products", "sku"),
    ("customers", "email"),
]:
    values = [row[field].casefold() for row in tables[name]]
    require(all(values), f"Valores presentes: {name}.{field}")
    require(len(values) == len(set(values)), f"Unicidad: {name}.{field}")

cutoff = date(manifest["cutoff_exclusive"])
start = date(manifest["period_start_inclusive"])

for name, rows in tables.items():
    for row in rows:
        created = date(row["created_at"])
        updated = date(row["updated_at"])
        require(created <= updated < cutoff, f"Fechas: {name}")

for row in tables["products"]:
    require(int(row["category_id"]) in keys["categories"], "Categoría de producto")
    require(Decimal(row["list_price"]) > 0, "Precio de catálogo")
    require(row["is_active"] in {"0", "1"}, "Estado del producto")

for row in tables["customers"]:
    require(row["email"].endswith("@example.com"), "Correo sintético")
    require(row["is_active"] in {"0", "1"}, "Estado del cliente")

orders = {int(row["order_id"]): row for row in tables["orders"]}
for row in orders.values():
    require(int(row["customer_id"]) in keys["customers"], "Cliente de pedido")
    require(row["status"] in {"pending", "confirmed", "cancelled"}, "Estado de pedido")
    require(row["currency_code"] == "PEN", "Moneda")
    require(start <= date(row["order_date"]) < cutoff, "Período del pedido")

line_keys = set()
line_counts = Counter()
gross_total = Decimal("0")
discount_total = Decimal("0")
confirmed_net = Decimal("0")
confirmed_quantity = 0

for row in tables["order_items"]:
    order_id = int(row["order_id"])
    line_number = int(row["line_number"])
    key = (order_id, line_number)

    require(order_id in orders, "Pedido de línea")
    require(int(row["product_id"]) in keys["products"], "Producto de línea")
    require(line_number > 0 and key not in line_keys, "Clave de línea")
    line_keys.add(key)
    line_counts[order_id] += 1

    quantity = int(row["quantity"])
    price = Decimal(row["unit_price"])
    discount = Decimal(row["discount_amount"])
    require(quantity > 0 and price > 0, "Cantidad y precio")
    gross = quantity * price
    require(0 <= discount <= gross, "Descuento de línea")
    require(
        date(row["created_at"]) >= date(orders[order_id]["created_at"]),
        "Creación de línea posterior o igual a su pedido",
    )

    gross_total += gross
    discount_total += discount
    if orders[order_id]["status"] == "confirmed":
        confirmed_net += gross - discount
        confirmed_quantity += quantity

require(set(line_counts) == set(orders), "Todos los pedidos tienen líneas")
require(all(1 <= count <= 5 for count in line_counts.values()), "Líneas por pedido")

controls = manifest["controls"]
require(
    dict(Counter(row["status"] for row in orders.values()))
    == controls["order_status_counts"],
    "Conteos por estado",
)

for label, total in [
    ("gross_amount_all_orders", gross_total),
    ("discount_amount_all_orders", discount_total),
    ("net_amount_all_orders", gross_total - discount_total),
    ("net_amount_confirmed_orders", confirmed_net),
]:
    require(total == Decimal(controls[label]), f"Reconciliación: {label}")

require(
    confirmed_quantity == controls["quantity_confirmed_orders"],
    "Unidades confirmadas",
)

print("PASS: hashes y conteos de los cinco archivos.")
print("PASS: claves, relaciones, fechas y reglas comerciales.")
print("PASS: todos los pedidos tienen entre una y cinco líneas.")
print("PASS: estados, importes y unidades reconciliados con el manifiesto.")
