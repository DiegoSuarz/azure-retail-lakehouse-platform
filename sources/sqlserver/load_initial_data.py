"""Carga y reconcilia los datos iniciales en SQL Server."""

import argparse
import csv
import getpass
from collections import Counter
import os
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/initial"

# Orden de inserción según las dependencias entre entidades.
TABLES = {
    "categories": [
        "category_id", "category_name", "created_at", "updated_at",
    ],
    "products": [
        "product_id", "category_id", "sku", "product_name", "brand",
        "list_price", "is_active", "created_at", "updated_at",
    ],
    "customers": [
        "customer_id", "first_name", "last_name", "email", "city",
        "region", "is_active", "created_at", "updated_at",
    ],
    "orders": [
        "order_id", "customer_id", "order_date", "status",
        "currency_code", "created_at", "updated_at",
    ],
    "order_items": [
        "order_id", "line_number", "product_id", "quantity",
        "unit_price", "discount_amount", "created_at", "updated_at",
    ],
}

INTEGER_FIELDS = {
    "category_id", "product_id", "customer_id", "order_id",
    "line_number", "quantity", "is_active",
}
DECIMAL_FIELDS = {"list_price", "unit_price", "discount_amount"}
DATE_FIELDS = {"created_at", "updated_at", "order_date"}


def convert(field, value):
    if field in INTEGER_FIELDS:
        return int(value)
    if field in DECIMAL_FIELDS:
        return Decimal(value)
    if field in DATE_FIELDS:
        # SQL datetime2 no conserva zona: almacenamos el instante en UTC.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    return value


def odbc_value(value):
    return "{" + value.replace("}", "}}") + "}"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("SQL_SERVER_HOST"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SQL_SERVER_PORT", "1433")))
    args = parser.parse_args()
    if not args.host:
        parser.error("Indica --host o configura SQL_SERVER_HOST.")
    if os.environ.get("SQL_SERVER_DATABASE", "TechRetail_OLTP") != "TechRetail_OLTP":
        parser.error("SQL_SERVER_DATABASE debe ser TechRetail_OLTP.")
    if os.environ.get("SQL_SERVER_USER", "retail_loader") != "retail_loader":
        parser.error("La carga requiere el usuario retail_loader.")

    subprocess.run(
        [sys.executable, str(ROOT / "tests/generators/validate_initial_data.py")],
        cwd=ROOT,
        check=True,
    )

    datasets = {}

    for table, fields in TABLES.items():
        with (DATA / f"{table}.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames == fields, f"Columnas inesperadas: {table}")
            datasets[table] = [
                tuple(convert(field, row[field]) for field in fields)
                for row in reader
            ]

    orders = [
        dict(zip(TABLES["orders"], row))
        for row in datasets["orders"]
    ]
    order_status = {row["order_id"]: row["status"] for row in orders}
    expected_status_counts = dict(Counter(order_status.values()))
    expected_totals = [Decimal("0") for _ in range(4)] + [0]

    for values in datasets["order_items"]:
        row = dict(zip(TABLES["order_items"], values))
        gross = row["quantity"] * row["unit_price"]
        discount = row["discount_amount"]
        net = gross - discount
        expected_totals[0] += gross
        expected_totals[1] += discount
        expected_totals[2] += net
        if order_status[row["order_id"]] == "confirmed":
            expected_totals[3] += net
            expected_totals[4] += row["quantity"]

    password = os.environ.get("SQL_SERVER_PASSWORD") or getpass.getpass(
        "Contraseña de retail_loader: "
    )
    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={odbc_value(f'{args.host},{args.port}')};"
        "DATABASE=TechRetail_OLTP;"
        "UID=retail_loader;"
        f"PWD={odbc_value(password)};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    connection = pyodbc.connect(
        connection_string, autocommit=False, timeout=15
    )
    del password, connection_string

    try:
        cursor = connection.cursor()
        cursor.execute("SET XACT_ABORT ON; SET NOCOUNT ON;")

        # Conserva bloqueos exclusivos hasta el commit o rollback.
        for table in TABLES:
            count = cursor.execute(
                f"SELECT COUNT_BIG(*) FROM dbo.[{table}] "
                "WITH (TABLOCKX, HOLDLOCK)"
            ).fetchone()[0]
            require(count == 0, f"Tabla con datos: {table}. Carga cancelada.")

        for table, fields in TABLES.items():
            columns = ", ".join(f"[{field}]" for field in fields)
            placeholders = ", ".join("?" for _ in fields)
            cursor.executemany(
                f"INSERT INTO dbo.[{table}] ({columns}) "
                f"VALUES ({placeholders})",
                datasets[table],
            )

        for table in TABLES:
            actual = cursor.execute(
                f"SELECT COUNT_BIG(*) FROM dbo.[{table}]"
            ).fetchone()[0]
            expected = len(datasets[table])
            require(actual == expected, f"Conteo incorrecto: {table}")
            print(f"PASS: {table}, {actual} registros.")

        status_counts = dict(cursor.execute(
            "SELECT status, COUNT_BIG(*) FROM dbo.orders GROUP BY status"
        ).fetchall())
        require(
            status_counts == expected_status_counts,
            "Conteos por estado diferentes de los CSV.",
        )

        totals = cursor.execute("""
            SELECT
                SUM(i.quantity * i.unit_price),
                SUM(i.discount_amount),
                SUM(i.quantity * i.unit_price - i.discount_amount),
                SUM(CASE WHEN o.status = 'confirmed'
                    THEN i.quantity * i.unit_price - i.discount_amount
                    ELSE 0 END),
                SUM(CASE WHEN o.status = 'confirmed'
                    THEN CAST(i.quantity AS bigint) ELSE 0 END)
            FROM dbo.order_items AS i
            JOIN dbo.orders AS o ON o.order_id = i.order_id;
        """).fetchone()

        names = [
            "gross_amount_all_orders",
            "discount_amount_all_orders",
            "net_amount_all_orders",
            "net_amount_confirmed_orders",
        ]
        for index, name in enumerate(names):
            require(
                totals[index] == expected_totals[index],
                f"Importe incorrecto: {name}",
            )
        require(
            totals[4] == expected_totals[4],
            "Unidades confirmadas diferentes de los CSV.",
        )

        connection.commit()
        print("PASS: estados, importes y unidades reconciliados.")
        print("COMMIT: carga inicial completada.")
    except Exception:
        connection.rollback()
        print("ROLLBACK: la carga no se confirmó.", file=sys.stderr)
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
