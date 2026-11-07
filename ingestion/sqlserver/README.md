# Ingesta inicial de SQL Server

## Referencia del origen

capture_initial_source.py lee las cinco tablas de TechRetail_OLTP
mediante retail_reader, sin modificar registros.

Comprueba conteos y controles comerciales de M2.
Guarda registros ordenados por clave, columnas, hashes y fechas.

## Ejecución

Desde la raíz del repositorio, con el entorno virtual activo:

    (
        set -e
        set -a
        source .env
        set +a
        python ingestion/sqlserver/capture_initial_source.py \
            --output data/validation/source_before.json
    )

El archivo de salida no se sobrescribe y permanece fuera de Git.

## Consistencia

La captura utiliza aislamiento SERIALIZABLE.
Los bloqueos se liberan al terminar y no cubren la extracción de ADF.

Se mantendrá una ventana sin escrituras durante extracción y validación.
La referencia se comparará con los Parquet y una captura posterior.

Esta referencia local debe complementarse con la validación Parquet
y la revisión manual de ADF.

## Estado

Captura del origen implementada y comprobada.
Carga inicial histórica validada con manifiesto publicado en Bronze.
El flujo actual no requiere generar ni publicar nuevos manifiestos.

## Validación de Parquet

tests/ingestion/validate_initial_parquet.py compara los archivos
descargados con las referencias del origen antes y después.

Comprueba columnas, tipos compatibles, conteos, claves,
todos los valores y relaciones entre las cinco entidades.

Genera un informe local únicamente cuando los controles pasan.
Este informe no sustituye la revisión manual de las métricas de ADF
ni la comparación de los archivos cloud con los validados.

Pruebas locales realizadas:

- Parquet con contenido idéntico: aceptados.
- Producto modificado, conservando el conteo: rechazado.
- Caso inválido: sin informe de aceptación.

Los archivos de prueba y la referencia posterior simulada
se crearon en una carpeta temporal y se eliminaron al terminar.

Los cinco Parquet reales de ADF se validaron satisfactoriamente
contra las referencias de SQL Server antes y después.

## Aceptación sin manifiesto

Se retira el constructor build_initial_manifest.py.
La validación de datos se ejecuta directamente:

    python tests/ingestion/validate_initial_parquet.py \
        --before RUTA_CAPTURA_ANTERIOR \
        --after RUTA_CAPTURA_POSTERIOR \
        --parquet-dir CARPETA_PARQUET \
        --report RUTA_NUEVO_INFORME

El operador revisa en ADF estados, identificadores, fechas,
consistencia Verified y métricas de filas y archivos.
Confirma la ventana sin escrituras y que las capturas delimitan
la extracción. Conserva evidencia de esa revisión.

También compara los archivos cloud con los descargados y validados.
El informe Parquet no acredita automáticamente estas revisiones.

Procedimiento: [Aceptación de extracción inicial](../../docs/design/initial-extraction-manifest.md).

La ejecución documentada a continuación pertenece al flujo histórico.

## Ejecución inicial aceptada

- Pipeline: pl_ingest_sqlserver_initial.
- RunId: 89d277f4-ddee-49a2-9d9f-588efacf9788.
- Inicio UTC: 2026-10-11T01:32:05Z.
- Fin UTC: 2026-10-11T01:34:25Z.
- Estado de ADF: Succeeded.
- Cinco actividades Copy con consistencia Verified.
- Ventana sin escrituras confirmada por el operador.

| Entidad | Filas validadas | Archivos Parquet |
|---|---:|---:|
| categories | 6 | 1 |
| products | 60 | 1 |
| customers | 500 | 1 |
| orders | 2000 | 1 |
| order_items | 5862 | 1 |
| Total | 8428 | 5 |

Las referencias del origen antes y después coinciden.
Los Parquet conservan todos los valores del origen, con tipos
compatibles, claves y relaciones válidas.

Una segunda descarga confirmó que los cinco archivos cloud
coinciden byte por byte con los archivos validados.

El manifiesto está publicado en bronze, en:

    sqlserver/techretail_oltp/initial/run_id=89d277f4-ddee-49a2-9d9f-588efacf9788/manifest.json

Su publicación impidió sobrescribir un manifiesto existente.
La copia publicada se descargó y coincidió byte por byte con la local.

La aceptación utilizó scripts locales y publicación mediante CLI.
El pipeline de ADF todavía no automatiza estas comprobaciones
ni la publicación del manifiesto.
