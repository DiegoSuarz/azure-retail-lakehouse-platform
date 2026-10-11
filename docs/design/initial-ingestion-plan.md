# Plan de ingesta inicial de SQL Server

## Objetivo

Extraer las cinco tablas de TechRetail_OLTP a Bronze mediante ADF
y SHIR, conservando los valores del origen en archivos Parquet.

## Conexiones

- Origen: ls_sqlserver_local.
- Destino: ls_adls_gen2.
- Integration Runtime: shir-arlp-dev-local.
- Usuario SQL: retail_reader.
- Contraseña: referencia existente a Key Vault.
- Contenedor de destino: bronze.

## Identidad y rutas

ingestion_run_id utilizará el RunId del pipeline de ADF.

Ruta relativa al contenedor bronze:

    sqlserver/techretail_oltp/initial/run_id=<ingestion_run_id>/<entity>/

Las entidades serán categories, products, customers, orders
y order_items.

Cada entidad contendrá los archivos Parquet de su extracción.
Se registrarán los nombres reales de los archivos generados.

Cada nueva ejecución utilizará una ruta diferente.
No se sobrescribirán ejecuciones anteriores.

## Consistencia del origen

La primera carga utilizará una ventana sin escrituras sobre
las cinco tablas durante la extracción y la validación.

No se ejecutará el cargador inicial ni se aplicarán cambios
manuales o automáticos durante esa ventana.

Las copias se realizarán inicialmente de forma secuencial.
Este orden no sustituye una instantánea transaccional.

Si se detectan escrituras durante la ventana, la ejecución
no se aceptará como carga inicial coherente.

Los archivos incrementales permanecerán separados del origen SQL.

## Corte y fechas

El conjunto sintético inicial tiene como corte exclusivo:

    2026-10-01T00:00:00.000Z

Este corte describe los datos generados, no representa
el instante real de extracción ni una marca de agua técnica.

Se registrarán por separado el inicio y el fin de extracción en UTC.

Los valores datetime2 del origen representan UTC por convención,
aunque el tipo de SQL Server no almacena una zona horaria.

## Controles de referencia

| Tabla | Filas esperadas |
|---|---:|
| categories | 6 |
| products | 60 |
| customers | 500 |
| orders | 2000 |
| order_items | 5862 |

Controles comerciales del conjunto inicial:

- Pedidos pending: 209.
- Pedidos confirmed: 1578.
- Pedidos cancelled: 213.
- Importe bruto de todas las líneas: PEN 21645086.45.
- Descuento de todas las líneas: PEN 1667089.99.
- Importe neto de todas las líneas: PEN 19977996.46.
- Importe neto confirmado: PEN 15781257.30.
- Unidades totales: 14792.
- Unidades confirmadas: 11682.

Estos valores se verificarán en SQL Server antes de la extracción.
Si difieren, se investigará la causa antes de continuar.

## Validación del destino

La validación leerá los Parquet y comprobará:

- Conteos por entidad contra SQL Server.
- Columnas y compatibilidad de tipos.
- Claves primarias sin duplicados.
- Relaciones entre las cinco entidades.
- Valores de los registros contra el origen por clave.
- Distribución de estados de pedidos.
- Importes y unidades contra los controles de referencia.

Los importes conservarán precisión decimal.
Las fechas se compararán por su valor, no por su formato visual.

La cantidad de filas reportada por Copy se registrará como evidencia,
pero no sustituirá la lectura y validación de los archivos.

## Manifiesto de extracción

Se generará manifest.json en la raíz de la ejecución.

Registrará:

- Versión del formato del manifiesto.
- ingestion_run_id.
- Sistema de origen y base de datos.
- Corte del conjunto sintético.
- Inicio y fin de extracción en UTC.
- Método utilizado para mantener la consistencia.
- Entidades, archivos, tamaños y hashes SHA-256.
- Conteos de origen, copia y destino.
- Resultados de reconciliación.
- Estado de finalización.

Será distinto del manifiesto de generación local de M2.

La especificación exacta y el mecanismo de generación se concretarán
antes de ejecutar la carga completa.

## Fallos y finalización

Una ejecución solo se marcará completa cuando las cinco tablas
se hayan copiado y todos los controles requeridos se superen.

Las ejecuciones parciales o fallidas no se utilizarán como
entrada aceptada para Silver.

La existencia de carpetas o archivos no implica una carga completa.

Los archivos parciales se identificarán para revisión y limpieza.
Una nueva ejecución utilizará otro ingestion_run_id.

## Costos

La ejecución generará consumo de ADF, acceso a Key Vault
y operaciones de almacenamiento.

Los archivos conservarán un cargo por capacidad mientras existan.
Se evitarán ejecuciones repetidas sin un objetivo de validación.

Esta etapa no requiere desplegar Databricks.

## Estado

Plan definido en M5.1.
Datasets y pipeline publicados en ADF.
Referencia local del origen capturada y controles de M2 verificados.
Ejecución completa, validación de Parquet y manifiesto pendientes.
