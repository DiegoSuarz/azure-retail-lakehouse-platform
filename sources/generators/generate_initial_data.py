"""Genera el conjunto inicial reproducible del retail tecnológico."""

import argparse
import csv
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

CENT = Decimal("0.01")
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
CUTOFF = datetime(2026, 10, 1, tzinfo=timezone.utc)
REFERENCE_DATE = datetime(2025, 12, 1, tzinfo=timezone.utc)

CATALOG = [
    ("Laptops", "Laptop", 180000, 650000),
    ("Smartphones", "Smartphone", 50000, 450000),
    ("Monitores", "Monitor", 40000, 250000),
    ("Perifericos", "Periferico", 3000, 50000),
    ("Almacenamiento", "Unidad de almacenamiento", 5000, 80000),
    ("Redes", "Equipo de red", 8000, 120000),
]

LOCATIONS = [
    ("Lima", "Lima"),
    ("Arequipa", "Arequipa"),
    ("Trujillo", "La Libertad"),
    ("Cusco", "Cusco"),
    ("Piura", "Piura"),
]


def timestamp(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def money(value):
    return format(value.quantize(CENT), ".2f")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(seed):
    rng = random.Random(seed)
    reference_time = timestamp(REFERENCE_DATE)

    categories = []
    products = []
    customers = []
    orders = []
    order_items = []

    for category_id, (name, label, minimum, maximum) in enumerate(CATALOG, 1):
        categories.append({
            "category_id": category_id,
            "category_name": name,
            "created_at": reference_time,
            "updated_at": reference_time,
        })

        for model in range(1, 11):
            product_id = len(products) + 1
            price = Decimal(rng.randint(minimum, maximum)) / 100
            products.append({
                "product_id": product_id,
                "category_id": category_id,
                "sku": f"TECH-{product_id:04d}",
                "product_name": f"{label} modelo {model:02d}",
                "brand": f"Marca sintetica {(model - 1) % 5 + 1}",
                "list_price": money(price),
                "is_active": 1,
                "created_at": reference_time,
                "updated_at": reference_time,
            })

    for customer_id in range(1, 501):
        city, region = rng.choice(LOCATIONS)
        customers.append({
            "customer_id": customer_id,
            "first_name": f"Cliente{customer_id:04d}",
            "last_name": f"Sintetico{customer_id:04d}",
            "email": f"customer{customer_id:04d}@example.com",
            "city": city,
            "region": region,
            "is_active": 1,
            "created_at": reference_time,
            "updated_at": reference_time,
        })

    gross_total = Decimal("0")
    discount_total = Decimal("0")
    confirmed_net_total = Decimal("0")
    confirmed_quantity = 0
    status_counts = dict.fromkeys(("pending", "confirmed", "cancelled"), 0)
    period_seconds = int((CUTOFF - START).total_seconds())

    for order_id in range(1, 2001):
        order_date = START + timedelta(seconds=rng.randrange(period_seconds))
        status = rng.choices(
            ["pending", "confirmed", "cancelled"],
            weights=[10, 80, 10],
            k=1,
        )[0]

        available_seconds = int((CUTOFF - order_date).total_seconds()) - 1
        delay = (
            rng.randint(0, min(available_seconds, 86400))
            if status != "pending"
            else 0
        )
        updated_at = order_date + timedelta(seconds=delay)
        status_counts[status] += 1

        orders.append({
            "order_id": order_id,
            "customer_id": rng.randint(1, 500),
            "order_date": timestamp(order_date),
            "status": status,
            "currency_code": "PEN",
            "created_at": timestamp(order_date),
            "updated_at": timestamp(updated_at),
        })

        for line_number in range(1, rng.randint(1, 5) + 1):
            product = rng.choice(products)
            quantity = rng.randint(1, 4)
            unit_price = Decimal(product["list_price"])
            gross = quantity * unit_price
            discount_rate = Decimal(rng.choice([0, 5, 10, 15])) / 100
            discount = (gross * discount_rate).quantize(CENT)
            net = gross - discount

            order_items.append({
                "order_id": order_id,
                "line_number": line_number,
                "product_id": product["product_id"],
                "quantity": quantity,
                "unit_price": money(unit_price),
                "discount_amount": money(discount),
                "created_at": timestamp(order_date),
                "updated_at": timestamp(order_date),
            })

            gross_total += gross
            discount_total += discount
            if status == "confirmed":
                confirmed_net_total += net
                confirmed_quantity += quantity

    datasets = {
        "categories": categories,
        "products": products,
        "customers": customers,
        "orders": orders,
        "order_items": order_items,
    }
    controls = {
        "order_status_counts": status_counts,
        "gross_amount_all_orders": money(gross_total),
        "discount_amount_all_orders": money(discount_total),
        "net_amount_all_orders": money(gross_total - discount_total),
        "net_amount_confirmed_orders": money(confirmed_net_total),
        "quantity_confirmed_orders": confirmed_quantity,
    }
    return datasets, controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data/initial"))
    args = parser.parse_args()

    # Evita sobrescribir una generación existente.
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("La carpeta de salida no está vacía. Usa otra ubicación.")

    datasets, controls = generate(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    files = {}
    for name, rows in datasets.items():
        filename = f"{name}.csv"
        digest = write_csv(args.output_dir / filename, rows)
        files[filename] = {"row_count": len(rows), "sha256": digest}

    manifest = {
        "generator_version": 1,
        "seed": args.seed,
        "currency": "PEN",
        "encoding": "utf-8",
        "delimiter": ",",
        "timestamp_timezone": "UTC",
        "period_start_inclusive": timestamp(START),
        "cutoff_exclusive": timestamp(CUTOFF),
        "files": files,
        "controls": controls,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
