# Ejecución SCD en Azure

## Alcance

Demostración de cambios SCD tipo 1 y tipo 2 sobre copias separadas
de las dimensiones Gold aceptadas de M9.

Las entradas de cambios son sintéticas.
No representan una nueva ingesta desde Silver.
Las tablas originales de M9 no se modificaron.

## Entorno y ejecución

- Fecha: 7 de noviembre de 2026.
- Workspace: dbw-arlp-dev-diego01.
- Cómputo: cmp-arlp-dev-silver.
- Runtime: 16.4 LTS.
- Notebook: notebooks/gold/03_scd_dimensions.ipynb.
- Commit preparado: f7f2541.
- Ejecución SCD: 1e03e712-4ccf-4c81-a2c6-f6d258b5e894.
- Ejecución M9 de origen: 953a045c-f46b-4f1a-bb98-5003f14b6930.
- Estado final del informe: completed.

## Evidencia persistida

Raíz de la demostración:

abfss://gold@starlpdevdiego01.dfs.core.windows.net/scd/run_id=1e03e712-4ccf-4c81-a2c6-f6d258b5e894

El informe se encuentra en report.json bajo esa raíz.
Las dimensiones se conservan en tables/dim_product y tables/dim_customer.
Las entradas sintéticas se guardaron en inputs/demo-1 en versión Delta 0.

## Inicialización

Se leyeron versiones Delta explícitas del informe M9:

| Tabla | Filas | Versión |
|---|---:|---:|
| dim_product | 61 | 0 |
| dim_customer | 500 | 0 |
| fact_sales | 5862 | 0 |

Las copias dimensionales comenzaron en versión Delta 0.
Se conservaron las columnas originales y se añadieron vigencias
y auditoría SCD.

Observación inicial UTC: 2026-11-07T17:45:01.082819+00:00.

## Aplicación del lote

Lote: 1e03e712-4ccf-4c81-a2c6-f6d258b5e894-demo-1.

Intento: 065e0e10-6b20-42e5-9c66-98bf2f34e3da.

Observación UTC: 2026-11-07T17:50:20.405768+00:00.

| Dimensión | Tipo 1 | Tipo 2 | Combinado | Alta | Sin cambios |
|---|---:|---:|---:|---:|---:|
| Productos | 1 | 1 | 1 | 1 | 58 |
| Clientes | 1 | 1 | 1 | 1 | 497 |

Se corrigieron nombres y se modificaron precios de catálogo
o ubicaciones, según la dimensión.
Los cambios combinados incluyeron atributos tipo 1 y tipo 2.

Cada dimensión se aplicó mediante un MERGE independiente.

| Dimensión | Filas finales | Versiones actuales | Versión Delta |
|---|---:|---:|---:|
| dim_product | 64 | 62 | 1 |
| dim_customer | 503 | 501 | 1 |

El resultado persistido coincidió con el preparado.
Los controles del historial temporal finalizaron correctamente.

## Referencias de ventas heredadas

Antes y después de los cambios se verificaron las referencias
de las 5862 líneas de ventas M9.

Las claves heredadas continuaron identificando las mismas entidades,
incluidas las versiones dimensionales cerradas.

La comprobación utilizó la misma tabla aceptada como referencia
y entrada de ventas; no compara dos copias independientes de hechos.
No se escribieron ventas ni se aplicó resolución temporal a ventas nuevas
en esta demostración de Azure.

## Repetición sin cambios

Intento: e0d85e13-7ab3-4eae-96f5-baa7dff3d152.

| Dimensión | Entidades sin cambios | Filas | Versión conservada |
|---|---:|---:|---:|
| dim_product | 62 | 64 | 1 |
| dim_customer | 501 | 503 | 1 |

Ambos resultados devolvieron changed: false y verified: true.
Se conservaron los valores y la auditoría sin otro commit Delta.

Finalización UTC: 2026-11-07T17:56:04.499040+00:00.

## Operación y límites

- Vigencias basadas en estados observados.
- Un único escritor por dimensión.
- Sin transacción conjunta entre productos y clientes.
- Sin reconocimiento persistente de lotes históricos por batch_id.
- Sin recuperación automática de fallos.
- Las entradas antiguas y los fallos parciales requieren revisión manual.
- Las copias SCD se consultan por ruta; este notebook no las registra
  como nuevas tablas de Unity Catalog.

## Cierre de recursos

Después de completar la demostración:

- Cómputo cmp-arlp-dev-silver detenido.
- NAT nat-arlp-dev-databricks desvinculado de ambas subredes y eliminado.
- IP pública pip-arlp-dev-databricks eliminada.
- Ambas subredes verificadas con NAT nulo.
- Consulta de recursos temporales sin resultados.

Los datos y el informe permanecen en ADLS.
La revisión del costo definitivo queda pendiente.

## Estado

Demostración SCD en Azure completada y verificada.
Pendientes el cierre general de M10 y su integración en main.
