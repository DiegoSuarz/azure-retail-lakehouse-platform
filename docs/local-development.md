# Entorno de desarrollo local

## Entorno verificado

- Sistema: Ubuntu en WSL.
- Python: 3.12.3.
- Git: 2.43.0.
- Entorno virtual: .venv.

## Crear el entorno

Desde la raíz del repositorio:

```bash
python3 -m venv .venv
```

Este paso se realiza una sola vez por copia local del proyecto.

## Activar el entorno

```bash
source .venv/bin/activate
```

Se debe activar en cada nueva sesión de terminal que requiera Python.

## Verificar el intérprete

```bash
python --version
python -m pip --version
```

Las rutas del intérprete y de pip deben pertenecer a .venv.

## Dependencias

Todavía no se han incorporado dependencias del proyecto.

Se registrarán conforme se implementen los componentes.
Las instalaciones se realizarán mediante python -m pip
dentro del entorno virtual.

## VS Code

Abrir el proyecto desde WSL:

```bash
code .
```

Seleccionar el intérprete .venv/bin/python mediante
Python: Select Interpreter.

## Desactivar el entorno

```bash
deactivate
```

## Alcance

Este entorno se utilizará para generación de datos sintéticos,
consumo local de API y pruebas.

Databricks tendrá su propio entorno de ejecución.
La compatibilidad de PySpark y Delta se verificará al preparar
las transformaciones.

La carpeta .venv está excluida de Git y debe recrearse
en cada equipo.
