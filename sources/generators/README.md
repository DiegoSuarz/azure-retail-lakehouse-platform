# Generación de datos iniciales

## Ejecución

Desde la raíz del repositorio, con el entorno virtual activo:

    python sources/generators/generate_initial_data.py

Requiere Python 3.12 y utiliza únicamente la biblioteca estándar.

## Parámetros

- --seed: semilla aleatoria; valor predeterminado 42.
- --output-dir: carpeta de salida; valor predeterminado data/initial.

El generador rechaza una carpeta de salida que ya contiene archivos.

## Conjunto inicial

| Entidad | Filas con semilla 42 |
|---|---:|
| categories | 6 |
| products | 60 |
| customers | 500 |
| orders | 2000 |
| order_items | 5862 |

Los pedidos se distribuyen en:

- pending: 209.
- confirmed: 1578.
- cancelled: 213.

## Fechas e importes

- Inicio inclusivo de pedidos: 2026-01-01T00:00:00.000Z.
- Corte exclusivo: 2026-10-01T00:00:00.000Z.
- Clientes y catálogo creados el 1 de diciembre de 2025 en UTC.
- Fechas representadas en UTC.
- Moneda PEN.
- Importes calculados mediante Decimal.
- Descuento expresado como importe total de línea.
- Datos y marcas sintéticos; correos bajo example.com.

Los precios de catálogo se copian como precios de venta en esta
generación inicial. Los cambios posteriores se modelarán por separado.

## Archivos

Se generan cinco CSV y manifest.json.

El manifiesto contiene parámetros, conteos, hashes SHA-256 y totales
para reconciliar los archivos y la posterior carga en SQL Server.

Los archivos generados permanecen excluidos de Git.

## Validación

    python tests/generators/validate_initial_data.py

El validador comprueba hashes, conteos, claves, relaciones,
fechas, reglas comerciales y concordancia con el manifiesto.

La comparación de dos generaciones con semilla 42 confirmó
igualdad byte por byte de los seis archivos en Python 3.12.3.

## Controles verificados con semilla 42

- Importe bruto de todos los pedidos: PEN 21645086.45.
- Descuento de todos los pedidos: PEN 1667089.99.
- Importe neto de todos los pedidos: PEN 19977996.46.
- Importe neto de pedidos confirmados: PEN 15781257.30.
- Unidades de pedidos confirmados: 11682.

## Estado

Generación y validación local completadas.
La carga en SQL Server todavía está pendiente.
