"""Lectura y validación del modelo Gold persistido."""

import json
from pathlib import Path

from transformations.gold.inputs import EXPECTED_ENTITIES


EXPECTED_GOLD_TABLES = {
    "dim_product",
    "dim_customer",
    "dim_date",
    "dim_order_status",
    "ref_exchange_rates",
    "product_catalog_mapping",
    "fact_sales",
}


def read_gold_execution(spark, report_path):
    """Recupera las versiones Silver y Gold registradas en una ejecución."""
    report = json.loads(
        Path(report_path).read_text(encoding="utf-8")
    )

    if (
        report.get("scope") != "local_gold_initial"
        or report.get("status") != "tables_verified"
    ):
        raise ValueError("Se requiere una ejecución con tablas verificadas.")

    specifications = {}

    for section, expected_names in (
        ("inputs", EXPECTED_ENTITIES),
        ("tables", EXPECTED_GOLD_TABLES),
    ):
        entries = report.get(section)
        if not isinstance(entries, dict) or set(entries) != expected_names:
            raise ValueError(f"Inventario incompatible: {section}")

        specifications[section] = {}

        for name, record in entries.items():
            if not isinstance(record, dict):
                raise ValueError(f"Registro incompatible: {section}/{name}")

            path = record.get("path")
            version = record.get("version")
            row_count = record.get("row_count")

            if not isinstance(path, str) or not path.strip():
                raise ValueError(f"Ruta inválida: {section}/{name}")

            if not Path(path).is_absolute():
                raise ValueError(f"Se requiere ruta absoluta: {section}/{name}")

            if type(version) is not int or version < 0:
                raise ValueError(f"Versión inválida: {section}/{name}")

            if type(row_count) is not int or row_count < 0:
                raise ValueError(f"Conteo inválido: {section}/{name}")

            if section == "tables" and record.get("verified") is not True:
                raise ValueError(f"Tabla sin verificación: {name}")

            specifications[section][name] = (path, version, row_count)

    recovered = {}

    for section, entries in specifications.items():
        recovered[section] = {}

        for name, (path, version, expected_count) in entries.items():
            frame = (
                spark.read.format("delta")
                .option("versionAsOf", version)
                .load(path)
            )

            actual_count = frame.count()
            if actual_count != expected_count:
                raise ValueError(
                    f"Conteo diferente en {section}/{name}: "
                    f"esperado={expected_count}, obtenido={actual_count}"
                )

            recovered[section][name] = frame

    return report, recovered["inputs"], recovered["tables"]


