# Construcción y validación local de Gold

## Alcance

Carga inicial de siete tablas Gold con PySpark y Delta locales.
Las entradas Silver se leen mediante rutas y versiones explícitas.
No se implementan actualizaciones incrementales ni historial SCD.

## Ejecución verificada

- Ejecución Gold: 815d77ca-1b31-40f4-b3b1-a6eeb9e23aa0.
- Carpeta: data/validation/gold/run_id=815d77ca-1b31-40f4-b3b1-a6eeb9e23aa0/.
- Informe de escritura: report.json.
- Estado de escritura: tables_verified.
- Informe de validación: validation-bcdb9336-3dd7-45f2-b3d9-1606c70cccd1.json.
- Estado de validación: passed.
- El informe de validación conserva el SHA-256 del informe de escritura.

El informe de escritura mantiene model_validation: pending.
La evidencia posterior está en el informe de validación independiente.
Ambos informes deben interpretarse conjuntamente.

## Tablas verificadas

| Tabla | Filas | Versión Delta |
|---|---:|---:|
| dim_product | 61 | 0 |
| dim_customer | 500 | 0 |
| dim_date | 730 | 0 |
| dim_order_status | 3 | 0 |
| ref_exchange_rates | 195 | 0 |
| product_catalog_mapping | 6 | 0 |
| fact_sales | 5862 | 0 |

Productos procede de Silver posterior a CDC, versión 4.
Las otras siete entradas Silver utilizan la versión 0.
El informe registra las rutas y los conteos de entrada.

## Controles aprobados

- Grano, claves únicas y relaciones dimensionales.
- Procedencia común en las siete tablas.
- Reconciliación por línea de contexto e importes PEN contra Silver.
- Selección cambiaria independiente para 274 fechas comerciales.
- Importes USD contrastados con fracciones exactas y HALF_UP.
- Seis asociaciones de catálogo y sus atributos reconciliados con Silver.

Se conservan 5759 líneas con conversión y 103 sin tasa aplicable.
El producto 61 está incluido sin crear ventas ficticias.

## Referencias comerciales comprobadas

| Control | Resultado |
|---|---:|
| Pedidos distintos | 2000 |
| Unidades totales | 14792 |
| Bruto total PEN | 21645086.45 |
| Descuento total PEN | 1667089.99 |
| Neto total PEN | 19977996.46 |
| Pedidos confirmados | 1578 |
| Unidades confirmadas | 11682 |
| Neto confirmado PEN | 15781257.30 |

Los totales incluyen todos los estados salvo indicación de confirmed.
Estas referencias corresponden a las entradas seleccionadas.

## Repetición local

Desde la raíz del repositorio, con el entorno virtual activo:

1. Ejecutar python -m transformations.gold.run_local
2. Identificar la ruta del nuevo report.json mostrada en la salida.
3. Ejecutar python -m transformations.gold.validate_local --report RUTA_DEL_NUEVO_REPORT_JSON

El constructor utiliza por defecto:
- Inventario: data/validation/gold_initial_inputs.json.
- Carpeta de salida: data/validation/gold.

Cada construcción crea una carpeta nueva y no sobrescribe tablas.
La escritura de las siete tablas no es una transacción conjunta.
Una ejecución parcial no se acepta como carga completa.

Los datos y los informes locales permanecen excluidos de Git.
Este documento registra la evidencia; no contiene los archivos Delta.

## Pendientes

- Construcción en Azure ejecutada y validada el 31 de octubre de 2026.
- Evidencia Azure y pendientes de cierre en
  [M9 — Modelo estrella y capa Gold](../modules/m9-gold-star-schema.md).

## Consultas SQL verificadas

Consultas Spark SQL en serving/spark_sql/:

- confirmed_sales_summary.sql: resumen confirmado, ticket promedio y cobertura USD.
- confirmed_sales_by_month_category.sql: ventas por mes comercial y categoría.
- orders_by_status.sql: distribución operativa por estado.

Resultados del resumen confirmado:

| Indicador | Resultado |
|---|---:|
| Líneas | 4607 |
| Pedidos distintos | 1578 |
| Unidades | 11682 |
| Neto PEN | 15781257.30 |
| Ticket promedio PEN | 10000.80 |
| Líneas con conversión | 4538 |
| Líneas sin conversión | 69 |
| Neto PEN sin conversión | 218881.86 |
| Neto USD convertido | 4572378.30 |

El total USD tiene cobertura parcial y no representa todas las ventas.

La agrupación por mes y categoría conserva líneas, unidades e importes.
Los pedidos distintos por categoría no se suman como total general.

La distribución por estado devuelve 209 pedidos pending, 1578 confirmed
y 213 cancelled. Un estado sin pedidos permanece con conteos cero.

Las consultas utilizan vistas temporales y no modifican las tablas Delta.
