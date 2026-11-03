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

Comprueba estructura y archivos admitidos; calcula conteos y hashes
para comparar la preparación temporal.
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

Se suben únicamente los archivos de datos; no se publica un manifiesto.
Todos los archivos se descargan y verifican mediante SHA-256.
La publicación impide sobrescribir objetos existentes.

El proceso genera operaciones facturables de almacenamiento,
transferencia cuando corresponda y capacidad por los archivos conservados.

## Fallos

Un fallo detiene el proceso y se registra en el informe.
No se eliminan automáticamente los archivos publicados.

Revisar el informe antes de repetir una ejecución.
La aceptación exige revisar el informe y todos los archivos esperados.
La publicación no es atómica: una carpeta puede contener solo una parte
de la entrega si la ejecución falla.

## Pruebas históricas realizadas

- Preparación de los cuatro lotes: satisfactoria.
- Archivo alterado en una copia temporal: rechazado por hash.
- Caso alterado: ninguna llamada a Azure CLI ni informe de publicación.

## Evidencia histórica de publicación

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

## Flujo actual comprobado sin manifiestos

Los generadores crean tres archivos en batch_001 y un JSONL en cada
lote adicional: seis archivos de datos en total.
La preparación local de los cuatro lotes y las simulaciones S08–S12
se comprobaron sin publicar en Azure.

La tabla histórica anterior incluye cuatro manifiestos; sus cifras
no describen una publicación nueva bajo el contrato actual.
Las entradas antiguas requieren copias compatibles sin manifest.json.
No modificar ni mezclar entregas mientras se preparan o procesan.
