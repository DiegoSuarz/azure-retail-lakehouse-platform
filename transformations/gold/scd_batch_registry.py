"""Registro local de lotes SCD con creación exclusiva."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def register_scd_batch(
    registry_root, identity, target_path, base_version, run_id
):
    """Crea o recupera un registro local sin sobrescribir lotes existentes."""
    payload = identity["payload"]
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    calculated_sha = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    if identity["sha256"] != calculated_sha:
        raise ValueError("La huella de identidad no corresponde a su contenido.")

    dimension = payload["dimension"]
    batch_id = payload["batch_id"]
    if dimension not in ("dim_product", "dim_customer"):
        raise ValueError("Dimensión no admitida para registrar el lote.")
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise ValueError("Se requiere batch_id no vacío.")
    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError("Se requiere una ruta de destino no vacía.")
    if type(base_version) is not int or base_version < 0:
        raise ValueError("La versión Delta de partida es inválida.")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("Se requiere run_id no vacío.")

    batch_filename = hashlib.sha256(batch_id.encode("utf-8")).hexdigest()
    directory = Path(registry_root) / dimension
    record_path = directory / f"{batch_filename}.json"
    directory.mkdir(parents=True, exist_ok=True)

    def read_existing():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record["registry_format_version"] != 1:
            raise ValueError("Formato de registro incompatible.")
        if record["identity"] != identity:
            raise ValueError("El lote ya existe con otra identidad.")
        if (
            record["target_path"] != target_path
            or record["base_version"] != base_version
        ):
            raise ValueError("El lote ya existe con otro destino o versión de partida.")
        return record, False

    if record_path.exists():
        return read_existing()

    record = {
        "registry_format_version": 1,
        "identity": identity,
        "target_path": target_path,
        "base_version": base_version,
        "status": "registered",
        "registered_run_id": run_id,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {},
        "result": None,
    }

    temporary = directory / f".registry-{uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            )

        try:
            os.link(temporary, record_path)
        except FileExistsError:
            return read_existing()

        return record, True
    finally:
        temporary.unlink(missing_ok=True)
