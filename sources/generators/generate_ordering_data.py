"""Genera escenarios S08–S12 sobre el primer lote funcional."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from generate_incremental_data import make_event, write_json


def write_batch(root, batch_id, events):
    directory = root / "functional" / batch_id
    directory.mkdir(parents=True)
    path = directory / "changes.jsonl"
    path.write_text(
        "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/incremental")
    )
    args = parser.parse_args()
    root = args.output_dir
    first = root / "functional" / "batch_001"
    payload = (first / "changes.jsonl").read_bytes()
    events = [
        json.loads(line) for line in payload.decode("utf-8").splitlines()
        if line.strip()
    ]

    candidates = [
        event for event in events if event["entity"] == "customers"
    ]
    if len(candidates) != 1 or candidates[0]["event_sequence"] != 1:
        parser.error("Se esperaba un único cambio inicial de cliente.")

    targets = [
        root / "functional" / batch_id
        for batch_id in ("batch_002", "batch_003", "batch_004")
    ] + [root / "ordering-expectations.json"]
    if any(path.exists() for path in targets):
        parser.error("Ya existe una salida de estos escenarios.")

    first_event = candidates[0]
    second = make_event(
        "S10", "customers", first_event["after"],
        {"city": "Cusco", "region": "Cusco"}, 9, sequence=2,
    )
    third = make_event(
        "S11", "customers", second["after"],
        {"city": "Piura", "region": "Piura"}, 9, sequence=3,
    )

    write_batch(root, "batch_002", [deepcopy(first_event), third])
    write_batch(root, "batch_003", [second])
    write_batch(root, "batch_004", [deepcopy(second)])

    write_json(root / "ordering-expectations.json", {
        "schema_version": 1,
        "covered_scenarios": ["S08", "S09", "S10", "S11", "S12"],
        "delivery_order": [
            "functional/batch_001",
            "functional/batch_001",
            "functional/batch_002",
            "functional/batch_003",
            "functional/batch_004",
        ],
        "customer_key": first_event["business_key"],
        "sequence_2_event_id": second["event_id"],
        "sequence_3_event_id": third["event_id"],
        "checkpoints": [
            {
                "after_delivery": 2,
                "additional_applied_events": 0,
                "reason": "Reproceso del primer lote",
            },
            {
                "after_delivery": 3,
                "additional_applied_events": 0,
                "pending_event_ids": [third["event_id"]],
                "customer_sequence": 1,
            },
            {
                "after_delivery": 4,
                "additional_applied_events": 2,
                "pending_event_ids": [],
                "customer_sequence": 3,
            },
            {
                "after_delivery": 5,
                "additional_applied_events": 0,
                "customer_sequence": 3,
            },
        ],
        "expected_final_customer": third["after"],
        "sales_controls_unchanged_from_batch_001": True,
        "processing_verified": False,
    })

    print("GENERADO: batch_002, batch_003 y batch_004.")
    print("Secuencia de llegada del cliente: 1, repetida 1, 3, 2, repetida 2.")
    print("Estado final esperado: Piura / Piura, secuencia 3.")


if __name__ == "__main__":
    main()
