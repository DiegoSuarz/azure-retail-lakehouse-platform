"""Esquema de lectura de productos conservados de DummyJSON."""

from pyspark.sql import types as T


PRODUCT_SCHEMA = T.StructType([
    T.StructField("id", T.IntegerType(), nullable=True),
    T.StructField("title", T.StringType(), nullable=True),
    T.StructField("category", T.StringType(), nullable=True),
    T.StructField("description", T.StringType(), nullable=True),
    T.StructField("brand", T.StringType(), nullable=True),
    T.StructField("sku", T.StringType(), nullable=True),
    T.StructField("price", T.DecimalType(18, 2), nullable=True),
    T.StructField("rating", T.DecimalType(3, 2), nullable=True),
    T.StructField("stock", T.IntegerType(), nullable=True),
    T.StructField("thumbnail", T.StringType(), nullable=True),
])


PAGE_SCHEMA = T.StructType([
    T.StructField(
        "products",
        T.ArrayType(PRODUCT_SCHEMA),
        nullable=True,
    ),
])
