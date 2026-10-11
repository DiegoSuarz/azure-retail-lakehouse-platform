# Manifiesto de extracción inicial

## Objetivo

Identificar una extracción de SQL Server y registrar la evidencia
necesaria para aceptarla como entrada de Bronze.

## Ubicación

Dentro del contenedor bronze:

    sqlserver/techretail_oltp/initial/run_id=<ingestion_run_id>/manifest.json

## Generación

El manifiesto se generará mediante un script local de Python,
después de descargar y validar los archivos Parquet.

La publicación se realizará mediante Azure CLI con autenticación
de Microsoft Entra, sin utilizar claves de almacenamiento.

El pipeline realiza la copia. La aceptación y publicación del
manifiesto serán pasos manuales asistidos por scripts en esta etapa.

## Campos obligatorios

| Campo | Contenido |
|---|---|
| schema_version | Entero 1 |
| ingestion_run_id | RunId del pipeline |
| source_system | sqlserver |
| source_database | TechRetail_OLTP |
| pipeline_name | pl_ingest_sqlserver_initial |
| synthetic_cutoff_exclusive | 2026-10-01T00:00:00.000Z |
| extraction_started_at | Inicio real del pipeline en UTC |
| extraction_finished_at | Fin real del pipeline en UTC |
| validated_at | Fecha de validación en UTC |
| consistency | Método y controles de estabilidad del origen |
| entities | Archivos y conteos de las cinco tablas |
| reconciliation | Resultados de los controles |
| status | completed, únicamente después de validar |

Cada entidad registrará source_row_count, copy_rows_read,
copy_rows_copied y destination_row_count.

Cada archivo registrará su ruta relativa a la raíz de ejecución,
size_bytes y sha256. Se utilizarán los nombres reales generados por ADF.

## Consistencia y reconciliación

Se mantendrá una ventana sin escrituras durante extracción y validación.

Se comparará el contenido del origen antes y después de la copia,
mediante una representación determinista ordenada por clave primaria.

La igualdad de esas referencias detecta diferencias entre ambos
momentos, no demuestra por sí sola ausencia de modificaciones transitorias.

Los Parquet se compararán por clave contra el origen y se validarán
columnas, tipos compatibles, duplicados, relaciones, estados,
importes decimales y unidades.

Las métricas de Copy y las fechas de ejecución se obtendrán de ADF.
No se sustituirán por valores esperados ni por fechas inventadas.

## Finalización

Solo se generará status completed cuando las cinco entidades
superen todas las comprobaciones.

Una copia Succeeded sin manifiesto validado seguirá pendiente
de aceptación. Los fallos se conservarán en un informe local separado.

Antes de subir el manifiesto se comprobará que los archivos cloud
coincidan con los archivos descargados y validados.

No se sobrescribirá un manifiesto ya publicado.
La carga no se utilizará en Silver hasta finalizar su aceptación.
