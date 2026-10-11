"""Funciones comunes para conservar respuestas originales de API."""

import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "azure-retail-lakehouse-platform/1.0",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def retry_delay(value, attempt):
    if value:
        try:
            return max(0, int(value))
        except ValueError:
            try:
                moment = parsedate_to_datetime(value)
                return max(
                    0,
                    (moment - datetime.now(timezone.utc)).total_seconds(),
                )
            except (ValueError, TypeError, OverflowError):
                pass
    return 2 ** attempt


def reject_constant(value):
    raise ValueError(f"Constante JSON no válida: {value}")


def fetch_json(url, output, run_id, source_system):
    require(not output.exists(), f"Archivo existente: {output}")
    metadata_path = output.with_name(output.name + ".metadata.json")
    require(
        not metadata_path.exists(),
        f"Metadatos existentes: {metadata_path}",
    )

    for attempt in range(1, 4):
        request = Request(url, headers=HEADERS)
        try:
            with urlopen(request, timeout=30) as response:
                status = response.status
                require(status == 200, f"Estado HTTP inesperado: {status}")
                payload = response.read()
                response_url = response.geturl()
            break
        except HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code <= 599
            retry_after = error.headers.get("Retry-After")
            error.close()
            if not retryable or attempt == 3:
                raise
            delay = retry_delay(retry_after, attempt)
        except (URLError, TimeoutError, ConnectionError):
            if attempt == 3:
                raise
            delay = retry_delay(None, attempt)

        # Una espera larga requiere retomar la extracción posteriormente.
        require(
            delay <= 60,
            f"Reintento aplazado: esperar al menos {delay:.0f} segundos "
            "antes de una nueva ejecución.",
        )
        print(f"REINTENTO: intento {attempt + 1}/3 en {delay:.0f} segundos.")
        time.sleep(delay)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(payload)

    metadata = {
        "schema_version": 1,
        "ingestion_run_id": run_id,
        "source_system": source_system,
        "request_url": url,
        "response_url": response_url,
        "extracted_at": utc_now(),
        "http_status": status,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "attempts": attempt,
    }
    write_json(metadata_path, metadata)

    parsed = json.loads(
        payload,
        parse_float=Decimal,
        parse_constant=reject_constant,
    )
    return parsed, metadata
