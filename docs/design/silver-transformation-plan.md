# Plan de transformación a Silver

## Objetivo

Construir ocho tablas Delta a partir de las entradas verificadas,
con tipos explícitos, procedencia y controles de aceptación.

## Estrategia de ejecución

Desarrollar y validar las transformaciones con Spark y Delta locales.
Después ejecutar y verificar el proceso en Azure Databricks.

La lógica de transformación recibirá DataFrames.
Las rutas y la configuración de sesión permanecerán separadas.

Databricks Runtime 16.4 LTS es un candidato pendiente de confirmar.
La validación local no sustituye las pruebas del runtime seleccionado.

## Tablas previstas

| Ruta relativa a silver | Clave |
|---|---|
| techretail/categories/ | category_id |
| techretail/products/ | product_id |
| techretail/customers/ | customer_id |
| techretail/orders/ | order_id |
| techretail/order_items/ | order_id, line_number |
| external/dummyjson_products/ | source_system, external_product_id |
| reference/product_external_mapping/ | source_system, external_product_id |
| reference/exchange_rates/ | series_code, observation_date |

El mapeo también exige unicidad por producto local y fuente externa.

Las rutas de tablas serán estables.
No se particionarán inicialmente estas tablas pequeñas.

## Alcance inicial

Utilizar la carga inicial aceptada de SQL Server y las extracciones
conservadas de DummyJSON y BCRPData, junto con el mapeo versionado.

Conservar los valores comerciales de SQL Server.
Normalizar las API conforme a sus contratos.

Los lotes sintéticos incrementales permanecerán en Bronze.
La aplicación de eventos y el estado incremental corresponden a M8.

## Tipos de las tablas de SQL Server

Se conservarán los nombres y valores comerciales del origen.

| Campos | Tipo Spark |
|---|---|
| Identificadores, line_number y quantity | IntegerType |
| Textos | StringType |
| is_active | BooleanType |
| list_price, unit_price y discount_amount | DecimalType(18, 2) |
| created_at, updated_at y order_date | TimestampType |

Las fechas del origen representan UTC por convención.
La sesión de Spark utilizará UTC.

El Parquet de categories utiliza INT96 para las fechas.
Su lectura con TimestampType conservó exactamente los seis registros.
No requiere nanosAsLong ni división manual.

Las once columnas temporales de la carga inicial se comprobaron
con PyArrow: sus valores son representables en microsegundos sin pérdida.
La lectura completa con Spark se verificará para las cinco entidades.

La nulabilidad mostrada por el lector no sustituye las reglas
de obligatoriedad del contrato: se comprobarán explícitamente.

## Controles de aceptación de la carga SQL inicial

- Columnas y tipos compatibles con el contrato.
- Campos obligatorios presentes.
- Claves positivas y sin duplicados.
- Referencias entre las cinco entidades válidas.
- Fechas y reglas comerciales coherentes.
- Todos los pedidos con líneas válidas.
- Conteos y valores reconciliados contra la entrada aceptada.
- Importes y unidades coincidentes con los controles de M5.

No se corregirán valores comerciales por suposición.
Si falla un control requerido, la carga no se declarará aceptada.

La escritura y lectura Delta deberán conservar los valores de negocio.
La aceptación del conjunto completo requerirá comprobar las cinco tablas.

## Obligatoriedad y unicidad del origen SQL

Todos los campos comerciales de las cinco tablas son obligatorios.
La nulabilidad del esquema de lectura no autoriza valores nulos.

Se comprobarán también las claves alternativas:

- categories: category_name.
- products: sku.
- customers: email.

La comparación de textos deberá definir explícitamente su tratamiento
respecto a la intercalación del origen; no se supondrá equivalencia
entre la comparación de Spark y la de SQL Server.

## Procedencia de las tablas SQL

Cada registro incorporará estas columnas técnicas:

| Columna | Tipo | Significado |
|---|---|---|
| source_system | StringType | sqlserver |
| ingestion_run_id | StringType | Ejecución aceptada de Bronze |
| processing_run_id | StringType | Ejecución de transformación |
| source_file | StringType | Archivo de entrada |
| processed_at | TimestampType | Inicio del procesamiento en UTC |

El mismo processing_run_id y processed_at se utilizarán para las
cinco tablas de una ejecución.

Las fechas técnicas no reemplazan created_at, updated_at ni order_date.
En local, source_file identificará la copia utilizada.
En Azure, identificará el archivo leído desde ADLS.

## Política de escritura inicial

M7 creará las tablas con errorifexists.
No se utilizará append ni overwrite para repetir la carga inicial.

Las rutas Silver cloud serán las rutas estables del diseño.
Las pruebas locales utilizarán carpetas nuevas y separadas de Bronze.

Todos los controles previos deberán pasar antes de iniciar las escrituras.
Después se leerán las tablas Delta y se reconciliarán sus valores.

Las escrituras de distintas tablas no constituyen una transacción única.
Una ejecución parcial no se declarará aceptada ni habilitará el avance
a Gold. Su recuperación requerirá un procedimiento explícito.

La actualización incremental de tablas existentes corresponde a M8.

## Estado

Alcance de ocho tablas definido.
Tipos, controles, procedencia y escritura inicial definidos para SQL Server.
Lectura de categories comprobada con Spark local.

Contratos detallados de API y mapeo pendientes.
Implementación de transformaciones y validación integrada pendientes.
