"""Lectura y normalización de observaciones de BCRPData."""

from pyspark.sql import functions as F

from transformations.silver.bcrpdata_schemas import RESPONSE_SCHEMA


def read_bcrpdata_observations(spark, source_path):
    """Extrae las observaciones originales de una respuesta de una serie."""
    response = (
        spark.read
        .schema(RESPONSE_SCHEMA)
        .option("multiLine", True)
        .option("mode", "FAILFAST")
        .json(source_path)
        .withColumn("source_file", F.col("_metadata.file_path"))
    )

    if response.filter(F.col("periods").isNull()).limit(1).count():
        raise ValueError("Respuesta sin lista de observaciones.")

    periods = response.select(
        "source_file",
        F.explode("periods").alias("period"),
    )

    invalid_values = (
        F.col("period.values").isNull()
        | (F.size(F.col("period.values")) != 1)
    )
    if periods.filter(invalid_values).limit(1).count():
        raise ValueError("Cada observación debe contener un único valor.")

    return periods.select(
        F.col("period.name").alias("observation_date_text"),
        F.col("period.values").getItem(0).alias("raw_value"),
        F.col("source_file"),
    )


def parse_observation_date(text, start_date, end_date):
    """Convierte una fecha BCRP dentro del intervalo solicitado."""
    from datetime import date

    months = {
        "ene": 1, "feb": 2, "mar": 3, "abr": 4,
        "may": 5, "jun": 6, "jul": 7, "ago": 8,
        "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    }

    day, month, year_text = text.strip().split(".")
    if len(year_text) not in (2, 4):
        raise ValueError(f"Año incompatible: {text}")

    years = [
        year for year in range(start_date.year, end_date.year + 1)
        if (
            year == int(year_text)
            if len(year_text) == 4
            else year % 100 == int(year_text)
        )
    ]
    if len(years) != 1:
        raise ValueError(f"Año ambiguo o fuera del intervalo: {text}")

    observed = date(years[0], months[month.lower()], int(day))
    if not start_date <= observed <= end_date:
        raise ValueError(f"Fecha fuera del intervalo: {text}")

    return observed


def parse_exchange_rate(raw_value):
    """Convierte una tasa sin redondear; devuelve None si no está disponible."""
    from decimal import Decimal, InvalidOperation, localcontext

    if not isinstance(raw_value, str):
        raise ValueError("La tasa original debe ser texto.")

    try:
        value = Decimal(raw_value.strip())
    except InvalidOperation:
        return None

    if not value.is_finite():
        return None

    if value <= 0:
        raise ValueError(f"La tasa debe ser positiva: {raw_value}")

    if value >= Decimal("1000000"):
        raise ValueError(f"Tasa fuera de decimal(20,14): {raw_value}")

    with localcontext() as context:
        context.prec = 38
        stored = value.quantize(Decimal("0.00000000000001"))

    if stored != value:
        raise ValueError(f"La tasa perdería precisión: {raw_value}")

    return stored


def normalize_bcrpdata_observations(
    observations,
    series_code,
    start_date,
    end_date,
    ingestion_run_id,
    processing_run_id,
    extracted_at,
    processed_at,
):
    """Convierte fechas y tasas, conservando su valor original y procedencia."""
    from pyspark.sql import types as T
    from transformations.silver.bcrpdata_schemas import RATE_TYPE

    date_parser = F.udf(
        lambda text: parse_observation_date(text, start_date, end_date),
        T.DateType(),
    )
    rate_parser = F.udf(parse_exchange_rate, RATE_TYPE)

    converted = (
        observations
        .withColumn(
            "observation_date",
            date_parser(F.col("observation_date_text")),
        )
        .withColumn(
            "rate_pen_per_usd",
            rate_parser(F.col("raw_value")),
        )
    )

    return converted.select(
        F.lit(series_code).alias("series_code"),
        F.col("observation_date"),
        F.col("rate_pen_per_usd"),
        F.col("rate_pen_per_usd").isNotNull().alias("available"),
        F.col("raw_value"),
        F.lit("bcrpdata").alias("source_system"),
        F.lit(ingestion_run_id).alias("ingestion_run_id"),
        F.lit(processing_run_id).alias("processing_run_id"),
        F.col("source_file"),
        F.lit(extracted_at).alias("extracted_at"),
        F.lit(processed_at).alias("processed_at"),
    )


def validate_bcrpdata_observations(observations, start_date, end_date):
    """Comprueba fechas, tasas, disponibilidad y unicidad por serie y día."""
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
        (F.col("source_system") == "bcrpdata")
        & (F.col("series_code") == "PD04638PD")
        & F.col("observation_date").between(start_date, end_date)
        & F.col("raw_value").isNotNull()
        & valid_rate
    )

    invalid_rows = observations.filter(
        ~F.coalesce(valid, F.lit(False))
    ).count()

    duplicate_groups = (
        observations
        .groupBy("series_code", "observation_date")
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
        raise ValueError(f"Observaciones BCRPData incompatibles: {result}")

    return result


def write_bcrpdata_delta(spark, observations, silver_root):
    """Escribe las tasas y verifica los tipos y valores recuperados."""
    target = f"{silver_root.rstrip('/')}/reference/exchange_rates"

    observations.write.format("delta").mode("error").save(target)

    recovered = (
        spark.read.format("delta")
        .load(target)
        .select(*observations.columns)
    )

    expected_types = [
        (field.name, field.dataType) for field in observations.schema
    ]
    actual_types = [
        (field.name, field.dataType) for field in recovered.schema
    ]
    if actual_types != expected_types:
        raise ValueError("BCRPData: tipos diferentes después de escribir")

    if (
        observations.exceptAll(recovered).count() != 0
        or recovered.exceptAll(observations).count() != 0
    ):
        raise ValueError("BCRPData: datos diferentes después de escribir")

    return {
        "entity": "exchange_rates",
        "path": target,
        "row_count": recovered.count(),
        "verified": True,
    }
