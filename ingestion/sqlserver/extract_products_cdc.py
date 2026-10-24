"""Extrae cambios nativos de CDC para dbo.products."""

import pyodbc


def read_product_changes(connection, last_lsn):
    """Devuelve un intervalo de captura y sus cambios de productos."""
    if (
        not isinstance(last_lsn, str)
        or not last_lsn.startswith("0x")
        or len(last_lsn) != 22
    ):
        raise ValueError("El LSN debe contener 0x y veinte dígitos hexadecimales.")

    previous = bytes.fromhex(last_lsn[2:])
    cursor = connection.cursor()

    try:
        bounds = cursor.execute(
            """
            SELECT
                sys.fn_cdc_increment_lsn(?),
                sys.fn_cdc_get_min_lsn(N'dbo_products'),
                sys.fn_cdc_get_max_lsn()
            """,
            pyodbc.Binary(previous),
        ).fetchone()

        from_lsn, min_lsn, to_lsn = (
            bytes(value) if value is not None else None
            for value in bounds
        )

        if any(
            value is None or value == bytes(10)
            for value in (from_lsn, min_lsn, to_lsn)
        ):
            raise RuntimeError("CDC no devuelve límites válidos.")

        if from_lsn < min_lsn:
            raise RuntimeError(
                "El intervalo requerido venció por retención. "
                "No se avanzará la posición de extracción."
            )

        if previous > to_lsn:
            raise RuntimeError("El LSN guardado supera el límite actual de CDC.")

        changes = []

        if from_lsn <= to_lsn:
            cursor.execute(
                """
                SELECT
                    sys.fn_varbintohexstr(__$start_lsn) AS commit_lsn,
                    sys.fn_varbintohexstr(__$seqval) AS sequence_value,
                    __$operation AS operation_code,
                    product_id, category_id, sku, product_name, brand,
                    list_price, is_active, created_at, updated_at
                FROM cdc.fn_cdc_get_all_changes_dbo_products(?, ?, N'all')
                ORDER BY __$start_lsn, __$seqval, __$operation, product_id
                """,
                pyodbc.Binary(from_lsn),
                pyodbc.Binary(to_lsn),
            )

            columns = [column[0] for column in cursor.description]
            changes = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        return {
            "source_database": "TechRetail_OLTP",
            "capture_instance": "dbo_products",
            "after_lsn": last_lsn,
            "to_lsn": "0x" + to_lsn.hex(),
            "changes": changes,
        }
    finally:
        cursor.close()


def save_product_changes(batch, output_path):
    """Guarda un lote completo sin sobrescribir archivos existentes."""
    import json
    import os
    import tempfile
    from pathlib import Path

    from ingestion.sqlserver.capture_products_baseline import serialize

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=".cdc-products-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(
                batch, stream, ensure_ascii=False,
                indent=2, default=serialize,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    return output


def main():
    import argparse
    import getpass
    import json
    import os
    from pathlib import Path

    from sources.sqlserver.load_initial_data import odbc_value

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("SQL_SERVER_HOST"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.host:
        parser.error("Indica --host o configura SQL_SERVER_HOST.")
    if args.output.exists():
        parser.error("El archivo de salida ya existe.")

    checkpoint_path = args.checkpoint.resolve()
    output_path = args.output.resolve()

    if output_path.parent != checkpoint_path.parent:
        parser.error("El lote y el checkpoint deben estar en la misma carpeta.")

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if (
        checkpoint.get("source_database") != "TechRetail_OLTP"
        or checkpoint.get("capture_instance") != "dbo_products"
    ):
        parser.error("El checkpoint no corresponde a la captura de productos.")

    previous_batch = checkpoint_path.parent / checkpoint["batch_file"]
    saved_batch = json.loads(previous_batch.read_text(encoding="utf-8"))

    if (
        saved_batch.get("source_database") != checkpoint["source_database"]
        or saved_batch.get("capture_instance") != checkpoint["capture_instance"]
        or saved_batch.get("to_lsn") != checkpoint["last_extracted_lsn"]
    ):
        parser.error("El checkpoint no coincide con su lote guardado.")

    last_lsn = checkpoint["last_extracted_lsn"]
    port = os.environ.get("SQL_SERVER_PORT", "1433")
    password = os.environ.get("SQL_SERVER_READER_PASSWORD")
    if not password:
        password = getpass.getpass("Contraseña de retail_reader: ")

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={odbc_value(f'{args.host},{port}')};"
        "DATABASE=TechRetail_OLTP;"
        "UID=retail_reader;"
        f"PWD={odbc_value(password)};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    connection = pyodbc.connect(
        connection_string, timeout=15, autocommit=False
    )
    del password, connection_string

    try:
        connection.timeout = 60
        batch = read_product_changes(connection, last_lsn)
    finally:
        connection.rollback()
        connection.close()

    output = save_product_changes(batch, output_path)

    next_checkpoint = {
        "source_database": batch["source_database"],
        "capture_instance": batch["capture_instance"],
        "last_extracted_lsn": batch["to_lsn"],
        "batch_file": output.name,
    }

    from uuid import uuid4

    temporary = checkpoint_path.with_name(
        f".checkpoint-{uuid4().hex}.tmp"
    )
    try:
        save_product_changes(next_checkpoint, temporary)
        os.replace(temporary, checkpoint_path)
    finally:
        temporary.unlink(missing_ok=True)

    print("PASS: checkpoint actualizado después de guardar el lote.")

    print(f"Eventos guardados: {len(batch['changes'])}")
    print(f"Después de LSN: {batch['after_lsn']}")
    print(f"Hasta LSN: {batch['to_lsn']}")
    print(f"GUARDADO: {output}")


if __name__ == "__main__":
    main()
