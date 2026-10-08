"""Comprueba las anomalías deliberadas de los escenarios S13–S20."""

import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path("data/incremental")
INITIAL = Path("data/initial")


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read_events(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main():
    expected_reasons = {
        "S13": "event_id_conflict",
        "S14": "entity_key_sequence_conflict",
        "S15": "invalid_status_transition",
        "S16": "missing_product_reference",
        "S17": "discount_exceeds_gross",
        "S18": "manifest_hash_mismatch",
        "S19": "existing_order_content_conflict",
        "S20": "stable_attribute_changed",
    }
    expectations = json.loads(
        (ROOT / "invalid-expectations.json").read_text(encoding="utf-8")
    )
    cases = expectations["cases"]
    require(expectations["schema_version"] == 1, "Versión de expectativas")
    require(len(cases) == 8, "Cantidad de casos")
    require(
        {case["scenario"] for case in cases} == set(expected_reasons),
        "Cobertura S13–S20",
    )

    orders = {
        int(row["order_id"]): row
        for row in read_csv(INITIAL / "orders.csv")
    }
    product_ids = {
        int(row["product_id"])
        for row in read_csv(INITIAL / "products.csv")
    }
    customer_ids = {
        int(row["customer_id"])
        for row in read_csv(INITIAL / "customers.csv")
    }
    first_events = read_events(
        ROOT / "functional" / "batch_001" / "changes.jsonl"
    )
    initial_customer_event = next(
        event for event in first_events if event["entity"] == "customers"
    )
    valid_transitions = {
        ("pending", "confirmed"),
        ("pending", "cancelled"),
        ("confirmed", "cancelled"),
    }

    for case in cases:
        scenario = case["scenario"]
        require(
            case["expected_outcome"] == expected_reasons[scenario],
            f"Expectativa de {scenario}",
        )
        require(
            case["directory"] == f"invalid/{scenario}",
            f"Directorio de {scenario}",
        )
        require(
            case["baseline"]
            == ("after_batch_001" if scenario in {"S13", "S14"} else "initial"),
            f"Base de {scenario}",
        )
        require(
            case["must_not_change_accepted_state"] is True,
            f"Expectativa de preservación de {scenario}",
        )

        directory = ROOT / case["directory"]
        manifest = json.loads(
            (directory / "manifest.json").read_text(encoding="utf-8")
        )
        require(manifest["schema_version"] == 1, f"Versión de {scenario}")
        require(
            manifest["batch_id"] == f"invalid_{scenario.lower()}",
            f"Identidad de {scenario}",
        )
        expected_files = (
            {"orders.csv", "order_items.csv"}
            if scenario in {"S16", "S17", "S19"}
            else {"changes.jsonl"}
        )
        require(set(manifest["files"]) == expected_files, f"Archivos de {scenario}")

        contents = {}
        hash_mismatches = []
        for filename, metadata in manifest["files"].items():
            path = directory / filename
            rows = (
                read_csv(path) if filename.endswith(".csv")
                else read_events(path)
            )
            require(len(rows) == metadata["row_count"], f"Conteo {scenario}/{filename}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != metadata["sha256"]:
                hash_mismatches.append(filename)
            contents[filename] = rows

        require(
            hash_mismatches == (["changes.jsonl"] if scenario == "S18" else []),
            f"Integridad de transporte de {scenario}",
        )

        if scenario in {"S13", "S14", "S15", "S18", "S20"}:
            require(len(contents["changes.jsonl"]) == 1, f"Evento único de {scenario}")
            event = contents["changes.jsonl"][0]

        if scenario == "S13":
            require(
                event["event_id"] == initial_customer_event["event_id"]
                and event != initial_customer_event,
                "S13 debe repetir event_id con contenido diferente",
            )
            restored = json.loads(json.dumps(event))
            restored["after"]["first_name"] = initial_customer_event["after"]["first_name"]
            require(restored == initial_customer_event, "Anomalía adicional en S13")

        elif scenario == "S14":
            require(
                event["event_id"] != initial_customer_event["event_id"],
                "S14 debe utilizar otro event_id",
            )
            restored = json.loads(json.dumps(event))
            restored["event_id"] = initial_customer_event["event_id"]
            require(restored == initial_customer_event, "Anomalía adicional en S14")

        elif scenario == "S15":
            original = orders[event["business_key"]["order_id"]]
            require(
                original["status"] == "cancelled"
                and event["after"]["status"] == "confirmed"
                and (original["status"], event["after"]["status"])
                not in valid_transitions,
                "S15 debe contener una transición prohibida",
            )

        elif scenario == "S16":
            bad_lines = [
                row for row in contents["order_items.csv"]
                if int(row["product_id"]) not in product_ids
            ]
            require(len(bad_lines) == 1, "S16 debe tener una referencia ausente")

        elif scenario == "S17":
            bad_lines = [
                row for row in contents["order_items.csv"]
                if Decimal(row["discount_amount"])
                > int(row["quantity"]) * Decimal(row["unit_price"])
            ]
            require(len(bad_lines) == 1, "S17 debe tener un descuento excesivo")

        elif scenario == "S18":
            require(
                event == initial_customer_event,
                "S18 debe conservar el evento y alterar solo el hash declarado",
            )

        elif scenario == "S19":
            repeated_orders = contents["orders.csv"]
            require(len(repeated_orders) == 1, "Pedido único de S19")
            repeated = repeated_orders[0]
            key = int(repeated["order_id"])
            require(key in orders, "S19 debe reutilizar una clave existente")
            original = orders[key]
            require(
                repeated["status"] != original["status"],
                "S19 debe tener contenido diferente",
            )
            require(
                all(int(row["order_id"]) == key
                    for row in contents["order_items.csv"]),
                "Líneas del pedido de S19",
            )

        elif scenario == "S20":
            original = orders[event["business_key"]["order_id"]]
            after = event["after"]
            require(
                after["customer_id"] in customer_ids
                and after["customer_id"] != int(original["customer_id"]),
                "S20 debe modificar customer_id a otro cliente existente",
            )
            require(
                (original["status"], after["status"]) in valid_transitions,
                "S20 debe conservar una transición de estado válida",
            )

        print(f"PASS: {scenario} — anomalía esperada verificada.")

    print("ALCANCE: datos de prueba verificados; rechazo en Silver pendiente.")


if __name__ == "__main__":
    main()
