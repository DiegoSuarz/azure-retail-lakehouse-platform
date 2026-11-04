"""Reglas de comparación para dimensiones SCD de productos y clientes."""


SCD_RULES = {
    "dim_product": {
        "business_key": "product_id",
        "version_key": "product_key",
        "stable": ("sku",),
        "type1": ("product_name", "brand"),
        "type2": (
            "category_id",
            "category_name",
            "list_price",
            "is_active",
        ),
    },
    "dim_customer": {
        "business_key": "customer_id",
        "version_key": "customer_key",
        "stable": (),
        "type1": ("first_name", "last_name"),
        "type2": ("city", "region", "is_active"),
    },
}
