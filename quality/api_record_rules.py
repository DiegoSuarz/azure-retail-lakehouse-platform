"""Reglas de registros de API conforme al contrato interno."""

from decimal import Decimal, InvalidOperation

CATEGORIES = {"laptops", "smartphones", "tablets", "mobile-accessories"}
OPTIONAL_TEXT = {
    "description": "external_description",
    "brand": "external_brand",
    "sku": "external_sku",
    "thumbnail": "thumbnail_url",
}


def issue(errors, code, field, message):
    errors.append({"code": code, "field": field, "message": message})


def evaluate_product(product, category):
    errors = []
    if not isinstance(product, dict):
        issue(errors, "DQ014", "record", "El producto no es un objeto")
        return {"status": "rejected", "errors": errors, "values": None}

    identifier = product.get("id")
    if type(identifier) is not int or identifier <= 0:
        issue(errors, "DQ014", "id", "Identificador no entero positivo")

    title = product.get("title")
    if not isinstance(title, str) or not title.strip():
        issue(errors, "DQ014", "title", "Título obligatorio ausente o inválido")

    if (
        category not in CATEGORIES
        or product.get("category") != category
    ):
        issue(errors, "DQ014", "category", "Categoría incompatible")

    numbers = {}
    for field in ("price", "rating"):
        value = product.get(field)
        if not (type(value) is int or isinstance(value, Decimal)):
            issue(errors, "DQ014", field, "Valor numérico incompatible")
            continue

        number = Decimal(value)
        if not number.is_finite():
            issue(errors, "DQ014", field, "Valor numérico no finito")
            continue
        if field == "rating" and not 0 <= number <= 5:
            issue(errors, "DQ014", field, "Rating fuera de 0 a 5")
            continue
        numbers[field] = number

    stock = product.get("stock")
    if type(stock) is not int or stock < 0:
        issue(errors, "DQ014", "stock", "Stock no entero no negativo")

    optional = {}
    for source, target in OPTIONAL_TEXT.items():
        value = product.get(source)
        if value is not None and not isinstance(value, str):
            issue(errors, "DQ014", source, "Campo opcional no textual")
        optional[target] = value

    values = None
    if not errors:
        values = {
            "source_system": "dummyjson",
            "external_product_id": identifier,
            "external_product_name": title,
            "external_category": category,
            "external_price": numbers["price"],
            "external_rating": numbers["rating"],
            "external_stock": stock,
            "external_currency_code": None,
            **optional,
        }

    return {
        "status": "rejected" if errors else "accepted",
        "errors": errors,
        "values": values,
    }


def evaluate_rate(raw):
    errors = []
    if not isinstance(raw, str):
        issue(errors, "DQ015", "values", "La tasa debe ser textual")
        return {
            "status": "rejected", "errors": errors,
            "available": None, "rate": None, "raw_value": raw,
        }

    try:
        rate = Decimal(raw.strip())
    except InvalidOperation:
        rate = None

    available = rate is not None and rate.is_finite()
    if not available:
        rate = None
    elif rate <= 0:
        issue(errors, "DQ015", "values", "La tasa numérica debe ser positiva")

    return {
        "status": "rejected" if errors else "accepted",
        "errors": errors,
        "available": available,
        "rate": rate,
        "raw_value": raw,
    }
