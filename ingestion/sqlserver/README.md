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

Esta referencia local no sustituye el manifiesto final de Bronze.

## Estado

Captura del origen implementada y comprobada.
Validación de Parquet y generación del manifiesto pendientes.

## Validación de Parquet

tests/ingestion/validate_initial_parquet.py compara los archivos
descargados con las referencias del origen antes y después.

Comprueba columnas, tipos compatibles, conteos, claves,
todos los valores y relaciones entre las cinco entidades.

Genera un informe local únicamente cuando los controles pasan.
Este informe no sustituye el manifiesto publicado en Bronze.

Pruebas locales realizadas:

- Parquet con contenido idéntico: aceptados.
- Producto modificado, conservando el conteo: rechazado.
- Caso inválido: sin informe de aceptación.

Los archivos de prueba y la referencia posterior simulada
se crearon en una carpeta temporal y se eliminaron al terminar.

La validación de los archivos reales de ADF sigue pendiente.

## Manifiesto de extracción

build_initial_manifest.py utiliza las referencias del origen,
los Parquet descargados y los metadatos reales de ADF.

La carpeta descargada debe llamarse run_id=<RunId> y contener
los directorios de las cinco entidades.

El generador exige:

- Pipeline y cinco copias con estado Succeeded.
- Identificadores y fechas de ejecución válidos.
- Capturas del origen que delimiten la extracción.
- Confirmación de la ventana sin escrituras.
- Verificación de consistencia de Copy con resultado Verified.
- Validación local de los Parquet satisfactoria.
- Conteos de filas y archivos coincidentes con ADF.

Genera manifest.json en la raíz local de la ejecución.
No sobrescribe un manifiesto existente ni publica archivos en Azure.

Se comprobó el rechazo de metadatos incompletos sin generar manifiesto.
La generación con evidencias reales y la publicación siguen pendientes.
