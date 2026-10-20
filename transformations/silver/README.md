# Transformaciones a Silver

## Estrategia

Desarrollar y comprobar las transformaciones con Spark local.
Después ejecutarlas y validarlas en Azure Databricks.

La lógica utilizará DataFrames y rutas configurables.
La configuración de sesión permanecerá separada.

La carga SQL utilizará rutas explícitas de Bronze ya aceptadas en M5.
No se ampliará el lector de manifiestos en M7.
Los manifiestos existentes se conservan; su limpieza se abordará
después del primer release con Gold.

## Entorno local comprobado

- WSL Ubuntu.
- Python 3.12.3.
- OpenJDK 11.0.29.
- PySpark 3.5.8.
- Delta Lake 3.3.3.

Instalación desde la raíz, con el entorno virtual activo:

    python -m pip install -r requirements-spark-local.txt
    python -m pip check

Spark y Delta superaron pruebas locales de escritura y lectura.
Se verificó _delta_log y pip check no encontró incompatibilidades.
La configuración de prueba utilizó local[1], driver de 1 GiB y UTC.

## Esquemas SQL Server

sqlserver_schemas.py define los tipos de las cinco entidades.
Los importes utilizan DecimalType(18, 2), los indicadores BooleanType
y las fechas TimestampType.

Se comprobó la lectura de la copia de Bronze correspondiente a
ingestion_run_id=89d277f4-ddee-49a2-9d9f-588efacf9788.

| Entidad | Filas verificadas |
|---|---:|
| categories | 6 |
| products | 60 |
| customers | 500 |
| orders | 2000 |
| order_items | 5862 |
| Total | 8428 |

Las cinco entidades superaron tipos de lectura, conteos y ausencia
de nulos obligatorios. nullable=true en el esquema leído de Parquet
no sustituye la comprobación explícita de obligatoriedad.

## Validadores conservados

sqlserver_validation.py contiene cinco funciones:

| Función | Control |
|---|---|
| validate_primary_key | Claves informadas, positivas y únicas |
| validate_foreign_keys | Cuatro relaciones entre entidades |
| validate_business_values | Precios, cantidades, descuentos, estados y moneda |
| validate_record_timestamps | Fechas técnicas presentes y ordenadas |
| validate_order_completeness | Cada pedido tiene al menos una línea |

Los cinco controles se probaron con datos válidos e inválidos.
La carga inicial de Bronze superó sus comprobaciones.

Las funciones devuelven resultados sin modificar los datos.
El proceso de carga deberá bloquear la escritura si falla un control.

Los grupos duplicados cuentan combinaciones de clave repetidas.
Los incumplimientos de distintas reglas pueden solaparse;
no deben sumarse como si fueran registros diferentes.

## Simplificación de M7

Se retiraron del validador las comprobaciones detalladas de
almacenamiento de textos, claves alternativas, período inicial
y fechas entre líneas y pedidos.

Estas comprobaciones se ejecutaron durante el desarrollo.
Sus implementaciones anteriores permanecen en el historial de Git;
no formarán parte de la carga simplificada.

Se mantienen los cinco esquemas, los validadores esenciales
y la arquitectura prevista de ocho tablas Silver.

## Siguiente entregable

Integrar lectura, obligatoriedad, validación, procedencia,
escritura Delta y comparación de los datos recuperados.

La escritura inicial utilizará errorifexists.
Las escrituras de varias tablas no constituyen una transacción única;
una ejecución parcial no se declarará completada.

## Estado

Esquemas y validadores esenciales comprobados por separado.
Carga integrada y tablas Silver del proyecto pendientes.

Las pruebas locales no verifican permisos ni acceso a ADLS.
La ejecución integrada en Databricks sigue pendiente.

## Primera carga integrada local

sqlserver_transform.py reúne cuatro pasos:

