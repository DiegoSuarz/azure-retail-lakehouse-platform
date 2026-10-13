"""Lee una extracción de API y verifica integridad y procedencia."""

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path, PurePosixPath
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
    root = Path(directory).resolve()
    try:
        manifest = parse_json(
            (root / "manifest.json").read_bytes(), "DQ001", "manifest.json"
        )
        require(isinstance(manifest, dict), "DQ001", "Manifiesto no objeto")
        require(
            type(manifest.get("schema_version")) is int
            and manifest["schema_version"] == 1,
            "DQ001", "Versión incompatible",
        )
        require(manifest.get("status") == "completed", "DQ001", "Extracción incompleta")
        source = manifest.get("source_system")
        require(
            isinstance(source, str) and source in {"dummyjson", "bcrpdata"},
            "DQ001", "Fuente incompatible",
        )
        run_id = manifest.get("ingestion_run_id")
        try:
            require(isinstance(run_id, str), "DQ001", "RunId ausente")
            UUID(run_id)
            ingestion_date = date.fromisoformat(manifest["ingestion_date"])
        except (ValueError, TypeError, KeyError) as error:
            raise ExtractionError("DQ001", "Identidad de extracción inválida") from error

        require(root.name == f"run_id={run_id}", "DQ001", "RunId diferente de la carpeta")
        require(
            root.parent.name == f"ingestion_date={ingestion_date.isoformat()}",
            "DQ001", "Fecha de ingesta diferente de la carpeta",
        )
        started = utc_date(manifest.get("extraction_started_at"), "inicio")
        finished = utc_date(manifest.get("extraction_finished_at"), "fin")
        require(started <= finished, "DQ001", "Intervalo de extracción invertido")
        require(
            ingestion_date == started.date(),
            "DQ001", "Fecha de ingesta diferente del inicio UTC",
        )

        files = manifest.get("files")
        require(isinstance(files, dict) and bool(files), "DQ002", "Inventario inválido")
        payloads = {}
        for relative, metadata in files.items():
            name = PurePosixPath(relative)
            require(
                bool(relative) and not name.is_absolute()
                and ".." not in name.parts and "\\" not in relative
                and name.as_posix() == relative and relative != "manifest.json",
                "DQ002", f"Ruta incompatible: {relative}",
            )
            path = root / relative
            require(
                path.resolve().is_relative_to(root)
                and not path.is_symlink() and path.is_file(),
                "DQ002", f"Archivo ausente o ruta incompatible: {relative}",
            )
            require(isinstance(metadata, dict), "DQ002", f"Metadatos inválidos: {relative}")
            payload = path.read_bytes()
            require(
                hashlib.sha256(payload).hexdigest() == metadata.get("sha256"),
                "DQ002", f"Hash diferente: {relative}",
            )
            require(
                type(metadata.get("size_bytes")) is int
                and len(payload) == metadata["size_bytes"],
                "DQ002", f"Tamaño diferente: {relative}",
            )
            payloads[relative] = payload

        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*") if path.is_file()
        }
        require(actual == set(files) | {"manifest.json"}, "DQ002", "Inventario diferente")

        documents = {
            name: parse_json(payload, "DQ004", name)
            for name, payload in payloads.items()
        }
        responses = {}
        expected_host = (
            "dummyjson.com" if source == "dummyjson"
            else "estadisticas.bcrp.gob.pe"
        )
        for name, metadata in files.items():
            if name.endswith(".metadata.json"):
                continue
            sidecar = metadata.get("metadata_file")
            require(
                isinstance(sidecar, str) and sidecar == name + ".metadata.json"
                and sidecar in documents,
                "DQ002", f"Procedencia ausente: {name}",
            )
            provenance = documents[sidecar]
            require(isinstance(provenance, dict), "DQ004", f"Procedencia inválida: {name}")
            require(
                type(provenance.get("schema_version")) is int
                and provenance["schema_version"] == 1
                and provenance.get("source_system") == source
                and provenance.get("ingestion_run_id") == run_id
                and type(provenance.get("http_status")) is int
                and provenance["http_status"] == 200,
                "DQ001", f"Identidad o estado HTTP incompatible: {name}",
            )
            require(
                provenance.get("payload_sha256") == metadata["sha256"]
                and type(provenance.get("size_bytes")) is int
                and provenance["size_bytes"] == metadata["size_bytes"],
                "DQ002", f"Procedencia diferente del contenido: {name}",
            )
            extracted = utc_date(provenance.get("extracted_at"), name)
            require(
                started <= extracted <= finished,
                "DQ001", f"Fecha de respuesta fuera de la extracción: {name}",
            )
            url = provenance.get("request_url")
            require(isinstance(url, str), "DQ001", f"URL ausente: {name}")
            parsed = urlparse(url)
            require(
                parsed.scheme == "https" and parsed.hostname == expected_host
                and parsed.username is None and parsed.password is None,
                "DQ001", f"URL de procedencia incompatible: {name}",
            )
            responses[name] = documents[name]

        referenced = {
            metadata["metadata_file"]
            for metadata in files.values()
            if isinstance(metadata, dict) and "metadata_file" in metadata
        }
        require(
            referenced == {name for name in files if name.endswith(".metadata.json")},
            "DQ002", "Metadatos adicionales sin respuesta asociada",
        )
        return manifest, responses, payloads
    except OSError as error:
        raise ExtractionError("DQ002", f"No se pudo leer la extracción: {error}") from error
