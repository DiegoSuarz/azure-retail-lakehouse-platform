# Transformaciones a Silver

## Estrategia

Las transformaciones se desarrollarán y comprobarán con Spark local.
Después se ejecutarán y validarán en Azure Databricks.

La lógica utilizará DataFrames y rutas configurables.
La configuración de sesión se mantendrá separada de las transformaciones.

## Entorno local comprobado

- WSL Ubuntu.
- Python 3.12.3.
- OpenJDK 11.0.29.
- PySpark 3.5.8.
- Delta Lake 3.3.3.

Instalación desde la raíz, con el entorno virtual activo:

    python -m pip install -r requirements-spark-local.txt
    python -m pip check

La prueba utilizó local[1], driver de 1 GiB y zona horaria UTC.

## Comprobaciones realizadas

- Spark procesó cinco registros.
- Delta escribió y leyó los cinco valores sin diferencias.
- Se comprobó la presencia de _delta_log.
- La tabla temporal se eliminó al finalizar.
- pip check no encontró dependencias incompatibles.

## Estado

Entorno local verificado.
Contratos Silver y transformaciones pendientes.

La prueba local no verifica permisos ni acceso a ADLS.
La ejecución integrada en Databricks sigue pendiente.

## Esquemas de la carga inicial SQL Server

sqlserver_schemas.py define los esquemas explícitos de las cinco entidades.
Los importes utilizan DecimalType(18, 2), los indicadores BooleanType
y las fechas TimestampType con la sesión configurada en UTC.

Se comprobó localmente la lectura de la copia de Bronze correspondiente
a ingestion_run_id=89d277f4-ddee-49a2-9d9f-588efacf9788.

| Entidad | Filas verificadas |
|---|---:|
| categories | 6 |
| products | 60 |
| customers | 500 |
| orders | 2000 |
| order_items | 5862 |
| Total | 8428 |

Las cinco entidades superaron las comprobaciones de tipos de lectura,
conteos y ausencia de nulos en campos obligatorios.

El lector Parquet devuelve campos nullable=true.
La obligatoriedad se comprobó sobre los datos explícitamente.

Esta comprobación no acredita todavía unicidad, relaciones,
reglas comerciales ni igualdad completa de valores.
No se escribieron tablas Silver.

## Validación de claves

sqlserver_validation.py implementa controles sobre DataFrames:

- Claves primarias informadas, positivas y únicas.
- Clave compuesta de order_items: order_id y line_number.
- Referencias de productos a categorías.
- Referencias de pedidos a clientes.
- Referencias de líneas a pedidos y productos.

Las cinco entidades de la carga inicial superaron los controles
de claves primarias: cero filas con claves inválidas y cero
grupos de claves duplicadas.

Las cuatro relaciones superaron los controles de claves foráneas:
cero filas sin referencia.

Se probaron claves simples y compuestas válidas, inválidas y repetidas.
Los controles de referencias se probaron con claves existentes,
inexistentes, nulas y filas repetidas sin referencia.

Los grupos duplicados cuentan combinaciones de clave repetidas.
Las referencias inexistentes cuentan filas afectadas.

Estas comprobaciones no acreditan todavía las claves alternativas,
las reglas comerciales ni la conservación completa de valores.

## Validación de valores comerciales

validate_business_values comprueba:

- list_price mayor que cero.
- Estados pending, confirmed o cancelled.
- Moneda PEN.
- quantity y unit_price mayores que cero.
- discount_amount entre cero y el importe bruto de la línea.

Las seis reglas superaron la comprobación de la carga inicial,
sin filas inválidas.

Se probaron valores nulos, cero, negativos, estados y monedas
incompatibles, y descuentos fuera del intervalo permitido.
Los descuentos cero e iguales al importe bruto son válidos.

Los incumplimientos se cuentan por regla.
Una fila puede incumplir varias reglas; sus conteos no representan
categorías mutuamente excluyentes.

Las reglas temporales y la existencia de líneas por pedido
siguen pendientes.

## Validación de valores comerciales

validate_business_values comprueba:

