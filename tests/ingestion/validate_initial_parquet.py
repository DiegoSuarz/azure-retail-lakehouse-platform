"""Compara los Parquet iniciales con las referencias de SQL Server."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

TABLES = {"categories", "products", "customers", "orders", "order_items"}
MONEY = {"list_price", "unit_price", "discount_amount"}
DATES = {"created_at", "updated_at", "order_date"}


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def digest(rows):
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return int(value)
    return value


def indexed(rows, keys, label):
    result = {}
    for row in rows:
        require(all(value is not None for value in row.values()),
                f"Valores nulos en {label}")
        key = tuple(row[name] for name in keys)
        require(key not in result, f"Clave duplicada en {label}: {key}")
        result[key] = row
    return result


def read_snapshot(path):
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    require(snapshot["schema_version"] == 1, "Versión de referencia")
    require(snapshot["source_database"] == "TechRetail_OLTP",
            "Base de datos de referencia")
    require(set(snapshot["entities"]) == TABLES, "Entidades de referencia")
    for name, entity in snapshot["entities"].items():
        rows = entity["rows"]
        require(len(rows) == entity["row_count"], f"Conteo de referencia: {name}")
        require(digest(rows) == entity["content_sha256"],
                f"Hash de referencia: {name}")
        indexed(rows, entity["primary_key"], f"referencia/{name}")
    return snapshot


def check_type(field):
    name, kind = field.name, field.type
    if name in MONEY:
        valid = pa.types.is_decimal(kind) and kind.scale == 2 and kind.precision >= 18
    elif name in DATES:
        valid = pa.types.is_timestamp(kind)
    elif name == "is_active":
        valid = pa.types.is_boolean(kind) or pa.types.is_integer(kind)
    elif name.endswith("_id") or name in {"line_number", "quantity"}:
        valid = pa.types.is_integer(kind)
    else:
        valid = pa.types.is_string(kind) or pa.types.is_large_string(kind)
    require(valid, f"Tipo incompatible: {name}, {kind}")


def validate_entity(root, name, reference):
    paths = sorted((root / name).rglob("*.parquet"))
    require(bool(paths), f"No hay archivos Parquet para {name}")
    rows, files = [], []
    for path in paths:
        with pq.ParquetFile(path) as parquet:
            schema = parquet.schema_arrow
            require(len(schema.names) == len(reference["columns"])
                    and set(schema.names) == set(reference["columns"]),
                    f"Columnas diferentes: {path.name}")
            for field in schema:
                check_type(field)
            rows.extend(
                {key: normalize(value) for key, value in row.items()}
                for row in parquet.read().to_pylist()
            )
            schema_text = str(schema)
        files.append({
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "arrow_schema": schema_text,
        })

    require(len(rows) == reference["row_count"], f"Conteo diferente: {name}")
    expected = indexed(reference["rows"], reference["primary_key"], name)
    actual = indexed(rows, reference["primary_key"], name)
    require(actual.keys() == expected.keys(), f"Claves diferentes: {name}")
    for key in expected:
        require(actual[key] == expected[key],
                f"Valores diferentes en {name}, clave {key}")
    print(f"PASS: {name}, {len(rows)} registros y valores idénticos.")
    return rows, {
        "source_row_count": reference["row_count"],
        "destination_row_count": len(rows),
        "files": files,
        "record_comparison": "passed",
    }


def check_relationships(data):
    categories = {row["category_id"] for row in data["categories"]}
    products = {row["product_id"] for row in data["products"]}
    customers = {row["customer_id"] for row in data["customers"]}
    orders = {row["order_id"] for row in data["orders"]}
    require(all(row["category_id"] in categories for row in data["products"]),
            "Relación products/categories")
    require(all(row["customer_id"] in customers for row in data["orders"]),
            "Relación orders/customers")
    require(all(row["order_id"] in orders and row["product_id"] in products
                for row in data["order_items"]), "Relaciones de order_items")
    require({row["order_id"] for row in data["order_items"]} == orders,
            "Pedidos sin líneas")
    print("PASS: relaciones y presencia de líneas por pedido.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--parquet-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    require(not args.report.exists(), "El informe ya existe")
    require(args.before.resolve() != args.after.resolve(),
            "Las referencias deben ser archivos distintos")

    before = read_snapshot(args.before)
    after = read_snapshot(args.after)
    require(datetime.fromisoformat(after["capture_started_at"])
            >= datetime.fromisoformat(before["capture_finished_at"]),
            "Orden temporal de las referencias")
    require(before["controls"] == after["controls"], "Controles del origen cambiaron")
    for name in TABLES:
        require(before["entities"][name] == after["entities"][name],
                f"Contenido del origen cambió: {name}")
    print("PASS: referencias del origen antes y después coinciden.")

    data, entities = {}, {}
    known_files = set()
    for name in sorted(TABLES):
        data[name], entities[name] = validate_entity(
            args.parquet_dir, name, before["entities"][name]
        )
        known_files.update(
            item["path"] for item in entities[name]["files"]
        )
    all_files = {
        path.relative_to(args.parquet_dir).as_posix()
        for path in args.parquet_dir.rglob("*.parquet")
    }
    require(all_files == known_files, "Hay Parquet fuera de las cinco entidades")
    check_relationships(data)

    report = {
        "schema_version": 1,
        "status": "validated",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "source_before_sha256": hashlib.sha256(args.before.read_bytes()).hexdigest(),
        "source_after_sha256": hashlib.sha256(args.after.read_bytes()).hexdigest(),
        "entities": entities,
        "reference_controls": before["controls"],
        "reconciliation": {
            "source_before_after": "passed",
            "columns_and_types": "passed",
            "primary_keys": "passed",
            "all_record_values": "passed",
            "relationships": "passed",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"GUARDADO: {args.report}")
    print("ALCANCE: validación local; manifiesto cloud todavía pendiente.")


if __name__ == "__main__":
    main()
