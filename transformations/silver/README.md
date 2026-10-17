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
