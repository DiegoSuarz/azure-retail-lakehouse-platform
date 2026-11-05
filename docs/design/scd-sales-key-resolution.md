# Resolución de claves dimensionales para ventas con SCD

## Objetivo

Resolver product_key y customer_key para ventas nuevas utilizando
las versiones dimensionales correspondientes a order_date_utc.

Las vigencias representan estados observados según el contrato temporal.
No acreditan una historia efectiva de negocio anterior a la observación.

## Entradas

La resolución de ventas nuevas requiere:

- order_id y line_number como grano de la línea.
- product_id y customer_id como claves de negocio.
- order_date_utc como timestamp no nulo.
- Dimensiones SCD completas y previamente validadas.
- Referencias explícitas a las versiones Delta utilizadas.

Las claves de negocio se conservan durante la preparación de ventas,
antes de seleccionar las columnas definitivas de fact_sales.
La sesión Spark utiliza UTC.

## Coincidencia temporal

Para cada dimensión se exige igualdad de la clave de negocio y:

valid_from <= order_date_utc AND
(valid_to IS NULL OR order_date_utc < valid_to)

El inicio está incluido y el fin excluido.
Una venta exactamente en el límite entre versiones corresponde a la nueva.

No se filtra únicamente is_current: una venta tardía puede necesitar
una versión histórica cerrada.

is_active no determina la coincidencia temporal.
Su interpretación comercial se valida por separado.

## Ventas heredadas de M9

Las 5862 líneas de la carga aceptada conservan sus claves originales.
Su identificación depende de la base M9 aceptada, no solamente de su fecha.

La conservación comprueba que las claves sigan existiendo en las dimensiones.
No requiere que la fecha de la venta pertenezca a las vigencias iniciales SCD.

No se reasignan automáticamente sus claves al crear nuevas versiones.
Esta excepción no se extiende a ventas nuevas anteriores al historial.

## Ventas nuevas y tardías

Cada línea debe obtener exactamente una versión de producto
y exactamente una versión de cliente.

Una venta tardía utiliza las vigencias disponibles para su fecha.
La fecha de llegada o procesamiento no sustituye a order_date_utc.

Sin coincidencia, la línea bloquea el lote para revisión.
Esto incluye entidades desconocidas, fechas anteriores al inicio
del historial y posibles huecos entre versiones.

Varias coincidencias bloquean el lote por ambigüedad.
No se elige arbitrariamente la primera, la última ni la versión actual.

M10 no crea automáticamente versiones desconocidas ni retroactivas.

## Conservación de los hechos

La resolución conserva el grano, la cantidad de líneas y sus importes.
Añade las claves de producto y cliente a las ventas nuevas.

Las claves de fecha y estado mantienen su tratamiento existente.
Los importes PEN y USD no se recalculan por un cambio dimensional.

## Escenarios de aceptación

- Venta dentro de una versión abierta.
- Venta dentro de una versión cerrada.
- Venta exactamente en el inicio de una versión nueva.
- Venta anterior al historial disponible.
- Entidad sin referencia dimensional.
- Versiones solapadas que generan varias coincidencias.
- Conservación de claves de la base M9 aceptada.
- Conservación del grano y los importes de las ventas.

## Estado

Política definida.
Implementación y pruebas de resolución temporal pendientes.
