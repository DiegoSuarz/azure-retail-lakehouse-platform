"""Controles de aceptación para los DataFrames de SQL Server."""

from functools import reduce
from operator import or_

from pyspark.sql import functions as F


PRIMARY_KEYS = {
    "categories": ("category_id",),
    "products": ("product_id",),
    "customers": ("customer_id",),
    "orders": ("order_id",),
    "order_items": ("order_id", "line_number"),
}


def validate_primary_key(frame, entity):
    """Devuelve conteos de claves inválidas y grupos duplicados."""
    keys = PRIMARY_KEYS[entity]

    invalid_condition = reduce(
        or_,
        [
            F.col(name).isNull() | (F.col(name) <= 0)
            for name in keys
        ],
    )

    invalid_rows = frame.filter(invalid_condition).count()

    duplicate_groups = (
        frame.groupBy(*keys)
        .count()
        .filter(F.col("count") > 1)
        .count()
    )

    return {
        "entity": entity,
        "keys": list(keys),
        "invalid_key_rows": invalid_rows,
        "duplicate_key_groups": duplicate_groups,
        "passed": invalid_rows == 0 and duplicate_groups == 0,
    }


FOREIGN_KEYS = (
    ("products", "category_id", "categories", "category_id"),
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
)


def validate_foreign_keys(frames):
    """Cuenta filas sin referencia para cada relación del contrato."""
    results = []

    for child, child_key, parent, parent_key in FOREIGN_KEYS:
        child_frame = frames[child].alias("child")
        parent_frame = frames[parent].select(parent_key).alias("parent")

        missing_rows = child_frame.join(
            parent_frame,
            F.col(f"child.{child_key}") == F.col(f"parent.{parent_key}"),
            "left_anti",
        ).count()

        results.append({
            "entity": child,
            "column": child_key,
            "reference_entity": parent,
            "reference_column": parent_key,
            "missing_reference_rows": missing_rows,
            "passed": missing_rows == 0,
        })

    return results


def validate_business_values(frame, entity):
    """Cuenta incumplimientos de valores comerciales por regla."""
    rules = {}

    if entity == "products":
        rules["positive_list_price"] = F.col("list_price") > 0

    elif entity == "orders":
        rules["allowed_status"] = F.col("status").isin(
            "pending", "confirmed", "cancelled"
        )
        rules["pen_currency"] = F.col("currency_code") == "PEN"

    elif entity == "order_items":
        rules["positive_quantity"] = F.col("quantity") > 0
        rules["positive_unit_price"] = F.col("unit_price") > 0
        rules["valid_discount"] = (
            (F.col("discount_amount") >= 0)
            & (
                F.col("discount_amount")
                <= F.col("quantity") * F.col("unit_price")
            )
        )

    elif entity not in PRIMARY_KEYS:
        raise ValueError(f"Entidad no admitida: {entity}")

    if not rules:
        return []

    summary = frame.agg(*[
        F.count(
            F.when(
                ~F.coalesce(condition, F.lit(False)),
                F.lit(1),
            )
        ).alias(name)
        for name, condition in rules.items()
    ]).first().asDict()

    return [
        {
            "entity": entity,
            "rule": name,
            "invalid_rows": count,
            "passed": count == 0,
        }
        for name, count in summary.items()
    ]


def validate_record_timestamps(frame, entity):
    """Comprueba presencia y orden de las fechas técnicas."""
    if entity not in PRIMARY_KEYS:
        raise ValueError(f"Entidad no admitida: {entity}")

    valid = (
        F.col("created_at").isNotNull()
        & F.col("updated_at").isNotNull()
        & (F.col("updated_at") >= F.col("created_at"))
    )

    invalid_rows = frame.filter(
        ~F.coalesce(valid, F.lit(False))
    ).count()

    return {
        "entity": entity,
        "rule": "updated_at_not_before_created_at",
        "invalid_rows": invalid_rows,
        "passed": invalid_rows == 0,
    }


def validate_order_completeness(frames):
    """Cuenta pedidos que no tienen ninguna línea."""
    orders = frames["orders"].alias("orders")
    item_orders = (
        frames["order_items"]
        .select("order_id")
        .distinct()
        .alias("item_orders")
    )

    missing_rows = orders.join(
        item_orders,
        F.col("orders.order_id") == F.col("item_orders.order_id"),
        "left_anti",
    ).count()

    return {
        "entity": "orders",
        "rule": "order_has_items",
        "orders_without_items": missing_rows,
        "passed": missing_rows == 0,
    }


TEXT_STORAGE = {
    "categories": {
        "category_name": ("utf-16-le", 200),
    },
    "products": {
        "sku": ("cp1252", 40),
        "product_name": ("utf-16-le", 400),
        "brand": ("utf-16-le", 200),
    },
    "customers": {
        "first_name": ("utf-16-le", 200),
        "last_name": ("utf-16-le", 200),
        "email": ("cp1252", 254),
        "city": ("utf-16-le", 200),
        "region": ("utf-16-le", 200),
    },
    "orders": {
        "status": ("cp1252", 20),
        "currency_code": ("cp1252", 3),
    },
    "order_items": {},
}


def text_fits_storage(value, encoding, max_bytes):
    """Comprueba presencia, representación y longitud sin alterar texto."""
    if value is None:
        return False
    try:
        return len(value.encode(encoding, errors="strict")) <= max_bytes
    except UnicodeError:
        return False


def validate_text_storage(frame, entity):
    """Cuenta textos incompatibles con el almacenamiento del origen."""
    rules = TEXT_STORAGE[entity]
    results = []

    for column, (encoding, max_bytes) in rules.items():
        checker = F.udf(
            lambda value, enc=encoding, limit=max_bytes:
                text_fits_storage(value, enc, limit),
            "boolean",
        )

        invalid_rows = frame.filter(~checker(F.col(column))).count()

        results.append({
            "entity": entity,
            "column": column,
            "rule": "text_fits_source_storage",
            "encoding": encoding,
            "max_bytes": max_bytes,
            "invalid_rows": invalid_rows,
            "passed": invalid_rows == 0,
        })

    return results


ALTERNATE_KEYS = {
    "categories": ("category_name",),
    "products": ("sku",),
    "customers": ("email",),
    "orders": (),
    "order_items": (),
}


def validate_alternate_keys(frame, entity):
    """Detecta duplicados bajo la política de comparación de Silver."""
    results = []

    for column in ALTERNATE_KEYS[entity]:
        comparison = F.lower(F.rtrim(F.col(column)))

        duplicate_groups = (
            frame.select(comparison.alias("comparison_key"))
            .groupBy("comparison_key")
            .count()
            .filter(F.col("count") > 1)
            .count()
        )

        null_rows = frame.filter(F.col(column).isNull()).count()

        results.append({
            "entity": entity,
            "column": column,
            "comparison_policy": "spark_lower_rtrim",
            "null_rows": null_rows,
            "duplicate_key_groups": duplicate_groups,
            "passed": null_rows == 0 and duplicate_groups == 0,
        })

    return results
