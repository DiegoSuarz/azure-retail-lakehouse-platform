# M10 — Dimensiones con SCD tipo 1 y tipo 2

## Resultado

Se implementó un flujo SCD para dim_product y dim_customer,
preservando las claves heredadas de M9 y sus referencias desde fact_sales.

La lógica fue probada localmente y demostrada en Azure Databricks
sobre copias separadas de las dimensiones aceptadas.

Las entradas de cambios de las demostraciones son sintéticas.
No constituyen una nueva ingesta real desde Silver.
Las tablas originales de M9 permanecen sin modificaciones.

## Reglas implementadas

| Dimensión | Tipo 1 | Tipo 2 |
|---|---|---|
| Producto | product_name, brand | category_id, category_name, list_price, is_active |
| Cliente | first_name, last_name | city, region, is_active |

product_id y customer_id identifican entidades de negocio.
product_key y customer_key identifican versiones dimensionales.

El SKU de un producto existente se considera estable:
un cambio se bloquea para revisión.

Las correcciones tipo 1 se propagan a las versiones afectadas del historial.
Los cambios tipo 2 cierran la versión actual y generan una clave nueva.
Una ausencia en la entrada no implica una baja.

## Contrato temporal

Las vigencias representan estados observados, no una reconstrucción
de la historia efectiva del negocio.

- Timestamps normalizados a UTC.
- Inicio incluido y fin excluido.
- valid_to nulo para la versión actual.
- Exactamente una versión actual por entidad.
- Intervalos contiguos, sin huecos ni solapamientos.
- is_active independiente de is_current.

Los estados intermedios no observados no se reconstruyen automáticamente.

## Organización del código

| Archivo | Responsabilidad |
|---|---|
| scd_transform.py | Reglas, detección, preparación y validación temporal |
| scd_storage.py | Lectura versionada y aplicación mediante MERGE Delta |
| run_scd_local.py | Coordinación de la ejecución local |
| scd_initialization.py | Preparación inicial conservando las claves M9 |
| run_scd_initialization_local.py | Inicialización local persistida y verificada |
| scd_sales_keys.py | Resolución temporal y validación de ventas heredadas |

El notebook notebooks/gold/03_scd_dimensions.ipynb reutiliza estas funciones
para la demostración en Azure.

## Validación local

La inicialización aceptada conservó 61 productos y 500 clientes,
además de las referencias de 5862 líneas de ventas M9.

Las demostraciones sintéticas procesaron dos lotes consecutivos
por dimensión, con correcciones, nuevas versiones, altas y bajas lógicas.

Cada destino de demostración terminó con siete filas en versión Delta 2.
Se comprobaron repeticiones sin cambios y rechazos de historiales inválidos.

La resolución temporal de claves para ventas nuevas se probó localmente,
incluyendo límites exactos, versiones cerradas y coincidencias ambiguas.

## Ejecución aceptada en Azure

- Fecha: 7 de noviembre de 2026.
- Workspace: dbw-arlp-dev-diego01.
- Cómputo: cmp-arlp-dev-silver.
- Runtime: 16.4 LTS.
- Ejecución: 1e03e712-4ccf-4c81-a2c6-f6d258b5e894.
- Base M9: 953a045c-f46b-4f1a-bb98-5003f14b6930.
- Estado del informe: completed.

| Dimensión | Filas iniciales | Filas finales | Actuales | Versión final |
|---|---:|---:|---:|---:|
| dim_product | 61 | 64 | 62 | 1 |
| dim_customer | 500 | 503 | 501 | 1 |

Por dimensión se aplicaron una corrección tipo 1, un cambio tipo 2,
un cambio combinado y un alta.

Se verificaron el resultado persistido, el historial y las referencias
heredadas antes y después de los cambios.

La repetición clasificó 62 productos y 501 clientes como unchanged.
Ambos destinos conservaron la versión Delta 1, sus valores y auditoría.

La resolución temporal de ventas nuevas no se ejecutó en esta
demostración de Azure. No se escribieron ventas.

El control de ventas heredadas utiliza la misma base aceptada como
entrada y referencia; no compara dos copias independientes de hechos.

## Catálogo complementario

product_catalog_mapping conserva la fotografía aceptada de M9.
Su product_key identifica la versión original.

Para consumo actual se utiliza product_id y la versión dimensional actual.
Desde ventas se resuelve primero la product_key histórica.

La asociación externa no dispone de historial temporal.
Debe controlarse la multiplicidad de asociaciones antes de agregar ventas.

## Servicios y recursos utilizados

- Azure Databricks: ejecución PySpark y operaciones Delta.
- ADLS Gen2: tablas, entradas sintéticas e informe persistido.
- Azure NAT Gateway e IP pública Standard: salida de red del cómputo.
- Azure CLI: creación, asociación y retirada de los recursos de red.
- Git y GitHub: control de versiones del código y la documentación.

Las copias SCD se consultan por ruta.
El notebook no las registra como nuevas tablas en Unity Catalog.

Después de la demostración se detuvo el cómputo y se eliminaron
el NAT y su IP pública. Se verificaron ambas subredes sin NAT asociado.

## Aprendizajes y conclusiones

Separar claves de negocio y claves de versión permite conservar
las relaciones de hechos mientras evoluciona la dimensión.

Las correcciones descriptivas y los cambios históricos tienen efectos
distintos sobre las consultas y deben definirse por atributo.

Un MERGE por dimensión aplica cierres e inserciones de forma conjunta.
La igualdad con el estado actual evita escrituras y cambios de auditoría.

El alcance simplificado permitió mantener un flujo comprensible,
con garantías y límites explícitos.

## Límites operativos

- Un único escritor por dimensión.
- Versiones Delta de entrada y partida explícitas.
- Sin transacción conjunta entre tablas.
- Sin registro persistente de identidad de lotes.
- Sin recuperación automática después de fallos.
- Sin control global persistente del orden de las observaciones.

La repetición idéntica al estado actual no equivale a reconocer
cualquier lote histórico ya aplicado.
Los fallos parciales y las entradas antiguas requieren revisión manual.

## Evidencias

- [Plan y reglas](../design/scd-dimensions-plan.md)
- [Contrato temporal](../design/scd-temporal-contract.md)
- [Claves y versiones](../design/scd-version-structure.md)
- [Inicialización local](../design/scd-initialization-local.md)
- [Ventas y resolución temporal](../design/scd-sales-key-resolution.md)
- [Demostraciones locales](../design/scd-local-execution.md)
- [Demostración Azure](../design/scd-azure-execution.md)

## Estado de cierre

Implementación y comprobaciones locales y Azure documentadas.
Registro de cierre preparado en feature/m10-scd-dimensions.

Integración en main y revisión del costo definitivo pendientes.
El siguiente módulo previsto es M11.