def validate_gold_relationships(tables):
    """Comprueba el grano, las claves y las referencias del modelo inicial."""
    from pyspark.sql import functions as F

    if set(tables) != EXPECTED_GOLD_TABLES:
        raise ValueError("Inventario Gold incompatible para validar relaciones.")

    unique_keys = (
        ("dim_product", ("product_key",)),
        ("dim_product", ("product_id",)),
        ("dim_customer", ("customer_key",)),
        ("dim_customer", ("customer_id",)),
        ("dim_date", ("date_key",)),
        ("dim_date", ("full_date",)),
        ("dim_order_status", ("order_status_key",)),
        ("dim_order_status", ("status",)),
        ("fact_sales", ("order_id", "line_number")),
        ("ref_exchange_rates", ("series_code", "observation_date")),
        ("product_catalog_mapping", ("source_system", "external_product_id")),
        ("product_catalog_mapping", ("source_system", "product_id")),
    )
    positive_columns = {
        "product_key", "product_id", "customer_key", "customer_id",
        "date_key", "order_status_key", "order_id", "line_number",
        "external_product_id",
    }
    checks = []

    for table_name, columns in unique_keys:
        frame = tables[table_name]
        invalid = F.lit(False)

        for column in columns:
            invalid = invalid | F.col(column).isNull()
            if column in positive_columns:
                invalid = invalid | (F.col(column) <= 0)

        invalid_count = frame.filter(invalid).count()
        duplicate_groups = (
            frame.groupBy(*columns)
            .count()
            .filter(F.col("count") > 1)
            .count()
        )

        check = {
            "table": table_name,
            "keys": list(columns),
            "invalid_key_rows": invalid_count,
            "duplicate_key_groups": duplicate_groups,
            "passed": invalid_count == 0 and duplicate_groups == 0,
        }
        checks.append(check)

        if not check["passed"]:
            raise ValueError(f"Clave Gold incompatible: {check}")

    relationships = (
        ("fact_sales", "product_key", "dim_product", "product_key"),
        ("fact_sales", "customer_key", "dim_customer", "customer_key"),
        ("fact_sales", "date_key", "dim_date", "date_key"),
        (
            "fact_sales", "order_status_key",
            "dim_order_status", "order_status_key",
        ),
        (
            "product_catalog_mapping", "product_key",
            "dim_product", "product_key",
        ),
        (
            "product_catalog_mapping", "product_id",
            "dim_product", "product_id",
        ),
    )

    for source_name, source_column, target_name, target_column in relationships:
        source = tables[source_name]
        reference = tables[target_name].select(
            F.col(target_column).alias(source_column)
        )

        missing_count = source.join(
            reference,
            on=source_column,
            how="left_anti",
        ).count()

        check = {
            "table": source_name,
            "column": source_column,
            "reference_table": target_name,
            "reference_column": target_column,
            "missing_reference_rows": missing_count,
            "passed": missing_count == 0,
        }
        checks.append(check)

        if not check["passed"]:
            raise ValueError(f"Referencia Gold inexistente: {check}")

    mismatched_products = tables["product_catalog_mapping"].select(
        "product_id", "product_key"
    ).join(
        tables["dim_product"].select("product_id", "product_key"),
        on=["product_id", "product_key"],
        how="left_anti",
    ).count()

    pair_check = {
        "table": "product_catalog_mapping",
        "rule": "product_id_matches_product_key",
        "invalid_rows": mismatched_products,
        "passed": mismatched_products == 0,
    }
    checks.append(pair_check)

    if not pair_check["passed"]:
        raise ValueError(f"Correspondencia de producto incompatible: {pair_check}")

    return {"passed": True, "checks": checks}


