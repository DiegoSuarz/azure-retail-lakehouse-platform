"""Lee una extracción de API y verifica integridad y procedencia."""

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID


class ExtractionError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(condition, code, message):
    if not condition:
        raise ExtractionError(code, message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Clave JSON repetida: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Constante JSON incompatible: {value}")


def parse_json(payload, code, label):
    try:
        return json.loads(
            payload,
            parse_float=Decimal,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (ValueError, UnicodeError) as error:
        raise ExtractionError(code, f"JSON inválido en {label}: {error}") from error


def utc_date(value, label):
    try:
        require(isinstance(value, str), "DQ001", f"Fecha ausente: {label}")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExtractionError("DQ001", f"Fecha inválida: {label}") from error
    require(
        result.tzinfo is not None and result.utcoffset() == timedelta(0),
        "DQ001", f"Fecha no UTC: {label}",
    )
    return result


def read_extraction(directory):
    """Lee respuestas y procedencia sin manifiesto global."""
    directory = Path(directory)
    require(
        directory.is_dir() and not directory.is_symlink(),
        "DQ002", "Directorio ausente o enlace simbólico",
    )
    root = directory.resolve()
    try:
        require(
            root.name.startswith("run_id=")
            and root.parent.name.startswith("ingestion_date="),
            "DQ001", "Ruta de extracción incompatible",
        )
        run_id = root.name.removeprefix("run_id=")
        try:
            require(str(UUID(run_id)) == run_id, "DQ001", "RunId no canónico")
            ingestion_date = date.fromisoformat(
                root.parent.name.removeprefix("ingestion_date=")
            )
        except ValueError as error:
            raise ExtractionError("DQ001", "Identidad de extracción inválida") from error

        payloads = {}
        for path in sorted(root.rglob("*")):
            require(not path.is_symlink(), "DQ002", "Enlace simbólico en extracción")
            if path.is_dir():
                continue
            require(path.is_file(), "DQ002", "Entrada no regular")
            relative = path.relative_to(root).as_posix()
            require(
                relative.endswith(".json")
                and path.name not in {"manifest.json", "failure.json"},
                "DQ002", f"Archivo no admitido: {relative}",
            )
            payloads[relative] = path.read_bytes()

        require(bool(payloads), "DQ002", "Extracción vacía")
        documents = {
            name: parse_json(payload, "DQ004", name)
            for name, payload in payloads.items()
        }
        response_names = {
            name for name in payloads if not name.endswith(".metadata.json")
        }
        require(bool(response_names), "DQ002", "Sin respuestas")
        require(
            set(payloads) == response_names | {
                name + ".metadata.json" for name in response_names
            },
            "DQ002", "Respuestas o metadatos sin pareja",
        )

        source = None
        responses = {}
        for name in sorted(response_names):
            provenance = documents[name + ".metadata.json"]
            require(isinstance(provenance, dict), "DQ004", f"Metadatos inválidos: {name}")
            current_source = provenance.get("source_system")
            require(
                isinstance(current_source, str)
                and current_source in {"dummyjson", "bcrpdata"},
                "DQ001", f"Fuente incompatible: {name}",
            )
            if source is None:
                source = current_source
            require(
                current_source == source
                and type(provenance.get("schema_version")) is int
                and provenance["schema_version"] == 1
                and provenance.get("ingestion_run_id") == run_id
                and type(provenance.get("http_status")) is int
                and provenance["http_status"] == 200,
                "DQ001", f"Identidad o estado HTTP incompatible: {name}",
            )
            payload = payloads[name]
            require(
                provenance.get("payload_sha256")
                == hashlib.sha256(payload).hexdigest()
                and type(provenance.get("size_bytes")) is int
                and provenance["size_bytes"] == len(payload),
                "DQ002", f"Contenido diferente de su procedencia: {name}",
            )
            extracted = utc_date(provenance.get("extracted_at"), name)
            require(
                extracted.date() >= ingestion_date,
                "DQ001", f"Respuesta anterior a la fecha de ingesta: {name}",
            )
            url = provenance.get("request_url")
            require(isinstance(url, str), "DQ001", f"URL ausente: {name}")
            parsed = urlparse(url)
            expected_host = (
                "dummyjson.com" if source == "dummyjson"
                else "estadisticas.bcrp.gob.pe"
            )
            require(
                parsed.scheme == "https" and parsed.hostname == expected_host
                and parsed.username is None and parsed.password is None,
                "DQ001", f"URL incompatible: {name}",
            )
            responses[name] = documents[name]

        suffix = (
            ("dummyjson", "products")
            if source == "dummyjson"
            else ("bcrpdata", "exchange_rates", "series_code=pd04638pd")
        )
        prefix = root.parent.parent
        require(
            tuple(prefix.parts[-len(suffix):]) == suffix,
            "DQ001", "Ruta diferente de la fuente",
        )
        extraction = {
            "source_system": source,
            "ingestion_run_id": run_id,
            "ingestion_date": ingestion_date.isoformat(),
        }
        return extraction, responses, payloads
    except OSError as error:
        raise ExtractionError("DQ002", f"No se pudo leer la extracción: {error}") from error
