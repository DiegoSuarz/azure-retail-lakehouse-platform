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


def build_product_dimension(products, categories):
    """Construye la dimensión inicial de productos con su categoría."""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    for frame, key in (
        (products, "product_id"),
        (categories, "category_id"),
    ):
        if frame.filter(
            F.col(key).isNull() | (F.col(key) <= 0)
        ).limit(1).count():
            raise ValueError(f"Clave nula o no positiva: {key}")

        if (
            frame.groupBy(key)
            .count()
            .filter(F.col("count") > 1)
            .limit(1)
            .count()
        ):
            raise ValueError(f"Clave duplicada: {key}")

    if products.filter(
        F.col("category_id").isNull()
    ).limit(1).count():
        raise ValueError("Existe un producto sin category_id.")

    missing = products.join(
        categories.select("category_id"),
        on="category_id",
        how="left_anti",
    )
    if missing.limit(1).count():
        raise ValueError("Existen productos sin categoría válida.")

    joined = (
        products.select(
            "product_id",
            "category_id",
            "sku",
            "product_name",
            "brand",
            "list_price",
            "is_active",
        )
        .join(
            categories.select("category_id", "category_name"),
            on="category_id",
            how="inner",
        )
    )

    return (
        joined
        .withColumn(
            "product_key",
            F.row_number()
            .over(Window.orderBy("product_id"))
            .cast("long"),
        )
        .select(
            "product_key",
            "product_id",
            "sku",
            "product_name",
            "brand",
            "category_id",
            "category_name",
            "list_price",
            "is_active",
        )
    )


def build_customer_dimension(customers):
    """Construye la dimensión inicial de clientes."""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    if customers.filter(
        F.col("customer_id").isNull() | (F.col("customer_id") <= 0)
    ).limit(1).count():
        raise ValueError("Clave nula o no positiva: customer_id")

    if (
        customers.groupBy("customer_id")
        .count()
        .filter(F.col("count") > 1)
        .limit(1)
        .count()
    ):
        raise ValueError("Clave duplicada: customer_id")

    return (
        customers
        .withColumn(
            "customer_key",
            F.row_number()
            .over(Window.orderBy("customer_id"))
            .cast("long"),
        )
        .select(
            "customer_key",
            "customer_id",
            "first_name",
            "last_name",
            "city",
            "region",
            "is_active",
        )
    )


def add_order_business_date(orders):
    """Añade el día comercial en Lima a pedidos con order_date en UTC."""
    from pyspark.sql import functions as F

    if orders.sparkSession.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La sesión Spark debe utilizar UTC.")

    if not isinstance(orders.schema["order_date"].dataType, T.TimestampType):
        raise ValueError("order_date debe ser de tipo timestamp.")

    if orders.filter(
        F.col("order_date").isNull()
    ).limit(1).count():
        raise ValueError("Existe un pedido sin order_date.")

    return orders.withColumn(
        "business_date",
        F.to_date(
            F.from_utc_timestamp(
                F.col("order_date"),
                "America/Lima",
            )
        ),
    )