def validate_gold_provenance(tables, report):
    """Comprueba que todas las filas pertenezcan a la ejecución registrada."""
    from datetime import datetime, timezone

    from pyspark.sql import functions as F
    from pyspark.sql import types as T

    if set(tables) != EXPECTED_GOLD_TABLES:
        raise ValueError("Inventario Gold incompatible para validar procedencia.")

    run_id = report.get("gold_processing_run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("Identificador de ejecución inválido en el informe.")

    processed_at_text = report.get("gold_processed_at")
    if not isinstance(processed_at_text, str):
        raise ValueError("Fecha de procesamiento inválida en el informe.")

    try:
        processed_at = datetime.fromisoformat(
            processed_at_text.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(
            "Fecha de procesamiento inválida en el informe."
        ) from error

    if (
        processed_at.tzinfo is None
        or processed_at.utcoffset() is None
    ):
        raise ValueError("La fecha del informe debe incluir zona horaria.")

    processed_at_utc = processed_at.astimezone(timezone.utc)
    checks = []

    for name, frame in tables.items():
        expected_types = (
            ("gold_processing_run_id", T.StringType()),
            ("gold_processed_at", T.TimestampType()),
        )
        for column, expected_type in expected_types:
            if column not in frame.columns:
                raise ValueError(f"Columna de procedencia ausente: {name}/{column}")

            if frame.schema[column].dataType != expected_type:
                raise ValueError(f"Tipo de procedencia incompatible: {name}/{column}")

        invalid = (
            ~F.col("gold_processing_run_id").eqNullSafe(F.lit(run_id))
            | ~F.col("gold_processed_at").eqNullSafe(F.lit(processed_at_utc))
        )
        invalid_count = frame.filter(invalid).count()

        check = {
            "table": name,
            "rule": "shared_gold_provenance",
            "invalid_rows": invalid_count,
            "passed": invalid_count == 0,
        }
        checks.append(check)

        if not check["passed"]:
            raise ValueError(f"Procedencia Gold incompatible: {check}")

    return {"passed": True, "checks": checks}


def reconcile_sales_lines(inputs, tables):
    """Compara cada línea Gold con su contexto e importes originales Silver."""
    from pyspark.sql import functions as F

    spark = tables["fact_sales"].sparkSession
    if spark.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La reconciliación requiere una sesión UTC.")

    # Calculamos la referencia directamente desde Silver.
    expected = (
        inputs["order_items"]
        .select(
            "order_id",
            "line_number",
            "product_id",
            "quantity",
            F.col("unit_price").alias("unit_price_pen"),
            F.col("discount_amount")
            .cast("decimal(28,2)")
            .alias("discount_amount_pen"),
        )
        .join(
            inputs["orders"].select(
                "order_id",
                "customer_id",
                F.col("order_date").alias("order_date_utc"),
                "currency_code",
                "status",
            ),
            on="order_id",
            how="inner",
        )
        .withColumn(
            "business_date",
            F.to_date(
                F.from_utc_timestamp("order_date_utc", "America/Lima")
            ),
        )
        .withColumn(
            "gross_amount_pen",
            (F.col("quantity") * F.col("unit_price_pen"))
            .cast("decimal(28,2)"),
        )
        .withColumn(
            "net_amount_pen",
            (F.col("gross_amount_pen") - F.col("discount_amount_pen"))
            .cast("decimal(28,2)"),
        )
    )

    # Recuperamos el contexto usando las relaciones persistidas en Gold.
    actual = (
        tables["fact_sales"]
        .join(
            tables["dim_product"].select("product_key", "product_id"),
            on="product_key",
            how="left",
        )
        .join(
            tables["dim_customer"].select("customer_key", "customer_id"),
            on="customer_key",
            how="left",
        )
        .join(
            tables["dim_date"].select(
                "date_key",
                F.col("full_date").alias("business_date"),
            ),
            on="date_key",
            how="left",
        )
        .join(
            tables["dim_order_status"].select("order_status_key", "status"),
            on="order_status_key",
            how="left",
        )
        .select(*expected.columns)
    )

    source_count = inputs["order_items"].count()
    expected_count = expected.count()
    actual_count = actual.count()

    if expected_count != source_count:
        raise ValueError(
            "La unión de referencia Silver perdió o multiplicó líneas."
        )

    missing_or_different = expected.exceptAll(actual).count()
    extra_or_different = actual.exceptAll(expected).count()

    result = {
        "source_line_count": source_count,
        "gold_line_count": actual_count,
        "missing_or_different_rows": missing_or_different,
        "extra_or_different_rows": extra_or_different,
        "passed": (
            actual_count == source_count
            and missing_or_different == 0
            and extra_or_different == 0
        ),
    }

    if not result["passed"]:
        raise ValueError(f"Reconciliación de líneas incompatible: {result}")

    return result


def validate_sales_exchange_rates(inputs, tables):
    """Contrasta las tasas persistidas con una selección independiente."""
    from datetime import timedelta

    from pyspark.sql import functions as F
    from pyspark.sql import types as T

    columns = (
        "series_code", "observation_date",
        "rate_pen_per_usd", "available", "raw_value",
    )
    silver_rates = inputs["exchange_rates"].select(*columns)
    gold_rates = tables["ref_exchange_rates"].select(*columns)

    if (
        silver_rates.exceptAll(gold_rates).limit(1).count()
        or gold_rates.exceptAll(silver_rates).limit(1).count()
    ):
        raise ValueError("La referencia cambiaria Gold difiere de Silver.")

    observations = silver_rates.collect()
    seen = set()
    available = []

    for row in observations:
        key = (row["series_code"], row["observation_date"])
        if key in seen:
            raise ValueError("Observación Silver duplicada.")
        seen.add(key)

        if (
            row["series_code"] != "PD04638PD"
            or row["observation_date"] is None
            or row["raw_value"] is None
        ):
            raise ValueError("Observación Silver incompatible.")

        rate = row["rate_pen_per_usd"]
        if row["available"] is True:
            if rate is None or rate <= 0:
                raise ValueError("Tasa Silver disponible inválida.")
            available.append(row)
        elif row["available"] is not False or rate is not None:
            raise ValueError("Disponibilidad Silver incompatible.")

    available.sort(key=lambda row: row["observation_date"])

    sales = tables["fact_sales"].join(
        tables["dim_date"].select(
            "date_key",
            F.col("full_date").alias("business_date"),
        ),
        on="date_key",
        how="left",
    )

    if sales.filter("business_date IS NULL").limit(1).count():
        raise ValueError("Venta sin fecha comercial dimensional.")

    expected_records = []
    for row in sales.select("business_date").distinct().collect():
        business_date = row["business_date"]
        candidates = [
            rate for rate in available
            if business_date - timedelta(days=7)
            <= rate["observation_date"] <= business_date
        ]
        selected = candidates[-1] if candidates else None
        expected_records.append((
            business_date,
            selected["series_code"] if selected else None,
            selected["observation_date"] if selected else None,
            selected["rate_pen_per_usd"] if selected else None,
            selected is not None,
        ))

    schema = T.StructType([
        T.StructField("business_date", T.DateType()),
        T.StructField("expected_series", T.StringType()),
        T.StructField("expected_date", T.DateType()),
        T.StructField("expected_rate", T.DecimalType(20, 14)),
        T.StructField("expected_available", T.BooleanType()),
    ])
    expected = sales.sparkSession.createDataFrame(
        expected_records, schema
    )
    compared = sales.join(expected, on="business_date", how="left")

    invalid = F.lit(False)
    for actual, reference in (
        ("exchange_rate_series_code", "expected_series"),
        ("exchange_rate_date", "expected_date"),
        ("rate_pen_per_usd", "expected_rate"),
        ("conversion_available", "expected_available"),
    ):
        invalid = invalid | ~F.col(actual).eqNullSafe(F.col(reference))

    invalid_count = compared.filter(invalid).count()
    if invalid_count:
        raise ValueError(
            f"Selección cambiaria incompatible: {invalid_count} líneas."
        )

    return {
        "passed": True,
        "reference_matches_silver": True,
        "invalid_rate_rows": invalid_count,
        "business_dates_checked": len(expected_records),
    }


def validate_sales_usd(tables):
    """Contrasta los importes USD con redondeo exacto independiente."""
    from decimal import Decimal, localcontext
    from fractions import Fraction

    from pyspark.sql import types as T

    fact = tables["fact_sales"]
    usd_columns = (
        "gross_amount_usd",
        "discount_amount_usd",
        "net_amount_usd",
    )
    expected_types = (
        ("gross_amount_pen", T.DecimalType(28, 2)),
        ("discount_amount_pen", T.DecimalType(28, 2)),
        ("rate_pen_per_usd", T.DecimalType(20, 14)),
        ("conversion_available", T.BooleanType()),
        *[(column, T.DecimalType(28, 2)) for column in usd_columns],
    )
    for column, expected_type in expected_types:
        if fact.schema[column].dataType != expected_type:
            raise ValueError(f"Tipo incompatible en validación USD: {column}")

    def rounded_cents(amount, rate):
        cents = Fraction(amount) * 100 / Fraction(rate)
        integer, remainder = divmod(cents.numerator, cents.denominator)
        return integer + int(2 * remainder >= cents.denominator)

    checked = 0
    converted = 0
    unavailable = 0
    invalid = 0

    columns = (
        "gross_amount_pen",
        "discount_amount_pen",
        "rate_pen_per_usd",
        "conversion_available",
        *usd_columns,
    )

    with localcontext() as context:
        context.prec = 80

        for row in fact.select(*columns).toLocalIterator():
            checked += 1
            actual = tuple(row[column] for column in usd_columns)
            available = row["conversion_available"]
            rate = row["rate_pen_per_usd"]

            if available is False:
                unavailable += 1
                if rate is not None or any(value is not None for value in actual):
                    invalid += 1
                continue

            if available is not True or rate is None or rate <= 0:
                invalid += 1
                continue

            gross = row["gross_amount_pen"]
            discount = row["discount_amount_pen"]
            if (
                gross is None
                or discount is None
                or gross < 0
                or discount < 0
                or discount > gross
            ):
                invalid += 1
                continue

            converted += 1
            gross_usd = Decimal(rounded_cents(gross, rate)).scaleb(-2)
            discount_usd = Decimal(rounded_cents(discount, rate)).scaleb(-2)
            expected = (
                gross_usd,
                discount_usd,
                gross_usd - discount_usd,
            )

            if (
                any(abs(value) >= Decimal("1e26") for value in expected)
                or actual != expected
            ):
                invalid += 1

    result = {
        "checked_rows": checked,
        "converted_rows": converted,
        "unavailable_rows": unavailable,
        "invalid_usd_rows": invalid,
        "passed": invalid == 0,
    }
    if not result["passed"]:
        raise ValueError(f"Importes USD persistidos incompatibles: {result}")

    return result


def reconcile_product_catalog(inputs, tables):
    """Contrasta asociaciones y atributos del catálogo Gold contra Silver."""
    from pyspark.sql import functions as F

    associations = inputs["product_external_mapping"].select(
        "source_system",
        "external_product_id",
        "product_id",
        "mapping_type",
        "mapping_note",
    )

    local = (
        inputs["products"]
        .join(
            inputs["categories"].select("category_id", "category_name"),
            on="category_id",
            how="inner",
        )
        .select(
            "product_id",
            F.col("sku").alias("local_sku"),
            F.col("product_name").alias("local_product_name"),
            F.col("brand").alias("local_brand"),
            F.col("category_name").alias("local_category_name"),
            F.col("list_price").alias("local_list_price_pen"),
        )
    )

    external = inputs["dummyjson_products"].select(
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

    expected = (
        associations
        .join(local, on="product_id", how="inner")
        .join(
            external,
            on=["source_system", "external_product_id"],
            how="inner",
        )
    )
    actual = tables["product_catalog_mapping"].select(*expected.columns)

    source_count = associations.count()
    if expected.count() != source_count:
        raise ValueError(
            "La referencia de catálogos perdió o multiplicó asociaciones."
        )

    if [
        (field.name, field.dataType) for field in actual.schema
    ] != [
        (field.name, field.dataType) for field in expected.schema
    ]:
        raise ValueError("Tipos de atributos del catálogo incompatibles.")

    missing_or_different = expected.exceptAll(actual).count()
    extra_or_different = actual.exceptAll(expected).count()

    result = {
        "source_association_count": source_count,
        "gold_association_count": actual.count(),
        "missing_or_different_rows": missing_or_different,
        "extra_or_different_rows": extra_or_different,
        "passed": (
            missing_or_different == 0
            and extra_or_different == 0
        ),
    }
    if not result["passed"]:
        raise ValueError(f"Catálogo Gold diferente de Silver: {result}")

    return result


def validate_gold_model(inputs, tables, report):
    """Ejecuta los controles del modelo Gold persistido."""
    results = {}

    results["relationships"] = validate_gold_relationships(tables)
    results["provenance"] = validate_gold_provenance(tables, report)
    results["sales_lines"] = reconcile_sales_lines(inputs, tables)
    results["exchange_rates"] = validate_sales_exchange_rates(inputs, tables)
    results["sales_usd"] = validate_sales_usd(tables)
    results["product_catalog"] = reconcile_product_catalog(inputs, tables)

    if not all(result["passed"] for result in results.values()):
        raise ValueError("El modelo Gold no superó todos los controles.")

    return {
        "passed": True,
        "gold_processing_run_id": report["gold_processing_run_id"],
        "results": results,
    }
