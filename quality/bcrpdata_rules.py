"""Evalúa las observaciones conservadas de BCRPData."""

import re
from datetime import date
from urllib.parse import urlparse

from quality.api_extraction_input import parse_json, require
from quality.api_record_rules import evaluate_rate

MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "may": 5, "jun": 6, "jul": 7, "ago": 8,
    "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def observation_date(text, start, end):
    if not isinstance(text, str):
        raise ValueError("Fecha de observación no textual")
    match = re.fullmatch(
        r"(\d{1,2})\.([A-Za-z]+)\.(\d{2}|\d{4})", text.strip()
    )
    if not match:
        raise ValueError("Formato de fecha incompatible")
    day, month, year_text = match.groups()
    if month.lower() not in MONTHS:
        raise ValueError("Mes no reconocido")
    years = [
        year for year in range(start.year, end.year + 1)
        if (
            str(year) == year_text if len(year_text) == 4
            else year % 100 == int(year_text)
        )
    ]
    if len(years) != 1:
        raise ValueError("Año ambiguo o fuera del intervalo")
    observed = date(years[0], MONTHS[month.lower()], int(day))
    if not start <= observed <= end:
        raise ValueError("Fecha fuera del intervalo solicitado")
    return observed


def evaluate_bcrpdata(manifest, responses, payloads):
    require(
        manifest.get("source_system") == "bcrpdata"
        and manifest.get("series_code") == "PD04638PD",
        "DQ015", "Fuente o serie incompatible",
    )
    require(
        set(responses) == {"response.json"},
        "DQ015", "Inventario de respuestas incompatible",
    )
    try:
        start = date.fromisoformat(manifest["requested_start_date"])
        end = date.fromisoformat(manifest["requested_end_date"])
    except (KeyError, TypeError, ValueError) as error:
        from quality.api_extraction_input import ExtractionError
        raise ExtractionError("DQ015", "Intervalo solicitado inválido") from error
    require(start <= end, "DQ015", "Intervalo solicitado invertido")

    provenance = parse_json(
        payloads["response.json.metadata.json"], "DQ004", "procedencia"
    )
    expected_path = (
        "/estadisticas/series/api/PD04638PD/json/"
        f"{start.isoformat()}/{end.isoformat()}/esp"
    )
    require(
        urlparse(provenance["request_url"]).path == expected_path,
        "DQ015", "La solicitud no coincide con la serie y el intervalo",
    )

    data = responses["response.json"]
    require(isinstance(data, dict), "DQ015", "Respuesta no objeto")
    config = data.get("config")
    require(isinstance(config, dict), "DQ015", "Configuración ausente")
    series = config.get("series")
    require(
        isinstance(series, list) and len(series) == 1
        and isinstance(series[0], dict),
        "DQ015", "Se esperaba exactamente una serie",
    )
    name = series[0].get("name")
    require(
        isinstance(name, str) and bool(name.strip()),
        "DQ015", "Nombre de serie ausente",
    )
    periods = data.get("periods")
    require(
        isinstance(periods, list) and bool(periods),
        "DQ015", "Observaciones ausentes",
    )
    metadata = manifest["files"]["response.json"]
    require(
        type(metadata.get("row_count")) is int
        and metadata["row_count"] == len(periods),
        "DQ003", "Conteo de observaciones diferente",
    )

    records = []
    seen = set()
    for position, period in enumerate(periods, 1):
        errors = []
        observed = None
        rate_result = None
        if not isinstance(period, dict):
            errors.append({
                "code": "DQ015", "field": "record",
                "message": "Observación no objeto",
            })
        else:
            try:
                observed = observation_date(period.get("name"), start, end)
            except ValueError as error:
                errors.append({
                    "code": "DQ015", "field": "name",
                    "message": str(error),
                })
            if observed is not None:
                require(
                    observed not in seen,
                    "DQ015", f"Fecha duplicada: {observed}",
                )
                seen.add(observed)

            values = period.get("values")
            if not isinstance(values, list) or len(values) != 1:
                errors.append({
                    "code": "DQ015", "field": "values",
                    "message": "Se esperaba un valor por observación",
                })
            else:
                rate_result = evaluate_rate(values[0])
                errors.extend(rate_result["errors"])

        records.append({
            "status": "rejected" if errors else "accepted",
            "errors": errors,
            "source_file": "response.json",
            "record_number": position,
            "business_key": {
                "series_code": "PD04638PD",
                "observation_date": observed.isoformat() if observed else None,
            },
            "available": rate_result["available"] if rate_result else None,
            "rate": rate_result["rate"] if rate_result else None,
            "raw_value": rate_result["raw_value"] if rate_result else None,
        })

    # Los controles de la extracción completa se contrastan cuando
    # todos los registros superan las reglas de estructura y contenido.
    if all(record["status"] == "accepted" for record in records):
        available = sum(record["available"] for record in records)
        expected = {
            "source_series_name": name,
            "observation_count": len(records),
            "available_count": available,
            "unavailable_count": len(records) - available,
            "first_observation_date": min(seen).isoformat(),
            "last_observation_date": max(seen).isoformat(),
        }
        controls = manifest.get("controls")
        require(isinstance(controls, dict), "DQ017", "Controles ausentes")
        require(
            all(
                controls.get(key) == value
                and type(controls.get(key)) is type(value)
                for key, value in expected.items()
            ),
            "DQ017", "Controles diferentes del manifiesto",
        )
        require(available > 0, "DQ015", "Sin tasas numéricas disponibles")

    return records
