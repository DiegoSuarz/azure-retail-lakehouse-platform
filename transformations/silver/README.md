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
