"""Lectura y normalización de productos de DummyJSON."""

from pyspark.sql import functions as F

from transformations.silver.dummyjson_schemas import PAGE_SCHEMA


def read_dummyjson_products(spark, bronze_root):
    """Lee las páginas originales y extrae sus productos."""
    pattern = (
        f"{bronze_root.rstrip('/')}/category=*/"
        "page_[0-9][0-9][0-9][0-9][0-9][0-9].json"
    )

    pages = (
        spark.read
        .schema(PAGE_SCHEMA)
        .option("multiLine", True)
        .option("mode", "FAILFAST")
        .json(pattern)
        .withColumn("source_file", F.input_file_name())
    )

    if pages.filter(F.col("products").isNull()).limit(1).count():
        raise ValueError("Existe una página sin lista de productos.")

    return (
        pages
        .select(
            "source_file",
            F.explode("products").alias("product"),
        )
        .select("product.*", "source_file")
    )


def normalize_dummyjson_products(
    products, ingestion_run_id, processing_run_id, processed_at
):
    """Selecciona los campos del contrato y añade procedencia."""
    return products.select(
        F.col("id").alias("external_product_id"),
        F.col("title").alias("external_product_name"),
        F.col("category").alias("external_category"),
        F.col("description").alias("external_description"),
        F.col("brand").alias("external_brand"),
        F.col("sku").alias("external_sku"),
        F.col("price").alias("external_price"),
        F.col("rating").alias("external_rating"),
        F.col("stock").alias("external_stock"),
        F.col("thumbnail").alias("thumbnail_url"),
        F.lit(None).cast("string").alias("external_currency_code"),
        F.lit("dummyjson").alias("source_system"),
        F.lit(ingestion_run_id).alias("ingestion_run_id"),
        F.lit(processing_run_id).alias("processing_run_id"),
        F.col("source_file"),
        F.lit(processed_at).alias("processed_at"),
    )


def validate_dummyjson_products(products):
    """Comprueba los valores esenciales y la identidad de los productos."""
    valid = (
        (F.col("source_system") == "dummyjson")
        & (F.col("external_product_id") > 0)
        & (F.length(F.trim(F.col("external_product_name"))) > 0)
        & F.col("external_category").isin(
            "laptops", "smartphones", "tablets", "mobile-accessories"
        )
        & F.col("external_price").isNotNull()
        & F.col("external_rating").between(0, 5)
        & (F.col("external_stock") >= 0)
        & F.col("external_currency_code").isNull()
    )

    invalid_rows = products.filter(
        ~F.coalesce(valid, F.lit(False))
    ).count()

    duplicate_groups = (
        products
        .groupBy("source_system", "external_product_id")
        .count()
        .filter(F.col("count") > 1)
        .count()
    )

    result = {
        "invalid_rows": invalid_rows,
        "duplicate_key_groups": duplicate_groups,
        "passed": invalid_rows == 0 and duplicate_groups == 0,
    }

    if not result["passed"]:
        raise ValueError(f"Productos DummyJSON incompatibles: {result}")

    return result


def write_dummyjson_delta(spark, products, silver_root):
    """Escribe el catálogo externo y verifica tipos y valores."""
    target = f"{silver_root.rstrip('/')}/external/dummyjson_products"

    products.write.format("delta").mode("errorifexists").save(target)

    recovered = (
        spark.read.format("delta")
        .load(target)
        .select(*products.columns)
    )

    expected_types = [
        (field.name, field.dataType) for field in products.schema
    ]
    actual_types = [
        (field.name, field.dataType) for field in recovered.schema
    ]
    if actual_types != expected_types:
        raise ValueError("DummyJSON: tipos diferentes después de escribir")

    if (
        products.exceptAll(recovered).count() != 0
        or recovered.exceptAll(products).count() != 0
    ):
        raise ValueError("DummyJSON: datos diferentes después de escribir")

    return {
        "entity": "dummyjson_products",
        "path": target,
        "row_count": recovered.count(),
        "verified": True,
    }
