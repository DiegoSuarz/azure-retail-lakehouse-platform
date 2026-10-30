"""Construcción integrada de las siete tablas iniciales de Gold."""

from datetime import datetime, timezone

from pyspark.sql import functions as F

from transformations.gold.dimensions import (
    add_order_business_date,
    build_customer_dimension,
    build_date_dimension,
    build_order_status_dimension,
    build_product_dimension,
)
from transformations.gold.references import (
    build_exchange_rate_reference,
    build_product_catalog_mapping,
)
from transformations.gold.sales_transform import build_sales_fact


def build_gold_tables(inputs, gold_processing_run_id, gold_processed_at):
    """Construye el modelo inicial y añade procedencia común."""
    if (
        not isinstance(gold_processing_run_id, str)
        or not gold_processing_run_id.strip()
    ):
        raise ValueError("Se requiere gold_processing_run_id no vacío.")

    if (
        not isinstance(gold_processed_at, datetime)
        or gold_processed_at.tzinfo is None
        or gold_processed_at.utcoffset() is None
    ):
        raise ValueError("gold_processed_at debe incluir zona horaria.")

    processed_at_utc = gold_processed_at.astimezone(timezone.utc)

    business_dates = add_order_business_date(inputs["orders"])
    bounds = business_dates.agg(
        F.min("business_date").alias("first_date"),
        F.max("business_date").alias("last_date"),
    ).first()

    if bounds["first_date"] is None:
        raise ValueError("Se requieren pedidos para definir el calendario.")

    products = build_product_dimension(
        inputs["products"], inputs["categories"]
    )
    customers = build_customer_dimension(inputs["customers"])
    dates = build_date_dimension(
        inputs["orders"].sparkSession,
        bounds["first_date"].year,
        bounds["last_date"].year,
    )
    statuses = build_order_status_dimension(
        inputs["orders"].sparkSession
    )
    rates = build_exchange_rate_reference(inputs["exchange_rates"])
    catalog_mapping = build_product_catalog_mapping(
        inputs["product_external_mapping"],
        products,
        inputs["dummyjson_products"],
    )

    sales = build_sales_fact(
        inputs["order_items"],
        inputs["orders"],
        products,
        customers,
        dates,
        statuses,
        rates,
        gold_processing_run_id,
        processed_at_utc,
    )

    tables = {
        "dim_product": products,
        "dim_customer": customers,
        "dim_date": dates,
        "dim_order_status": statuses,
        "ref_exchange_rates": rates,
        "product_catalog_mapping": catalog_mapping,
    }

    tables = {
        name: (
            frame
            .withColumn(
                "gold_processing_run_id",
                F.lit(gold_processing_run_id),
            )
            .withColumn(
                "gold_processed_at",
                F.lit(processed_at_utc),
            )
        )
        for name, frame in tables.items()
    }
    tables["fact_sales"] = sales

    return tables
