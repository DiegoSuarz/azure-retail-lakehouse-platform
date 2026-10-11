"""Captura y comprueba el origen inicial sin modificar sus registros."""

import argparse
import getpass
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sources/sqlserver"))
from load_initial_data import TABLES, odbc_value

COUNTS = {
    "categories": 6, "products": 60, "customers": 500,
    "orders": 2000, "order_items": 5862,
}
EXPECTED = {
    "order_status_counts": {
        "pending": 209, "confirmed": 1578, "cancelled": 213,
    },
    "gross_amount_all_orders": "21645086.45",
    "discount_amount_all_orders": "1667089.99",
    "net_amount_all_orders": "19977996.46",
    "net_amount_confirmed_orders": "15781257.30",
    "quantity_all_orders": 14792,
    "quantity_confirmed_orders": 11682,
}


def normalize(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return int(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("SQL_SERVER_HOST"))
    parser.add_argument("--port", type=int, default=os.environ.get(
        "SQL_SERVER_PORT", "1433"
    ))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.host:
        parser.error("Configura SQL_SERVER_HOST o indica --host.")
    if args.output.exists():
        parser.error("El archivo de salida ya existe; no se sobrescribirá.")
    if os.environ.get("SQL_SERVER_DATABASE", "TechRetail_OLTP") != "TechRetail_OLTP":
        parser.error("SQL_SERVER_DATABASE debe ser TechRetail_OLTP.")
    user = os.environ.get("SQL_SERVER_READER_USER", "retail_reader")
    if user != "retail_reader":
        parser.error("La captura requiere retail_reader.")

    password = os.environ.get("SQL_SERVER_READER_PASSWORD") or getpass.getpass(
        "Contraseña de retail_reader: "
    )
    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={odbc_value(f'{args.host},{args.port}')};"
        "DATABASE=TechRetail_OLTP;"
        f"UID={odbc_value(user)};PWD={odbc_value(password)};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    connection = pyodbc.connect(connection_string, timeout=15, autocommit=False)
    del password, connection_string
    entities = {}
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        connection.timeout = 60
        cursor = connection.cursor()
        cursor.execute(
            "SET NOCOUNT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;"
        )
        for table, fields in TABLES.items():
            keys = (
                ["order_id", "line_number"]
                if table == "order_items" else [fields[0]]
            )
            columns = ", ".join(f"[{name}]" for name in fields)
            ordering = ", ".join(f"[{name}]" for name in keys)
            records = cursor.execute(
                f"SELECT {columns} FROM dbo.[{table}] ORDER BY {ordering}"
            ).fetchall()
            rows = [
                dict(zip(fields, map(normalize, record))) for record in records
            ]
            if len(rows) != COUNTS[table]:
                raise RuntimeError(f"Conteo inesperado en {table}.")
            payload = json.dumps(
                rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            entities[table] = {
                "columns": fields, "primary_key": keys,
                "row_count": len(rows),
                "content_sha256": hashlib.sha256(payload).hexdigest(),
                "rows": rows,
            }
            print(f"PASS: {table}, {len(rows)} registros.")
    finally:
        connection.rollback()
        connection.close()

    orders = {
        row["order_id"]: row for row in entities["orders"]["rows"]
    }
    gross = discount = confirmed_net = Decimal("0")
    total_quantity = confirmed_quantity = 0
    for row in entities["order_items"]["rows"]:
        quantity = row["quantity"]
        amount = quantity * Decimal(row["unit_price"])
        reduction = Decimal(row["discount_amount"])
        gross += amount
        discount += reduction
        total_quantity += quantity
        if orders[row["order_id"]]["status"] == "confirmed":
            confirmed_net += amount - reduction
            confirmed_quantity += quantity
    controls = {
        "order_status_counts": dict(Counter(
            row["status"] for row in orders.values()
        )),
        "gross_amount_all_orders": format(gross, ".2f"),
        "discount_amount_all_orders": format(discount, ".2f"),
        "net_amount_all_orders": format(gross - discount, ".2f"),
        "net_amount_confirmed_orders": format(confirmed_net, ".2f"),
        "quantity_all_orders": total_quantity,
        "quantity_confirmed_orders": confirmed_quantity,
    }
    if controls != EXPECTED:
        raise RuntimeError("Los controles comerciales difieren de M2.")

    snapshot = {
        "schema_version": 1, "source_database": "TechRetail_OLTP",
        "capture_started_at": started_at,
        "capture_finished_at": datetime.now(timezone.utc).isoformat(),
        "capture_isolation": "serializable",
        "controls": controls, "entities": entities,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("PASS: estados, importes y unidades coinciden con M2.")
    print(f"GUARDADO: {args.output}")


if __name__ == "__main__":
    main()
