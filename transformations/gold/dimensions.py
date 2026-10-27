"""Construcción de las dimensiones iniciales de Gold."""

from pyspark.sql import types as T


def build_order_status_dimension(spark):
    """Crea los estados de pedido y su clasificación comercial."""
    schema = T.StructType([
        T.StructField("order_status_key", T.IntegerType(), nullable=False),
        T.StructField("status", T.StringType(), nullable=False),
        T.StructField("status_name", T.StringType(), nullable=False),
        T.StructField("counts_as_sale", T.BooleanType(), nullable=False),
    ])

    records = [
        (1, "pending", "Pendiente", False),
        (2, "confirmed", "Confirmado", True),
        (3, "cancelled", "Cancelado", False),
    ]

    return spark.createDataFrame(records, schema=schema)


def build_date_dimension(spark, start_year, end_year):
    """Construye un calendario de años completos."""
    from datetime import date, timedelta

    if (
        type(start_year) is not int
        or type(end_year) is not int
        or not 1 <= start_year <= end_year <= 9999
    ):
        raise ValueError("Se requieren años enteros válidos y ordenados.")

    months = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre",
        "Diciembre",
    )
    weekdays = (
        "Lunes", "Martes", "Miércoles", "Jueves",
        "Viernes", "Sábado", "Domingo",
    )

    schema = T.StructType([
        T.StructField("date_key", T.IntegerType(), nullable=False),
        T.StructField("full_date", T.DateType(), nullable=False),
        T.StructField("year", T.IntegerType(), nullable=False),
        T.StructField("quarter", T.IntegerType(), nullable=False),
        T.StructField("month_number", T.IntegerType(), nullable=False),
        T.StructField("month_name", T.StringType(), nullable=False),
        T.StructField("day_of_month", T.IntegerType(), nullable=False),
        T.StructField("day_of_week", T.IntegerType(), nullable=False),
        T.StructField("day_name", T.StringType(), nullable=False),
        T.StructField("is_weekend", T.BooleanType(), nullable=False),
    ])

    first = date(start_year, 1, 1)
    last = date(end_year, 12, 31)
    records = []

    for offset in range((last - first).days + 1):
        current = first + timedelta(days=offset)
        weekday = current.isoweekday()

        records.append((
            current.year * 10000 + current.month * 100 + current.day,
            current,
            current.year,
            (current.month - 1) // 3 + 1,
            current.month,
            months[current.month - 1],
            current.day,
            weekday,
            weekdays[weekday - 1],
            weekday >= 6,
        ))

    return spark.createDataFrame(records, schema=schema)
