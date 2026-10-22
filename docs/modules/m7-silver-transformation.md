# M7 — Transformaciones PySpark y tablas Delta en Silver

## Resultado

Se ejecutó la carga inicial de ocho tablas Silver en Azure Databricks.
Los datos se conservaron en Delta Lake dentro de ADLS Gen2
y se registraron como tablas externas en Unity Catalog.

Las cargas se ejecutaron manualmente desde cuatro notebooks,
reutilizando los módulos de transformations/silver/.

## Servicios y herramientas

| Componente | Uso |
|---|---|
| Azure Databricks Premium, Hybrid | Ejecutar las transformaciones |
| Runtime 16.4 LTS y Spark 3.5.2 | Procesamiento PySpark |
| ADLS Gen2 | Conservar Bronze y Silver |
| Access Connector e identidad administrada | Autenticación al almacenamiento |
| Unity Catalog | Credencial, ubicaciones externas y tablas |
| GitHub y carpeta Git de Databricks | Versionar módulos y notebooks |

El cómputo cmp-arlp-dev-silver utilizó un único nodo
Standard_D4ds_v4, sin Photon y con zona horaria UTC.

La configuración de red y permisos se describe en
[Infraestructura Databricks](../../infrastructure/databricks/README.md).

## Flujo implementado

1. Leer las entradas conservadas o el CSV de referencia versionado.
2. Aplicar los esquemas y transformaciones correspondientes.
3. Validar los datos antes de escribir.
4. Añadir procedencia e identificador de procesamiento.
5. Escribir Delta sin sobrescribir destinos existentes.
6. Recuperar los datos y comparar tipos y valores.
7. Registrar las tablas existentes en Unity Catalog.

El registro en Unity Catalog no copia ni reescribe los datos.

## Resultados verificados

Catálogo: dbw_arlp_dev_diego01.

| Esquema | Tabla | Filas |
|---|---|---:|
| silver_techretail | categories | 6 |
| silver_techretail | products | 60 |
| silver_techretail | customers | 500 |
| silver_techretail | orders | 2000 |
| silver_techretail | order_items | 5862 |
| silver_external | dummyjson_products | 38 |
| silver_reference | product_external_mapping | 6 |
| silver_reference | exchange_rates | 195 |
| Total | | 8667 |

- SQL Server superó 26 controles integrados.
- DummyJSON conservó 38 productos procedentes de nueve archivos.
- El mapeo validó seis asociaciones contra ambos catálogos.
- BCRPData conservó 184 tasas disponibles y 11 no disponibles.
- Las ocho tablas superaron la comparación posterior a la escritura.
- Se comprobaron consultas por nombre mediante Unity Catalog.

Las comparaciones de valores utilizaron exceptAll en ambas direcciones,
incluyendo duplicados y columnas de procedencia.

Los identificadores de las cuatro ejecuciones se encuentran en
[Transformaciones Silver](../../transformations/silver/README.md).

## Decisiones y compatibilidad

- mode("error") evita sobrescribir destinos existentes.
- _metadata.file_path conserva la ruta de los archivos JSON.
- Storage Blob Delegator se asignó a nivel de cuenta.
- Los permisos de datos se limitaron por contenedor.
- Las cargas completadas utilizaron cómputo clásico.
- La moneda de DummyJSON permanece nula: la fuente no la declara.
- Las tasas no disponibles permanecen nulas y conservan raw_value.
- Las asociaciones del mapeo son educativas, no equivalencias comerciales.

No se utilizaron claves compartidas del almacenamiento.

## Notebooks

Ubicación: notebooks/silver/.

- 01_sqlserver_to_silver.ipynb.
- 02_dummyjson_to_silver.ipynb.
- 03_product_mapping_to_silver.ipynb.
- 04_bcrpdata_to_silver.ipynb.

Los notebooks se versionaron sin salidas de ejecución.

La ejecución cloud se verificó antes de reubicarlos.
Después del movimiento se ajustaron importaciones y ruta del CSV,
y se comprobó la sintaxis de las celdas.
Las nuevas rutas aún no se han probado en Databricks.

## Alcance y limitaciones

Es una carga inicial; no implementa CDC, MERGE ni actualización incremental.
Las escrituras entre tablas son independientes.
Un fallo puede dejar tablas ya escritas y requiere revisión.

No debe repetirse Run all sobre los destinos existentes:
el modo de escritura bloqueará su sobrescritura.

La ejecución no está automatizada mediante ADF ni Jobs.
Los controles de M6 no se integraron como un flujo automático
de clasificación y publicación de cuarentena en estos notebooks.

Los manifiestos y lanzadores locales existentes se conservan.
Su limpieza se realizará después del primer release con Gold.

## Operación y costos

El clúster quedó detenido al finalizar la sesión.
Los datos Delta y el registro de tablas permanecen conservados.

El NAT Gateway y su IP pública siguen desplegados.
Sus cargos son independientes del estado del clúster.

La estimación previa no representa el gasto real de la sesión.
La revisión de consumos efectivos y la retirada temporal de red
siguen pendientes.

## Estado

Carga inicial Silver verificada en Azure y registrada en Unity Catalog.
Código y notebooks publicados en feature/m7-silver-transformation.

Pendientes de cierre:
- Verificar las rutas e importaciones de los notebooks reubicados.
- Revisar el diff final y completar la revisión operativa.
- Integrar la rama en main mediante pull request.

El siguiente módulo previsto es M8:
CDC simulado, incrementales e idempotencia.
