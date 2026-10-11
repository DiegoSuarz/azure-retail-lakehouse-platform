"""Extrae y valida la serie histórica de tipo de cambio de BCRPData."""

import argparse
import hashlib
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from api_common import fetch_json, require, utc_now, write_json

SERIES = "PD04638PD"
MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "may": 5, "jun": 6, "jul": 7, "ago": 8,
    "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def observation_date(text, start, end):
    require(isinstance(text, str), "Fecha de observación no textual")
    match = re.fullmatch(
        r"(\d{1,2})\.([A-Za-z]+)\.(\d{2}|\d{4})", text.strip()
    )
    require(match is not None, f"Formato de fecha inesperado: {text}")
    day, month, year_text = match.groups()
    require(month.lower() in MONTHS, f"Mes no reconocido: {text}")

    years = [
        year for year in range(start.year, end.year + 1)
        if (
            str(year) == year_text if len(year_text) == 4
            else year % 100 == int(year_text)
        )
    ]
    require(len(years) == 1, f"Año ambiguo o fuera del intervalo: {text}")
    result = date(years[0], MONTHS[month.lower()], int(day))
    require(start <= result <= end, f"Observación fuera del intervalo: {text}")
    return result


def validate_response(data, start, end):
    require(isinstance(data, dict), "Respuesta BCRP incompatible")
    config = data.get("config")
    require(isinstance(config, dict), "Falta config")
    series = config.get("series")
    require(
        isinstance(series, list) and len(series) == 1
        and isinstance(series[0], dict),
        "Se esperaba exactamente una serie",
    )
    name = series[0].get("name")
    require(isinstance(name, str) and bool(name.strip()), "Nombre de serie ausente")

    periods = data.get("periods")
    require(isinstance(periods, list) and bool(periods), "Sin observaciones")
    seen = set()
    unavailable = 0

    for period in periods:
        require(isinstance(period, dict), "Observación incompatible")
        observed = observation_date(period.get("name"), start, end)
        require(observed not in seen, f"Fecha duplicada: {observed}")
        seen.add(observed)

        values = period.get("values")
        require(
            isinstance(values, list) and len(values) == 1,
            f"Se esperaba un valor: {observed}",
        )
        raw = values[0]
        require(isinstance(raw, str), f"Tasa no textual: {observed}")
        try:
            rate = Decimal(raw.strip())
        except InvalidOperation:
            unavailable += 1
            continue
        if not rate.is_finite():
            unavailable += 1
            continue
        require(rate > 0, f"Tasa no positiva: {observed}")

    available = len(periods) - unavailable
    require(available > 0, "No se recibieron tasas numéricas válidas")
    return {
        "source_series_name": name,
        "observation_count": len(periods),
        "available_count": available,
        "unavailable_count": unavailable,
        "first_observation_date": min(seen).isoformat(),
        "last_observation_date": max(seen).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default="2026-09-30")
    parser.add_argument(
        "--output-root", type=Path, default=Path("data/apis")
    )
    args = parser.parse_args()

    try:
        start = date.fromisoformat(args.start_date)
        end = date.fromisoformat(args.end_date)
    except ValueError:
        parser.error("Las fechas deben utilizar YYYY-MM-DD.")
    if start > end:
        parser.error("La fecha inicial debe ser anterior o igual a la final.")

    run_id = str(uuid4())
    started_at = utc_now()
    ingestion_date = datetime.now(timezone.utc).date().isoformat()
    root = (
        args.output_root / "bcrpdata" / "exchange_rates"
        / f"series_code={SERIES.lower()}"
        / f"ingestion_date={ingestion_date}" / f"run_id={run_id}"
    )
    root.mkdir(parents=True, exist_ok=False)
    print(f"EXTRACCIÓN: {root}")

    url = (
        "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
        f"{SERIES}/json/{start.isoformat()}/{end.isoformat()}/esp"
    )
    try:
        path = root / "response.json"
        data, metadata = fetch_json(url, path, run_id, "bcrpdata")
        controls = validate_response(data, start, end)

        files = {}
        for filename in ("response.json", "response.json.metadata.json"):
            content = (root / filename).read_bytes()
            files[filename] = {
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        files["response.json"].update({
            "row_count": controls["observation_count"],
            "metadata_file": "response.json.metadata.json",
        })

        write_json(root / "manifest.json", {
            "schema_version": 1,
            "source_system": "bcrpdata",
            "series_code": SERIES,
            "ingestion_run_id": run_id,
            "ingestion_date": ingestion_date,
            "requested_start_date": start.isoformat(),
            "requested_end_date": end.isoformat(),
            "extraction_started_at": started_at,
            "extraction_finished_at": utc_now(),
            "controls": controls,
            "files": files,
            "status": "completed",
        })
    except BaseException as error:
        write_json(root / "failure.json", {
            "status": "failed",
            "ingestion_run_id": run_id,
            "failed_at": utc_now(),
            "error_type": type(error).__name__,
            "error_message": str(error),
        })
        raise

    print(f"SERIE: {controls['source_series_name']}")
    print(f"PASS: {controls['observation_count']} fechas únicas dentro del intervalo.")
    print(f"TASAS DISPONIBLES: {controls['available_count']}")
    print(f"NO DISPONIBLES: {controls['unavailable_count']}")
    print(f"MANIFIESTO: {root / 'manifest.json'}")
    print("ALCANCE: extracción local; publicación en Bronze pendiente.")


if __name__ == "__main__":
    main()
