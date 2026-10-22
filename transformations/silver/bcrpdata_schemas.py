"""Esquemas de lectura y tipo decimal de BCRPData."""

from pyspark.sql import types as T


RATE_TYPE = T.DecimalType(20, 14)


PERIOD_SCHEMA = T.StructType([
    T.StructField("name", T.StringType(), nullable=True),
    T.StructField(
        "values",
        T.ArrayType(T.StringType()),
        nullable=True,
    ),
])


RESPONSE_SCHEMA = T.StructType([
    T.StructField(
        "periods",
        T.ArrayType(PERIOD_SCHEMA),
        nullable=True,
    ),
])
