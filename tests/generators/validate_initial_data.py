"""Valida los archivos iniciales sin modificar los datos."""

import csv
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data-dir", type=Path, default=Path("data/initial"))
args = parser.parse_args()
ROOT = args.data_dir


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


tables = {}
expected_counts = {
    "categories": 6,
    "products": 60,
    "customers": 500,
    "orders": 2000,
    "order_items": None,
}
require(
    {path.stem for path in ROOT.glob("*.csv")} == set(expected_counts),
    "Conjunto de archivos CSV",
)
for name, expected_count in expected_counts.items():
    with (ROOT / f"{name}.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        reader = csv.DictReader(stream)
        require(
            reader.fieldnames
            and len(reader.fieldnames) == len(set(reader.fieldnames)),
            f"Cabecera válida: {name}",
        )
        rows = list(reader)
        require(
            all(
                None not in row
                and all(value is not None for value in row.values())
                for row in rows
            ),
            f"Filas con estructura válida: {name}",
        )
    if expected_count is not None:
        require(len(rows) == expected_count, f"Conteo: {name}")
    tables[name] = rows

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

cutoff = date("2026-10-01T00:00:00Z")
start = date("2026-01-01T00:00:00Z")

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

print("PASS: estructura y conteos de los cinco CSV.")
print("PASS: claves, relaciones, fechas y reglas comerciales.")
print("PASS: todos los pedidos tienen entre una y cinco líneas.")
print("Estados:", dict(Counter(row["status"] for row in orders.values())))
print("Bruto PEN:", gross_total)
print("Descuento PEN:", discount_total)
print("Neto PEN:", gross_total - discount_total)
print("Neto confirmado PEN:", confirmed_net)
print("Unidades confirmadas:", confirmed_quantity)
