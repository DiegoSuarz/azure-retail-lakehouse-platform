"""Valida los escenarios de reproceso y orden sin modificar las fuentes."""

import hashlib
import argparse
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "quality"))
from validate_batch_transport import read_batch as read_transport_batch

ROOT = Path("data/incremental")


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_batch(relative):
    directory = ROOT / relative
    expected_files = (
        {"orders.csv", "order_items.csv", "changes.jsonl"}
        if directory.name == "batch_001" else {"changes.jsonl"}
    )
    batch_id, payloads, _ = read_transport_batch(
        directory, expected_files=expected_files
    )
    events = [
        json.loads(line)
        for line in payloads["changes.jsonl"].decode("utf-8").splitlines()
        if line.strip()
    ]
    reference = {
        "batch_id": batch_id,
        "files": {
            filename: hashlib.sha256(payload).hexdigest()
            for filename, payload in payloads.items()
        },
    }
    return reference, events


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT)
    ROOT = parser.parse_args().data_dir
    expected = json.loads(
        (ROOT / "ordering-expectations.json").read_text(encoding="utf-8")
    )
    require(
        expected["covered_scenarios"] == ["S08", "S09", "S10", "S11", "S12"],
        "Cobertura declarada",
    )
    deliveries = [
        "functional/batch_001",
        "functional/batch_001",
        "functional/batch_002",
        "functional/batch_003",
        "functional/batch_004",
    ]
    require(expected["delivery_order"] == deliveries, "Orden de entrega")

    batches = {}
    for relative in dict.fromkeys(deliveries):
        batches[relative] = read_batch(relative)

    customer_key = expected["customer_key"]
    require(set(customer_key) == {"customer_id"}, "Clave de cliente")

    def customer_events(relative):
        return [
            event for event in batches[relative][1]
            if event["entity"] == "customers"
            and event["business_key"] == customer_key
        ]

    first, = customer_events("functional/batch_001")
    repeated_first, third = customer_events("functional/batch_002")
    second, = customer_events("functional/batch_003")
    repeated_second, = customer_events("functional/batch_004")

    require(first == repeated_first, "El duplicado de secuencia 1 difiere")
    require(second == repeated_second, "El duplicado de secuencia 2 difiere")
    require(
        [event["event_sequence"] for event in (first, second, third)] == [1, 2, 3],
        "Secuencias del cliente",
    )
    require(
        len({event["event_id"] for event in (first, second, third)}) == 3,
        "Identificadores de eventos únicos",
    )
    require(second["event_id"] == expected["sequence_2_event_id"], "ID secuencia 2")
    require(third["event_id"] == expected["sequence_3_event_id"], "ID secuencia 3")
    require(second["event_time"] == third["event_time"], "Empate temporal")
    require(date(first["event_time"]) < date(second["event_time"]), "Orden temporal")

    checkpoints = {
        checkpoint["after_delivery"]: checkpoint
        for checkpoint in expected["checkpoints"]
    }
    require(set(checkpoints) == {2, 3, 4, 5}, "Puntos de control")

    seen_batches = {}
    seen_events = {}
    sequence_ids = {}
    pending = {}
    current_sequence = 0
    state = None

    for delivery_number, relative in enumerate(deliveries, 1):
        batch_reference, events = batches[relative]
        batch_id = batch_reference["batch_id"]
        applied = 0

        if batch_id in seen_batches:
            require(seen_batches[batch_id] == batch_reference, "Conflicto de lote")
        else:
            seen_batches[batch_id] = batch_reference
            for event in events:
                if (
                    event["entity"] != "customers"
                    or event["business_key"] != customer_key
                ):
                    continue

                require(event["schema_version"] == 1, "Versión de evento")
                require(event["operation"] == "update", "Operación de evento")
                require(
                    event["after"]["customer_id"] == customer_key["customer_id"],
                    "Clave de imagen",
                )
                require(
                    event["after"]["updated_at"] == event["event_time"],
                    "Fecha de imagen",
                )

                event_id = event["event_id"]
                if event_id in seen_events:
                    require(seen_events[event_id] == event, "Conflicto de event_id")
                    continue

                sequence = event["event_sequence"]
                require(
                    type(sequence) is int and sequence > 0,
                    "Secuencia inválida",
                )
                require(sequence not in sequence_ids, "Conflicto de secuencia")
                require(sequence > current_sequence, "Evento anterior desconocido")

                seen_events[event_id] = event
                sequence_ids[sequence] = event_id
                pending[sequence] = event

                while current_sequence + 1 in pending:
                    next_event = pending.pop(current_sequence + 1)
                    after = next_event["after"]
                    if state is not None:
                        require(
                            date(next_event["event_time"]) >= date(state["updated_at"]),
                            "Retroceso temporal",
                        )
                        require(
                            after["created_at"] == state["created_at"],
                            "created_at modificado",
                        )
                    state = after.copy()
                    current_sequence += 1
                    applied += 1

        if delivery_number in checkpoints:
            checkpoint = checkpoints[delivery_number]
            require(
                applied == checkpoint["additional_applied_events"],
                f"Eventos aplicados en entrega {delivery_number}",
            )
            if "customer_sequence" in checkpoint:
                require(
                    current_sequence == checkpoint["customer_sequence"],
                    f"Secuencia en entrega {delivery_number}",
                )
            if "pending_event_ids" in checkpoint:
                require(
                    sorted(event["event_id"] for event in pending.values())
                    == sorted(checkpoint["pending_event_ids"]),
                    f"Pendientes en entrega {delivery_number}",
                )

    require(not pending, "Quedaron eventos pendientes")
    require(state == expected["expected_final_customer"], "Estado final")
    require(len(seen_events) == 3, "Conteo de eventos únicos del cliente")

    for relative in deliveries[2:]:
        batch_reference, events = batches[relative]
        require(set(batch_reference["files"]) == {"changes.jsonl"}, "Archivo inesperado")
        require(
            all(
                event["entity"] == "customers"
                and event["business_key"] == customer_key
                for event in events
            ),
            "Los lotes adicionales deben afectar solo al cliente seleccionado",
        )
    require(
        expected["sales_controls_unchanged_from_batch_001"] is True,
        "Expectativa de ventas",
    )

    print("PASS: estructura de lotes y referencias de contenido calculadas.")
    print("PASS: reproceso del lote y duplicados exactos.")
    print("PASS: secuencia 3 pendiente hasta recibir secuencia 2.")
    print("PASS: empate temporal resuelto por event_sequence.")
    print("PASS: evento repetido anterior no modifica el estado final.")
    print("ALCANCE: simulación local S08–S12; procesamiento cloud pendiente.")


if __name__ == "__main__":
    main()
