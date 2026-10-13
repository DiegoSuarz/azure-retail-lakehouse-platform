"""Clasifica eventos de actualización contra una referencia explícita."""

import json
from uuid import UUID

from event_reference import KEYS
from record_rules import CUTOFF, STATUSES, amount, issue, timestamp

COLUMNS = {
    "customers": {
        "customer_id", "first_name", "last_name", "email", "city",
        "region", "is_active", "created_at", "updated_at",
    },
    "products": {
        "product_id", "category_id", "sku", "product_name", "brand",
        "list_price", "is_active", "created_at", "updated_at",
    },
    "orders": {
        "order_id", "customer_id", "order_date", "status",
        "currency_code", "created_at", "updated_at",
    },
}
TEXT_LIMITS = {
    "first_name": 100, "last_name": 100, "email": 254,
    "city": 100, "region": 100, "sku": 40,
    "product_name": 200, "brand": 100,
    "status": 20, "currency_code": 3,
}
TRANSITIONS = {
    ("pending", "confirmed"),
    ("pending", "cancelled"),
    ("confirmed", "cancelled"),
}


def canonical(event):
    return json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def evaluate_event(event, context):
    errors = []
    result = {
        "status": "rejected",
        "errors": errors,
        "event_id": None,
        "entity": None,
        "business_key": None,
        "reference_content_json": None,
    }
    if not isinstance(event, dict):
        issue(errors, "DQ005", None, "Evento debe ser un objeto JSON")
        return result

    entity = event.get("entity")
    result["entity"] = entity if isinstance(entity, str) else None
    result["event_id"] = event.get("event_id") if isinstance(event.get("event_id"), str) else None

    if type(event.get("schema_version")) is not int or event["schema_version"] != 1:
        issue(errors, "DQ005", "schema_version", "Versión incompatible")
    if event.get("operation") != "update":
        issue(errors, "DQ005", "operation", "Solo se admite update")
    if not isinstance(entity, str) or entity not in COLUMNS:
        issue(errors, "DQ005", "entity", "Entidad no admitida")
    try:
        UUID(event.get("event_id", ""))
    except (ValueError, TypeError, AttributeError):
        issue(errors, "DQ005", "event_id", "UUID inválido")

    sequence = event.get("event_sequence")
    if type(sequence) is not int or sequence <= 0:
        issue(errors, "DQ005", "event_sequence", "Secuencia entera positiva requerida")

    event_time = timestamp(event, "event_time", errors)
    if event_time is not None and event_time < CUTOFF:
        issue(errors, "DQ009", "event_time", "Evento anterior al corte")

    if errors:
        return result

    key_field = KEYS[entity]
    key = event.get("business_key")
    if not isinstance(key, dict) or set(key) != {key_field}:
        issue(errors, "DQ005", "business_key", "Clave de negocio incompatible")
        return result
    identifier = key[key_field]
    if type(identifier) is not int or not 0 < identifier <= 2**31 - 1:
        issue(errors, "DQ006", key_field, "Clave positiva SQL int requerida")
        return result
    result["business_key"] = dict(key)

    previous = context["event_history"].get(event["event_id"])
    if previous is not None:
        if canonical(previous) == canonical(event):
            result["status"] = "duplicate"
        else:
            result["status"] = "conflict"
            result["reference_content_json"] = canonical(previous)
            issue(errors, "DQ011", "event_id", "event_id existente con contenido diferente")
        return result

    sequence_key = (entity, identifier, sequence)
    previous_id = context["sequence_history"].get(sequence_key)
    if previous_id is not None:
        result["status"] = "conflict"
        result["reference_content_json"] = canonical(
            context["event_history"][previous_id]
        )
        issue(
            errors, "DQ011", "event_sequence",
            "Entidad, clave y secuencia ya registradas con otro event_id",
        )
        return result

    after = event.get("after")
    if not isinstance(after, dict) or set(after) != COLUMNS[entity]:
        issue(errors, "DQ012", "after", "Imagen completa incompatible")
        return result

    for field, value in after.items():
        if field.endswith("_id"):
            if type(value) is not int or not 0 < value <= 2**31 - 1:
                issue(errors, "DQ005", field, "Identificador positivo SQL int requerido")
        elif field == "is_active":
            if type(value) is not bool:
                issue(errors, "DQ005", field, "Se requiere booleano JSON")
        elif field in TEXT_LIMITS:
            if (
                not isinstance(value, str) or not value.strip()
                or len(value) > TEXT_LIMITS[field]
            ):
                issue(errors, "DQ005", field, "Texto obligatorio o longitud inválida")

    if after[key_field] != identifier:
        issue(errors, "DQ012", key_field, "Imagen y clave de negocio diferentes")

    created = timestamp(after, "created_at", errors)
    updated = timestamp(after, "updated_at", errors)
    if updated is not None and updated != event_time:
        issue(errors, "DQ009", "updated_at", "Debe coincidir con event_time")
    if created is not None and updated is not None and updated < created:
        issue(errors, "DQ009", "updated_at", "Anterior a created_at")

    if entity == "products":
        price = amount(after, "list_price", errors)
        if price is not None and price <= 0:
            issue(errors, "DQ008", "list_price", "Precio debe ser positivo")
        category_id = after["category_id"]
        if type(category_id) is int and category_id not in context["records"]["categories"]:
            issue(errors, "DQ007", "category_id", "Categoría inexistente")

    if entity == "orders":
        timestamp(after, "order_date", errors)
        if isinstance(after["status"], str) and after["status"] not in STATUSES:
            issue(errors, "DQ005", "status", "Estado no admitido")
        if after["currency_code"] != "PEN":
            issue(errors, "DQ008", "currency_code", "Moneda distinta de PEN")

    if errors:
        return result

    original = context["records"][entity].get(identifier)
    last_sequence = context["last_sequence"].get((entity, identifier), 0)

    if original is None:
        result["status"] = "pending"
        issue(errors, "DQ007", key_field, "Registro afectado todavía no disponible")
        return result
    result["reference_content_json"] = canonical(original)

    if sequence != last_sequence + 1:
        result["status"] = "pending"
        issue(
            errors, "DQ011", "event_sequence",
            "Falta una secuencia anterior o una referencia histórica completa",
        )
        return result

    stable = {key_field, "created_at"}
    if entity == "products":
        stable.add("sku")
    elif entity == "orders":
        stable.update({"customer_id", "order_date", "currency_code"})

    for field in sorted(stable):
        if after[field] != original[field]:
            issue(errors, "DQ012", field, "Atributo estable modificado")

    previous_time = timestamp(original, "updated_at", errors)
    if previous_time is not None:
        if last_sequence == 0 and event_time <= previous_time:
            issue(errors, "DQ009", "event_time", "Debe ser posterior a la versión inicial")
        elif last_sequence > 0 and event_time < previous_time:
            issue(errors, "DQ009", "event_time", "Evento anterior a la versión vigente")

    if entity == "customers":
        for other_id, customer in context["records"]["customers"].items():
            if other_id != identifier and customer["email"] == after["email"]:
                issue(errors, "DQ006", "email", "Correo ya utilizado por otro cliente")
                break

    if entity == "orders":
        if after["customer_id"] not in context["records"]["customers"]:
            issue(errors, "DQ007", "customer_id", "Cliente inexistente")
        if (original["status"], after["status"]) not in TRANSITIONS:
            issue(errors, "DQ013", "status", "Transición de pedido no permitida")

    result["status"] = "rejected" if errors else "accepted"
    return result
