"""Guarda los productos y el límite inicial para la prueba de CDC."""

import argparse
import getpass
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pyodbc

from sources.sqlserver.load_initial_data import odbc_value


def serialize(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="milliseconds")
    if isinstance(value, Decimal):
        return format(value, ".2f")
    raise TypeError(f"Tipo no admitido: {type(value).__name__}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("SQL_SERVER_HOST"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.host:
        parser.error("Indica --host o configura SQL_SERVER_HOST.")
    if args.output.exists():
        parser.error("El archivo de salida ya existe.")

    port = os.environ.get("SQL_SERVER_PORT", "1433")
    password = os.environ.get("SQL_SERVER_READER_PASSWORD")
    if not password:
        password = getpass.getpass("Contraseña de retail_reader: ")

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={odbc_value(f'{args.host},{port}')};"
        "DATABASE=TechRetail_OLTP;"
        "UID=retail_reader;"
        f"PWD={odbc_value(password)};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    connection = pyodbc.connect(
        connection_string, timeout=15, autocommit=False
    )
    del password, connection_string

    try:
        connection.timeout = 60
        cursor = connection.cursor()
        cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;")

        cursor.execute("""
            SELECT product_id, category_id, sku, product_name, brand,
                   list_price, is_active, created_at, updated_at
            FROM dbo.products WITH (TABLOCK, HOLDLOCK)
            ORDER BY product_id
        """)
        columns = [column[0] for column in cursor.description]
        products = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if len(products) != 60:
            raise RuntimeError("Se esperaban 60 productos antes de las pruebas.")

        lsn = cursor.execute("""
            SELECT sys.fn_varbintohexstr(sys.fn_cdc_get_max_lsn())
        """).fetchval()

        if not lsn or int(lsn, 16) == 0:
            raise RuntimeError("El límite LSN todavía no es válido.")

        baseline = {
            "source_database": "TechRetail_OLTP",
            "capture_instance": "dbo_products",
            "baseline_lsn": lsn,
            "products": products,
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(
                baseline, stream, ensure_ascii=False,
                indent=2, default=serialize,
            )
            stream.write("\n")
    finally:
        connection.rollback()
        connection.close()

    print(f"PASS: {len(products)} productos conservados.")
    print(f"LSN inicial: {lsn}")
    print(f"GUARDADO: {args.output}")


if __name__ == "__main__":
    main()
