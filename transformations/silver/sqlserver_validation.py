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
