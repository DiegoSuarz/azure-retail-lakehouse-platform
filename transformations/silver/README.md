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
