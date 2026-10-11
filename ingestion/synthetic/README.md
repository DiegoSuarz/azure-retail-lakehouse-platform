# Ingesta de lotes sintéticos

## Objetivo

Conservar los lotes funcionales de M2 en Bronze sin modificar sus bytes.
Los scripts no aplican eventos ni modifican SQL Server.

## Requisitos

Ejecutar desde la raíz del repositorio con el entorno virtual activo.
La publicación requiere Azure CLI con sesión Microsoft Entra,
permisos de escritura y lectura en bronze y acceso de red autorizado.

## Validación local

    python ingestion/synthetic/validate_batches.py

Comprueba identidad, versión, inventario, conteos y hashes.
Complementa las validaciones de negocio de tests/generators.

## Preparación

    python ingestion/synthetic/ingest_batches.py

Valida los originales y una copia temporal.
Muestra las rutas previstas sin llamar a Azure.
La publicación posterior genera otro ingestion_run_id.

## Publicación

    python ingestion/synthetic/ingest_batches.py \
        --publish \
        --report data/validation/synthetic_ingestion_report.json

El informe no debe existir.
Los cuatro lotes comparten un UUID de ingesta.

Los datos se suben y verifican antes de publicar el manifiesto original.
Todos los archivos se descargan y verifican mediante SHA-256.
La publicación impide sobrescribir objetos existentes.

El proceso genera operaciones facturables de almacenamiento,
transferencia cuando corresponda y capacidad por los archivos conservados.

## Fallos

Un fallo detiene el proceso y se registra en el informe.
No se eliminan automáticamente los archivos publicados.

Revisar el informe antes de repetir una ejecución.
Un lote sin manifiesto está incompleto.
Un manifiesto publicado puede existir aunque su comprobación posterior
haya fallado; revisar ese caso antes de aceptar el lote.

## Pruebas realizadas

- Preparación de los cuatro lotes: satisfactoria.
- Archivo alterado en una copia temporal: rechazado por hash.
- Caso alterado: ninguna llamada a Azure CLI ni informe de publicación.

## Evidencia de publicación

Ingestion_run_id: 1c55b98a-9a92-4637-b4fe-a3528ae92565.

| Lote | Archivos publicados y verificados |
|---|---:|
| batch_001 | 4 |
| batch_002 | 2 |
| batch_003 | 2 |
| batch_004 | 2 |
| Total | 10 |

Ruta dentro de bronze:

    synthetic/incremental/batch_id=<batch_id>/run_id=1c55b98a-9a92-4637-b4fe-a3528ae92565/

Informe local: data/validation/synthetic_ingestion_report.json.
Los datos y el informe permanecen fuera de Git.

## Estado

Cuatro lotes funcionales publicados y verificados.
Procesamiento de eventos en Silver pendiente.
