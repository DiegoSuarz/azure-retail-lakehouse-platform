# Ingesta de API

## Objetivo

Conservar respuestas originales de DummyJSON y BCRPData en Bronze,
con metadatos de procedencia y manifiestos de extracción.

La extracción utiliza Python y la publicación Azure CLI.
ADF todavía no coordina estas extracciones.

## Componentes

| Script | Función |
|---|---|
| api_common.py | Solicitudes HTTP, reintentos y conservación de respuestas |
| extract_dummyjson.py | Extracción paginada de categorías tecnológicas |
| extract_bcrpdata.py | Extracción histórica de tipo de cambio |
| publish_api_extraction.py | Publicación y verificación en Bronze |

El publicador reutiliza upload y verify de ingestion/synthetic/ingest_batches.py.

## Extracción local

Desde la raíz del repositorio, con el entorno virtual activo:

    python ingestion/apis/extract_dummyjson.py --page-size 5
    python ingestion/apis/extract_bcrpdata.py

Cada ejecución crea una carpeta nueva bajo data/apis.
Las rutas incluyen fecha UTC de ingesta e ingestion_run_id.

Las respuestas se guardan sin reformatear.
Cada respuesta tiene metadatos con URL, fecha UTC, estado HTTP y SHA-256.

El cliente utiliza timeout de 30 segundos y hasta tres intentos.
No reintenta automáticamente HTTP 400, 401, 403 o 404.
Una espera Retry-After superior a 60 segundos detiene la extracción
para retomarla después, respetando el plazo indicado.

Una extracción fallida conserva las respuestas guardadas y failure.json.
No genera un manifiesto completed.

## Validaciones

DummyJSON comprueba categorías, paginación, estabilidad del total,
IDs únicos y campos obligatorios.

BCRPData comprueba una serie, fechas únicas dentro del intervalo,
un valor por observación y tasas numéricas positivas.
Los valores no disponibles se conservan; no se convierten en cero.

Los importes se interpretan con Decimal.
Las respuestas originales conservan la precisión recibida.

## Publicación

Preparación sin publicación:

    python ingestion/apis/publish_api_extraction.py --run-dir <carpeta>

Publicación:

    python ingestion/apis/publish_api_extraction.py \
        --run-dir <carpeta> \
        --publish \
        --report data/validation/<informe-nuevo>.json

Requiere Azure CLI autenticado mediante Microsoft Entra,
permisos de lectura y escritura en bronze y acceso de red autorizado.

Se comprueban identidad, rutas, inventario, tamaños y hashes.
Una copia temporal conserva los bytes preparados para publicar.

Los archivos se suben sin sobrescritura y se verifican mediante descarga.
El manifiesto se publica al final.
El informe registra el estado y los resultados por archivo.

Si falla, revisar el informe antes de repetir.
No se eliminan automáticamente archivos parciales.

La publicación genera operaciones facturables de almacenamiento,
transferencia cuando corresponda y capacidad por los archivos conservados.

## Evidencias

Extracciones del 2026-10-11, publicadas y verificadas:

| Fuente | Control | Resultado |
|---|---|---:|
| DummyJSON | Productos únicos | 38 |
| DummyJSON | Categorías | 4 |
| DummyJSON | Páginas de productos | 9 |
| DummyJSON | Archivos publicados, incluido manifiesto | 21 |
| BCRPData | Observaciones | 195 |
| BCRPData | Tasas disponibles | 184 |
| BCRPData | Valores n.d. | 11 |
| BCRPData | Archivos publicados, incluido manifiesto | 3 |

DummyJSON ingestion_run_id:

    172c6634-a566-4ae8-bfc7-04ae228dae77

BCRPData ingestion_run_id:

    e7d0e002-b3a6-4de3-8157-c2a3f818cd38

Serie BCRPData: PD04638PD.
Intervalo solicitado: 2026-01-01 a 2026-09-30.

Los 24 archivos publicados se verificaron mediante SHA-256.
Los datos e informes locales permanecen fuera de Git.

## Pendientes

- Incorporar el mapeo educativo versionado a Silver.
- Normalizar las respuestas en Silver.
- Definir el tratamiento analítico de fechas sin cotización.
- Incorporar posteriormente la coordinación mediante ADF.