1. Lectura de las cinco tablas con esquemas explícitos.
2. Validación integrada de 26 controles.
3. Incorporación de cinco columnas de procedencia.
4. Escritura Delta y comparación de tipos y valores recuperados.

La ejecución 1b1a6fd6-cb9b-4917-a651-20baeec5fd93 completó
la carga local con 8428 registros: 6 categorías, 60 productos,
500 clientes, 2000 pedidos y 5862 líneas.

Las comparaciones en ambas direcciones mediante exceptAll
no encontraron diferencias, incluidas las columnas técnicas.

Las tablas y report.json se conservaron en:
data/validation/silver_sqlserver/run_id=1b1a6fd6-cb9b-4917-a651-20baeec5fd93/

La comprobación corresponde a una ejecución local.
La ejecución en Databricks y el cierre de M7 siguen pendientes.

## Ejecución local

Desde la raíz del repositorio, con el entorno virtual activo:

    python -m transformations.silver.run_sqlserver_local \
        --bronze-root data/validation/bronze_download/sqlserver/techretail_oltp/initial/run_id=89d277f4-ddee-49a2-9d9f-588efacf9788 \
        --output-root data/validation/silver_sqlserver \
        --ingestion-run-id 89d277f4-ddee-49a2-9d9f-588efacf9788

El lanzador configura Spark y Delta locales y ejecuta lectura,
validación, procedencia, escritura y comparación de resultados.

Cada ejecución crea una carpeta nueva con processing_run_id.
No reemplaza las tablas de ejecuciones anteriores.
Esta separación permite repetir pruebas locales, no constituye
una implementación de actualización incremental.

Solo genera report.json con estado completed después de verificar
las cinco tablas. Un fallo puede dejar escrituras parciales.

La ejecución 52af9f2c-fb55-45c9-ba54-991e5dba4fc2 superó
26 controles y verificó 8428 registros en cinco tablas Delta.

## Productos de DummyJSON

dummyjson_schemas.py define los campos de lectura de las páginas JSON.
Para la extracción conservada, price utiliza DecimalType(18, 2)
y rating DecimalType(3, 2), suficientes para los valores inspeccionados.

dummyjson_transform.py implementa:

1. Lectura de páginas originales, excluyendo archivos de metadatos.
2. Extracción de una fila por producto mediante explode.
3. Normalización de nombres y adición de procedencia.
4. Validación de campos esenciales y unicidad de la clave.
5. Escritura Delta con errorifexists y comparación de tipos y valores.

Los campos opcionales ausentes permanecen nulos.
external_currency_code permanece nulo porque la fuente no declara moneda.
Los atributos externos no sustituyen los valores comerciales locales.

La ejecución cfe8f239-fdaf-404b-a629-7ca35d63eb2b leyó nueve páginas
y escribió 38 productos en external/dummyjson_products.
No se detectaron filas inválidas ni grupos duplicados.
La lectura Delta conservó los tipos y valores del DataFrame normalizado.

Las tablas y report.json se conservaron en:
data/validation/silver_dummyjson/run_id=cfe8f239-fdaf-404b-a629-7ca35d63eb2b/

La comprobación corresponde al entorno local.
El lanzador reutilizable y la ejecución en Databricks siguen pendientes.

## Ejecución local de DummyJSON

Desde la raíz del repositorio, con el entorno virtual activo:

    python -m transformations.silver.run_dummyjson_local \
        --bronze-root data/apis/dummyjson/products/ingestion_date=2026-10-11/run_id=172c6634-a566-4ae8-bfc7-04ae228dae77 \
        --output-root data/validation/silver_dummyjson \
        --ingestion-run-id 172c6634-a566-4ae8-bfc7-04ae228dae77

El lanzador ejecuta lectura, normalización, validación,
escritura Delta y comparación de resultados.
Rechaza entradas vacías y diferencias de conteo durante la normalización.

Cada ejecución utiliza una carpeta nueva.
El informe completed se genera después de verificar la tabla.

