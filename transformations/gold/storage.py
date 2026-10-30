"""Escritura y verificación de tablas Delta de Gold."""


def write_verified_gold_table(spark, frame, target):
    """Crea una tabla Delta y verifica sus tipos y valores recuperados."""
    frame.write.format("delta").mode("errorifexists").save(target)

    recovered = (
        spark.read.format("delta")
        .option("versionAsOf", 0)
        .load(target)
    )

    expected_types = [
        (field.name, field.dataType) for field in frame.schema
    ]
    actual_types = [
        (field.name, field.dataType) for field in recovered.schema
    ]
    if actual_types != expected_types:
        raise ValueError(f"Gold: columnas o tipos diferentes en {target}")

    if (
        frame.exceptAll(recovered).limit(1).count()
        or recovered.exceptAll(frame).limit(1).count()
    ):
        raise ValueError(f"Gold: valores diferentes en {target}")

    return {
        "path": target,
        "version": 0,
        "row_count": recovered.count(),
        "verified": True,
    }
