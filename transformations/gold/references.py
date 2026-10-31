"""Construcción de tablas complementarias de Gold."""

from pyspark.sql import functions as F
from pyspark.sql import types as T


def build_exchange_rate_reference(exchange_rates):
    """Conserva las observaciones cambiarias válidas y no disponibles."""
    expected_types = (
        ("series_code", T.StringType()),
        ("observation_date", T.DateType()),
        ("rate_pen_per_usd", T.DecimalType(20, 14)),
        ("available", T.BooleanType()),
        ("raw_value", T.StringType()),
    )
    for column, expected_type in expected_types:
        if exchange_rates.schema[column].dataType != expected_type:
            raise ValueError(f"Tipo incompatible en referencia: {column}")

    reference = exchange_rates.select(
        *[column for column, _ in expected_types]
    )

    valid_rate = (
        (
            F.col("available")
            & F.col("rate_pen_per_usd").isNotNull()
            & (F.col("rate_pen_per_usd") > 0)
        )
        | (
            ~F.col("available")
            & F.col("rate_pen_per_usd").isNull()
        )
    )
    valid = (
        (F.col("series_code") == "PD04638PD")
        & F.col("observation_date").isNotNull()
        & F.col("available").isNotNull()
        & F.col("raw_value").isNotNull()
        & valid_rate
    )
    if reference.filter(
        ~F.coalesce(valid, F.lit(False))
    ).limit(1).count():
        raise ValueError("Referencia cambiaria incompatible.")

    if (
        reference.groupBy("series_code", "observation_date")
        .count()
        .filter(F.col("count") > 1)
        .limit(1)
        .count()
    ):
        raise ValueError("Referencia cambiaria duplicada por serie y fecha.")

    return reference


def build_product_catalog_mapping(mapping, dim_product, external_products):
    """Reúne atributos de los catálogos según asociaciones educativas."""
    from transformations.silver.dummyjson_transform import (
        validate_dummyjson_products,
    )
    from transformations.silver.product_mapping_transform import (
        validate_product_mapping,
    )

    for column in ("product_id", "product_key"):
        if dim_product.filter(
            F.col(column).isNull() | (F.col(column) <= 0)
        ).limit(1).count():
            raise ValueError(f"Clave local inválida: {column}")

        if (
            dim_product.groupBy(column)
            .count()
            .filter(F.col("count") > 1)
            .limit(1)
            .count()
        ):
            raise ValueError(f"Clave local duplicada: {column}")

    validate_dummyjson_products(external_products)
    validate_product_mapping(mapping, dim_product, external_products)

    associations = mapping.select(
        "source_system",
        "external_product_id",
        "product_id",
        "mapping_type",
        "mapping_note",
    )

    local_catalog = dim_product.select(
        "product_id",
        "product_key",
        F.col("sku").alias("local_sku"),
        F.col("product_name").alias("local_product_name"),
        F.col("brand").alias("local_brand"),
        F.col("category_name").alias("local_category_name"),
        F.col("list_price").alias("local_list_price_pen"),
    )

    external_catalog = external_products.select(
        "source_system",
        "external_product_id",
        "external_product_name",
        "external_category",
        "external_brand",
        "external_sku",
        "external_price",
        "external_currency_code",
        "external_rating",
        "external_stock",
    )

    return (
        associations
        .join(local_catalog, on="product_id", how="inner")
        .join(
            external_catalog,
            on=["source_system", "external_product_id"],
            how="inner",
        )
        .select(
            "product_key",
            "product_id",
            "local_sku",
            "local_product_name",
            "local_brand",
            "local_category_name",
            "local_list_price_pen",
            "source_system",
            "external_product_id",
            "external_product_name",
            "external_category",
            "external_brand",
            "external_sku",
            "external_price",
            "external_currency_code",
            "external_rating",
            "external_stock",
            "mapping_type",
            "mapping_note",
        )
    )