La ejecución e53042a4-f37f-4481-a27f-7cf83bea82ae verificó 38 productos,
sin filas inválidas ni grupos duplicados.
El lanzador local está implementado y comprobado.
La ejecución en Databricks permanece pendiente.

## Mapeo externo de productos

product_mapping_transform.py implementa:

1. Lectura del CSV versionado con esquema explícito.
2. Validación de campos, unicidad y referencias a ambos catálogos.
3. Incorporación de archivo de origen, ejecución y fecha de procesamiento.
4. Escritura Delta y comparación de tipos y valores recuperados.

La validación permite como máximo una asociación por producto local
y fuente externa, y una por producto externo.
No exige cobertura completa de los catálogos.

Las asociaciones son educativas y no implican equivalencia comercial.
source_system identifica el catálogo externo asociado.
No se asigna ingestion_run_id porque el mapeo procede del CSV versionado.

La ejecución e9f8cd2d-3780-4f66-933b-6cfd48b3acf7 verificó seis
asociaciones en reference/product_external_mapping.
No se detectaron campos inválidos, grupos duplicados ni referencias
inexistentes. La lectura Delta conservó los tipos y valores.

El informe registra las rutas de ambos catálogos utilizados.
La salida local se conservó en:
data/validation/silver_product_mapping/run_id=e9f8cd2d-3780-4f66-933b-6cfd48b3acf7/

El lanzador reutilizable y la ejecución en Databricks siguen pendientes.

## Ejecución local del mapeo

Desde la raíz del repositorio, con el entorno virtual activo:

    python -m transformations.silver.run_product_mapping_local \
        --mapping-file sources/reference/product_external_mapping.csv \
        --local-products data/validation/silver_sqlserver/run_id=52af9f2c-fb55-45c9-ba54-991e5dba4fc2/silver/techretail/products \
        --external-products data/validation/silver_dummyjson/run_id=e53042a4-f37f-4481-a27f-7cf83bea82ae/silver/external/dummyjson_products \
        --output-root data/validation/silver_product_mapping

El lanzador comprueba las rutas de entrada y rechaza mapeos vacíos.
Ejecuta validación, procedencia, escritura Delta y comparación.

Cada ejecución utiliza una carpeta nueva.
El informe registra las rutas de los catálogos utilizados
y solo declara completed después de verificar la tabla.

La ejecución cf0fd697-681d-4e44-ac2d-66ec8d01e396 verificó seis
asociaciones, sin incumplimientos en los cinco conteos de validación.

El lanzador local está implementado y comprobado.
La ejecución en Databricks permanece pendiente.

## Tasas de BCRPData

bcrpdata_schemas.py define el esquema de la respuesta JSON
y DecimalType(20, 14) para conservar las tasas sin redondearlas.

bcrpdata_transform.py implementa:

1. Lectura de una observación por fila.
2. Conversión de fechas con meses en español.
3. Conversión de tasas sin pérdida de precisión.
4. Adición de procedencia y fecha real de extracción.
5. Validación de fechas, tasas, disponibilidad y claves.
6. Escritura Delta y comparación de tipos y valores.

La serie PD04638PD representa el tipo de cambio interbancario
de venta, expresado en PEN por USD.

Los valores no disponibles conservan raw_value,
con rate_pen_per_usd nulo y available=false.
No se rellenan tasas ni se eliminan estas observaciones.

La ejecución 60e748db-73a1-4bf1-8a79-74e8b5715c62 verificó
195 observaciones: 184 disponibles y 11 no disponibles.
No se detectaron filas inválidas ni claves duplicadas.
La lectura Delta conservó los tipos y valores normalizados.

Los resultados locales se conservaron en:
data/validation/silver_bcrpdata/run_id=60e748db-73a1-4bf1-8a79-74e8b5715c62/

El lanzador reutilizable y la ejecución en Databricks
permanecen pendientes.
