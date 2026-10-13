"""Reglas de tipos y valores para pedidos y líneas incrementales."""

import re
from datetime import datetime, timezone
from decimal import Decimal

CUTOFF = datetime(2026, 10, 1, tzinfo=timezone.utc)
STATUSES = {"pending", "confirmed", "cancelled"}


def issue(errors, code, field, message):
    errors.append({"code": code, "field": field, "message": message})


def integer(row, field, errors, positive_code):
    raw = row.get(field)
    if not isinstance(raw, str) or not re.fullmatch(r"-?\d+", raw):
        issue(errors, "DQ005", field, "Se esperaba un entero")
        return None
    value = int(raw)
    if not -(2**31) <= value <= 2**31 - 1:
        issue(errors, "DQ005", field, "Valor fuera del rango SQL int")
        return None
    if value <= 0:
        issue(errors, positive_code, field, "El valor debe ser mayor que cero")
    return value


def amount(row, field, errors):
    raw = row.get(field)
    if not isinstance(raw, str) or not re.fullmatch(r"-?[0-9]+\.[0-9]{2}", raw):
        issue(errors, "DQ005", field, "Importe requerido con dos decimales")
        return None
    value = Decimal(raw)
    if abs(value) >= Decimal("10000000000000000"):
        issue(errors, "DQ005", field, "Importe fuera del rango decimal(18,2)")
        return None
    return value


def timestamp(row, field, errors):
    raw = row.get(field)
    if not isinstance(raw, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", raw
    ):
        issue(errors, "DQ005", field, "Fecha requerida en UTC con milisegundos")
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        issue(errors, "DQ005", field, "Fecha no válida")
        return None


def check_dates(values, errors):
    created = values.get("created_at")
    updated = values.get("updated_at")
    if created is not None and updated is not None and updated < created:
        issue(errors, "DQ009", "updated_at", "Anterior a created_at")


def parse_order(row):
    errors = []
    values = {
        "order_id": integer(row, "order_id", errors, "DQ006"),
        "customer_id": integer(row, "customer_id", errors, "DQ006"),
        "order_date": timestamp(row, "order_date", errors),
        "created_at": timestamp(row, "created_at", errors),
        "updated_at": timestamp(row, "updated_at", errors),
        "status": row.get("status"),
        "currency_code": row.get("currency_code"),
    }
    if values["status"] not in STATUSES:
        issue(errors, "DQ005", "status", "Estado no admitido")
    if values["currency_code"] != "PEN":
        issue(errors, "DQ008", "currency_code", "Moneda distinta de PEN")
    check_dates(values, errors)
    if values["created_at"] is not None and values["created_at"] < CUTOFF:
        issue(errors, "DQ009", "created_at", "Pedido nuevo anterior al corte")
    return values, errors


def parse_item(row):
    errors = []
    values = {
        field: integer(row, field, errors, "DQ006")
        for field in ("order_id", "line_number", "product_id")
    }
    values["quantity"] = integer(row, "quantity", errors, "DQ008")
    for field in ("unit_price", "discount_amount"):
        values[field] = amount(row, field, errors)
    for field in ("created_at", "updated_at"):
        values[field] = timestamp(row, field, errors)

    price = values["unit_price"]
    discount = values["discount_amount"]
    quantity = values["quantity"]

    if price is not None and price <= 0:
        issue(errors, "DQ008", "unit_price", "Precio debe ser mayor que cero")
    if discount is not None and discount < 0:
        issue(errors, "DQ008", "discount_amount", "Descuento negativo")
    if (
        quantity is not None and quantity > 0
        and price is not None and price > 0
        and discount is not None
        and discount > quantity * price
    ):
        issue(
            errors, "DQ008", "discount_amount",
            "Descuento superior al importe bruto de la línea",
        )
    check_dates(values, errors)
    return values, errors


def check_customer(values, customer_ids, errors):
    identifier = values["customer_id"]
    if identifier is not None and identifier > 0 and identifier not in customer_ids:
        issue(
            errors, "DQ007", "customer_id",
            "Cliente inexistente en la referencia aceptada",
        )


def check_product(values, product_ids, errors):
    identifier = values["product_id"]
    if identifier is not None and identifier > 0 and identifier not in product_ids:
        issue(
            errors, "DQ007", "product_id",
            "Producto inexistente en la referencia aceptada",
        )


def check_item_parent(values, parent, errors):
    if parent is None:
        issue(
            errors, "DQ007", "order_id",
            "La línea no pertenece a un pedido incluido en el lote",
        )
        return
    created = values["created_at"]
    parent_created = parent["created_at"]
    if created is not None and parent_created is not None and created < parent_created:
        issue(
            errors, "DQ009", "created_at",
            "La línea fue creada antes que su pedido",
        )
