# M9 — Modelo estrella y capa Gold

## Resultado

Se construyó y verificó una carga inicial de siete tablas Gold,
primero en local y después en Azure Databricks, desde ocho entradas Silver.

Las tablas se guardaron en ADLS Gen2 como Delta y se registraron
como tablas externas en Unity Catalog.

## Alcance implementado

- Cuatro dimensiones: producto, cliente, fecha y estado del pedido.
- Hechos de ventas con grano por order_id y line_number.
- Referencia de tasas de cambio PEN por USD.
- Asociaciones educativas entre productos locales y catálogo externo.
- Importes PEN y USD, con neto USD calculado por diferencia.
- Selección de tasas según fecha comercial y antigüedad permitida.
- Procedencia común e informe de ejecución.
- Consultas individuales, controles y análisis por categoría.

La fecha comercial se interpreta en America/Lima.
Los timestamps de procesamiento y la sesión Spark utilizan UTC.
Solo los estados con counts_as_sale = true cuentan como ventas.

## Ejecución aceptada en Azure

- Fecha: 31 de octubre de 2026.
- Workspace: dbw-arlp-dev-diego01.
- Cómputo: cmp-arlp-dev-silver.
- Runtime: 16.4 LTS.
- Ejecución: 953a045c-f46b-4f1a-bb98-5003f14b6930.
- Procesamiento UTC: 2026-10-31T21:54:24.609780+00:00.
- Finalización UTC: 2026-10-31T22:09:47.649436+00:00.
- Estado final: completed.
- Registro: passed.

Informe persistido:

abfss://gold@starlpdevdiego01.dfs.core.windows.net/_executions/run_id=953a045c-f46b-4f1a-bb98-5003f14b6930/report.json

## Entradas Silver de Azure

| Entrada | Versión Delta | Filas |
|---|---:|---:|
| categories | 0 | 6 |
| products | 1 | 61 |
| customers | 0 | 500 |
| orders | 0 | 2000 |
| order_items | 0 | 5862 |
| dummyjson_products | 0 | 38 |
| product_external_mapping | 0 | 6 |
| exchange_rates | 0 | 195 |

La numeración de versiones Delta es propia de cada tabla y entorno.
La versión 4 de productos utilizada en local no sustituye a la
versión 1 verificada en Azure.

## Tablas Gold verificadas

Catálogo: dbw_arlp_dev_diego01.

| Esquema | Tabla | Filas | Versión Delta inicial |
|---|---|---:|---:|
| gold_sales | dim_product | 61 | 0 |
| gold_sales | dim_customer | 500 | 0 |
| gold_sales | dim_date | 730 | 0 |
| gold_sales | dim_order_status | 3 | 0 |
| gold_sales | fact_sales | 5862 | 0 |
| gold_reference | ref_exchange_rates | 195 | 0 |
| gold_reference | product_catalog_mapping | 6 | 0 |

Las cinco tablas comerciales se almacenan bajo gold/sales.
Las dos referencias se almacenan bajo gold/reference.
El producto 61 incorporado mediante CDC está presente en dim_product.

## Controles aprobados

El notebook de construcción verificó los tipos y valores recuperados
desde Delta, ejecutó la validación del modelo persistido y comprobó
la coincidencia de las consultas por Unity Catalog.

El notebook de consultas verificó adicionalmente:

- Conteos completos de las siete tablas.
- Claves no nulas y únicas en las cuatro dimensiones.
- Grano único de ventas por pedido y línea.
- Clave compuesta de tasas por serie y fecha.
- Correspondencia de ventas con las cuatro dimensiones.
- Consistencia básica de cantidades e importes PEN y USD.
- Consultas individuales de las siete tablas.
- Análisis de ventas confirmadas por categoría.

LIMIT 20 solo restringe las muestras de consulta.
Las validaciones recorren las tablas completas.
Los controles básicos de importes del segundo notebook no sustituyen
la reconciliación completa del constructor.

## Interpretación analítica

- Pendiente y cancelado se conservan en hechos, pero no cuentan como venta.
- Los pedidos distintos por categoría no se suman como total general.
- La conversión USD puede tener cobertura parcial.
- Una tasa no disponible se conserva como NULL, nunca como cero.
- Las seis asociaciones de catálogo son synthetic_demo.
- La moneda externa permanece NULL; no se presupone USD ni
  equivalencia comercial entre productos.

## Incidencia y recuperación

El intento 02b3ed01-6c68-4fb0-a027-67c31bb1c0a6 falló con:
[UNSUPPORTED_OPERATION] errorifexists is not supported.

Se cambió el modo de escritura a error en storage.py, commit 226d8b7.
Se actualizó la carpeta Git y se recargó la función en Databricks.

Antes de reintentar se comprobó que sales y reference no existían.
Se generó un nuevo identificador y se conservó el informe fallido.
La nueva ejecución completó escritura, validación y registro.

La advertencia de ventanas sin partición no impidió la ejecución.
Su rendimiento debe revisarse antes de aumentar significativamente el volumen.

## Artefactos principales

- notebooks/gold/01_silver_to_gold.ipynb.
- notebooks/gold/02_gold_queries_and_validation.ipynb.
- transformations/gold/storage.py.
- serving/spark_sql/.

Referencias:

- [Plan Gold](../design/gold-star-schema-plan.md).
- [Ejecución local](../design/gold-local-execution.md).

## Operación y costos

La ubicación externa loc_arlp_gold utiliza cred_arlp_adls.
La identidad del Access Connector recibió Storage Blob Data Contributor
sobre el contenedor gold. File events y fallback quedaron desactivados.
La prueba de conexión confirmó los permisos necesarios.

Al finalizar:

- El clúster quedó detenido.
- Se eliminaron nat-arlp-dev-databricks y pip-arlp-dev-databricks.
- Se conservaron VNet, subredes, NSG, workspace, identidad y datos.
- El grupo rg-arlp-dev quedó con siete recursos.

Antes de volver a utilizar el cómputo clásico debe restablecerse
la conectividad de salida.

El costo definitivo de la sesión queda pendiente de revisión
cuando Azure Cost Management refleje sus consumos.

## Limitaciones y estado

Carga inicial manual; sin actualización incremental Gold ni historial SCD.
Las escrituras entre tablas no forman una transacción conjunta.
El notebook de construcción no debe repetirse sobre destinos existentes.
Una ejecución parcial requiere revisar la recuperación.

Implementación y ejecución local y Azure verificadas.
M9 integrado en main mediante el
[PR #17](https://github.com/DiegoSuarz/azure-retail-lakehouse-platform/pull/17),
commit 8bf7398.
La revisión del costo definitivo permanece pendiente.

El siguiente módulo previsto es M10: dimensiones con SCD tipo 1 y tipo 2.
