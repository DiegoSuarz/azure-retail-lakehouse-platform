"""Esquemas de lectura de la carga inicial de SQL Server."""

from pyspark.sql import types as T


CATEGORIES_SCHEMA = T.StructType([
    T.StructField("category_id", T.IntegerType(), nullable=False),
    T.StructField("category_name", T.StringType(), nullable=False),
    T.StructField("created_at", T.TimestampType(), nullable=False),
    T.StructField("updated_at", T.TimestampType(), nullable=False),
])


PRODUCTS_SCHEMA = T.StructType([
    T.StructField("product_id", T.IntegerType(), nullable=False),
    T.StructField("category_id", T.IntegerType(), nullable=False),
    T.StructField("sku", T.StringType(), nullable=False),
    T.StructField("product_name", T.StringType(), nullable=False),
    T.StructField("brand", T.StringType(), nullable=False),
    T.StructField("list_price", T.DecimalType(18, 2), nullable=False),
    T.StructField("is_active", T.BooleanType(), nullable=False),
    T.StructField("created_at", T.TimestampType(), nullable=False),
    T.StructField("updated_at", T.TimestampType(), nullable=False),
])


CUSTOMERS_SCHEMA = T.StructType([
    T.StructField("customer_id", T.IntegerType(), nullable=False),
    T.StructField("first_name", T.StringType(), nullable=False),
    T.StructField("last_name", T.StringType(), nullable=False),
    T.StructField("email", T.StringType(), nullable=False),
    T.StructField("city", T.StringType(), nullable=False),
    T.StructField("region", T.StringType(), nullable=False),
    T.StructField("is_active", T.BooleanType(), nullable=False),
    T.StructField("created_at", T.TimestampType(), nullable=False),
    T.StructField("updated_at", T.TimestampType(), nullable=False),
])


ORDERS_SCHEMA = T.StructType([
    T.StructField("order_id", T.IntegerType(), nullable=False),
    T.StructField("customer_id", T.IntegerType(), nullable=False),
    T.StructField("order_date", T.TimestampType(), nullable=False),
    T.StructField("status", T.StringType(), nullable=False),
    T.StructField("currency_code", T.StringType(), nullable=False),
    T.StructField("created_at", T.TimestampType(), nullable=False),
    T.StructField("updated_at", T.TimestampType(), nullable=False),
])


ORDER_ITEMS_SCHEMA = T.StructType([
    T.StructField("order_id", T.IntegerType(), nullable=False),
    T.StructField("line_number", T.IntegerType(), nullable=False),
    T.StructField("product_id", T.IntegerType(), nullable=False),
    T.StructField("quantity", T.IntegerType(), nullable=False),
    T.StructField("unit_price", T.DecimalType(18, 2), nullable=False),
    T.StructField("discount_amount", T.DecimalType(18, 2), nullable=False),
    T.StructField("created_at", T.TimestampType(), nullable=False),
    T.StructField("updated_at", T.TimestampType(), nullable=False),
])


SQLSERVER_SCHEMAS = {
    "categories": CATEGORIES_SCHEMA,
    "products": PRODUCTS_SCHEMA,
    "customers": CUSTOMERS_SCHEMA,
    "orders": ORDERS_SCHEMA,
    "order_items": ORDER_ITEMS_SCHEMA,
}