- list_price mayor que cero.
- Estados pending, confirmed o cancelled.
- Moneda PEN.
- quantity y unit_price mayores que cero.
- discount_amount entre cero y el importe bruto de la línea.

Las seis reglas superaron la comprobación de la carga inicial,
sin filas inválidas.

Se probaron valores nulos, cero, negativos, estados y monedas
incompatibles, y descuentos fuera del intervalo permitido.
Los descuentos cero e iguales al importe bruto son válidos.

Los incumplimientos se cuentan por regla.
Una fila puede incumplir varias reglas; sus conteos no representan
categorías mutuamente excluyentes.

Las reglas temporales y la existencia de líneas por pedido
siguen pendientes.

## Fechas técnicas por registro

validate_record_timestamps comprueba que created_at y updated_at
estén informados y que updated_at sea mayor o igual que created_at.

Se comprobaron fechas iguales, actualización posterior,
actualización anterior y fechas nulas.
Las cinco entidades de Bronze superaron este control.

Esta validación no comprueba todavía fechas entre entidades,
order_date ni el corte temporal de la carga inicial.

## Existencia de líneas por pedido

validate_order_completeness identifica pedidos sin líneas
mediante LEFT ANTI JOIN.

Se comprobaron pedidos con una o varias líneas, pedidos sin líneas
y un conjunto de líneas vacío.
La carga inicial de Bronze contiene cero pedidos sin líneas.

Este control comprueba existencia de líneas.
Su validez se evalúa mediante los controles de claves,
referencias y valores comerciales.

## Capacidad de almacenamiento de textos

La consulta del origen confirmó Modern_Spanish_CI_AS en las columnas
de texto y la página de códigos 1252 para varchar y char.

validate_text_storage comprueba presencia, representación y longitud
en bytes, sin modificar los valores:

- nvarchar: codificación UTF-16LE.
- varchar y char: codificación Windows-1252 estricta.

Las once columnas de texto de Bronze superaron el control.
Se probaron longitudes límite y excesivas, caracteres representables
e incompatibles, cadenas vacías y nulos.
También se verificó la ejecución de la UDF dentro de Spark.

Las cadenas vacías no se rechazan por esta regla.
Los dominios de estado y moneda se comprueban por separado.

Este control no reproduce las comparaciones de la intercalación
ni verifica la unicidad de las claves alternativas.

## Claves alternativas

validate_alternate_keys comprueba category_name, sku y email.

La política spark_lower_rtrim utiliza lower y rtrim únicamente
para construir la clave de comparación.
Conserva los textos originales y distingue los acentos.

Se comprobaron claves diferentes, diferencias de mayúsculas,
espacios finales, acentos, espacios iniciales y claves nulas.

Las tres claves de Bronze superaron el control:
cero nulos y cero grupos duplicados bajo esta política.

Esta comparación no reproduce toda la intercalación
Modern_Spanish_CI_AS de SQL Server.
No sustituye las restricciones UNIQUE del origen.

## Período de la carga inicial

validate_initial_period recibe límites con zona horaria y comprueba:

- created_at y updated_at anteriores al corte exclusivo.
- order_date dentro del período comercial: inicio inclusivo
  y corte exclusivo.

No exige que las fechas técnicas sean posteriores al inicio comercial.

Se probaron el inicio exacto, el instante anterior al corte,
el corte exacto, pedidos anteriores al período y fechas nulas.
Las cinco entidades de Bronze superaron el control usando
los límites de data/initial/manifest.json.

La correspondencia con el corte del manifiesto de extracción
se comprobará al integrar la carga.

## Creación de líneas respecto al pedido

validate_item_creation_dates exige que created_at de cada línea
sea mayor o igual que created_at de su pedido.

Se probaron fechas iguales, posteriores, anteriores, pedido ausente
y fechas nulas en ambos lados.
Bronze superó el control sin líneas incompatibles.

La clave primaria de pedidos debe validarse antes del JOIN
para evitar multiplicación de filas.

Una referencia ausente puede incumplir también el control de claves
foráneas. Los conteos por regla pueden solaparse.
