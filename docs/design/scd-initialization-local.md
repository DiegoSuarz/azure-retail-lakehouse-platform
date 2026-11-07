# Inicialización local de dimensiones SCD

## Objetivo

Preparar dim_product y dim_customer para el procesamiento SCD,
preservando claves, atributos y procedencia de la base Gold aceptada de M9.

## Implementación

- scd_initialization.py añade vigencias y auditoría a los DataFrames.
- run_scd_initialization_local.py valida las entradas, crea las copias
  Delta y comprueba los datos recuperados.
- Las entradas se indican mediante argumentos de ejecución, sin manifiesto.
- Los informes de construcción y validación de M9 acreditan la base elegida.
- La huella SHA-256 vincula la validación con el informe de construcción.

## Ejecución aceptada

- Lote: f8f2f3e2-3121-4008-9959-cda1b0668ebb.
- Ejecución: e5a45834-7251-486a-8729-1bde9dc20036.
- Observación UTC: 2026-11-03T01:55:49.105725+00:00.
- Procesamiento UTC: 2026-11-03T16:22:27.244653+00:00.
- Finalización UTC: 2026-11-03T16:23:13.651789+00:00.
- Estado: completed.
- Ejecución Gold de origen: 815d77ca-1b31-40f4-b3b1-a6eeb9e23aa0.

## Resultados

| Tabla | Filas | Versión Delta | Escritura verificada |
|---|---:|---:|---|
| dim_product | 61 | 0 | Sí |
| dim_customer | 500 | 0 | Sí |

Las entradas dim_product, dim_customer y fact_sales se leyeron
en su versión Delta 0. La tabla de hechos contiene 5862 líneas.

Las copias se guardaron bajo:

data/validation/scd/batch_id=f8f2f3e2-3121-4008-9959-cda1b0668ebb/tables/

El informe se conserva en report.json dentro de la carpeta del lote.

## Estado inicial de las filas

- valid_from coincide con observed_at.
- valid_to es NULL.
- is_current es true.
- Los identificadores de creación y modificación SCD corresponden al lote.
- La auditoría de modificación identifica la ejecución de inicialización.
- Las columnas originales conservan sus valores.
- gold_processing_run_id y gold_processed_at conservan la procedencia M9.

Cada entidad comienza con una sola versión actual.
El inicio representa una observación; no demuestra vigencia histórica
de negocio anterior a ese instante.

## Controles ejecutados

- Aceptación de M9 y correspondencia entre sus informes.
- Lectura de versiones Delta explícitas.
- Conteos y procedencia de las entradas.
- Claves iniciales positivas, no nulas y únicas.
- Conservación de las columnas originales antes de escribir.
- Comparación de tipos y valores después de persistir.
- Ausencia de referencias huérfanas desde fact_sales:
  cero para productos y cero para clientes.

La comprobación de ventas utiliza las claves heredadas.
No constituye una validación temporal de ventas anteriores a valid_from.

## Límites y operación

Los destinos originales de M9 y fact_sales no se modificaron.
Esta ejecución fue local; no inicializó dimensiones SCD en Azure.

Todavía no se aplicaron cambios tipo 1 ni tipo 2.
Las escrituras de ambas dimensiones son independientes y no forman
una transacción conjunta.

El ejecutor rechaza destinos existentes y reserva el informe mediante
creación exclusiva. No implementa recuperación automática de intentos
parciales ni reconocimiento de reintentos ya completados.

No debe repetirse la inicialización sobre este mismo lote.
Los siguientes procesos deberán partir de las copias aceptadas.
