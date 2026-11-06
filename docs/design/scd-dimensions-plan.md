# Plan de dimensiones con SCD

## Objetivo y alcance

Incorporar SCD tipo 1 y tipo 2 en dim_product y dim_customer,
preservando las claves existentes de M9 y las relaciones con fact_sales.

Las reglas siguientes constituyen el diseño inicial del proyecto.
No implican que los datos disponibles permitan reconstruir historia anterior.

dim_date, dim_order_status, ref_exchange_rates y
product_catalog_mapping quedan fuera del procesamiento SCD de M10.
La relación del catálogo complementario con las versiones de producto
deberá revisarse al definir las claves y consultas de consumo.

## Matriz de atributos

| Dimensión | Atributo | Tratamiento | Regla |
|---|---|---|---|
| dim_product | product_id | Clave de negocio | Estable entre versiones |
| dim_product | sku | Estable | Un cambio se bloquea para revisión explícita |
| dim_product | product_name | Tipo 1 | Corrección descriptiva |
| dim_product | brand | Tipo 1 | Corrección descriptiva dentro de este alcance |
| dim_product | category_id, category_name | Tipo 2 | Conservar cambios de clasificación |
| dim_product | list_price | Tipo 2 | Conservar cambios del precio de catálogo |
| dim_product | is_active | Tipo 2 | Conservar bajas lógicas y reactivaciones |
| dim_customer | customer_id | Clave de negocio | Estable entre versiones |
| dim_customer | first_name, last_name | Tipo 1 | Corrección de nombres |
| dim_customer | city, region | Tipo 2 | Conservar cambios de ubicación |
| dim_customer | is_active | Tipo 2 | Conservar bajas lógicas y reactivaciones |

Una corrección real y un cambio de negocio no siempre pueden
distinguirse automáticamente. La matriz establece cómo se interpretarán
los cambios recibidos dentro del alcance de este proyecto.

Los pares categoría y ubicación se validan conjuntamente para evitar
combinaciones inconsistentes. Un cambio válido en cualquiera de sus
atributos puede generar una nueva versión.

## Reglas de aplicación

- Entidad nueva: crear su primera versión con una nueva clave dimensional.
- Registro sin cambios: no actualizar la fila ni crear una versión.
- Solo cambios tipo 1: corregir todas las versiones de la entidad,
  sin modificar sus claves ni períodos de vigencia.
- Cambios tipo 2: cerrar la versión actual y crear una nueva
  con una nueva clave dimensional.
- Cambios simultáneos tipo 1 y tipo 2: corregir los atributos tipo 1
  en las versiones existentes y crear una nueva versión por los tipo 2.
- Varios atributos tipo 2 modificados en el mismo cambio efectivo:
  producir una sola nueva versión.
- Baja lógica explícita: registrar is_active = false mediante tipo 2.
- Reactivación explícita: registrar is_active = true mediante tipo 2.
- Ausencia en una entrada: no interpretarla automáticamente como baja.
- Baja física: no eliminar versiones referenciadas por ventas;
  su tratamiento queda pendiente de contrato explícito.
- Cambio de SKU: bloquear para revisión, sin aplicación automática.

El alcance de tipo 1 sobre todas las versiones es una decisión deliberada:
esos atributos no conservan historial. Las consultas históricas mostrarán
su valor corregido.

## Claves y medidas que deben preservarse

product_id y customer_id identifican entidades de negocio.
product_key y customer_key identifican filas o versiones dimensionales.

Las claves existentes de M9 se conservan.
No se permite reconstruir toda la numeración al incorporar cambios.
Una versión nueva requiere una clave nueva, única y estable.

list_price representa el precio de catálogo del producto.
unit_price_pen representa el precio aplicado a la línea de venta.
Un cambio de catálogo no modifica precios ni importes de hechos existentes.

is_active representa el estado comercial de la entidad.
is_current representará la versión dimensional actual.
Una entidad inactiva puede tener una versión actual.

## Escenarios de aceptación

| Escenario | Resultado esperado |
|---|---|
| Cliente nuevo | Primera versión con nueva customer_key |
| Corrección de apellido | Mismas claves y vigencias, apellido corregido en todas las versiones |
| Cambio de ciudad o región | Versión anterior conservada y nueva customer_key |
| Producto cambia de categoría | Nueva product_key y clasificación anterior conservada |
| Producto cambia de precio de catálogo | Nueva versión; importes de ventas existentes intactos |
| Cambio de nombre y precio del producto | Corrección tipo 1 y una nueva versión por el precio |
| Baja lógica | Nueva versión inactiva sin borrar el historial |
| Reactivación | Nueva versión activa sin borrar el historial |
| Registro idéntico | Ninguna nueva versión ni actualización |
| Entidad ausente del lote | Ninguna baja inferida |
| SKU diferente para el mismo producto | Cambio bloqueado para revisión |

## Organización del flujo simplificado

- scd_transform.py reúne reglas, detección y preparación de cambios.
- scd_storage.py lee versiones Delta y aplica el resultado mediante MERGE.
- run_scd_local.py coordinará la ejecución; implementación pendiente.

La inicialización y la resolución de claves de ventas permanecen
en sus módulos específicos.

El flujo utiliza un único escritor por dimensión.
No incluye huellas de lotes, registro de estados ni recuperación automática.
La igualdad con el estado actual evita escrituras innecesarias.
Los fallos y las entradas antiguas requieren revisión manual.

## Pendientes

- Integrar el ejecutor y verificar la operación con lotes consecutivos.
- Completar los controles del historial en la ejecución integrada.
- Precisar el consumo del catálogo complementario con versiones de producto.
- Ejecutar y verificar el flujo en Azure.
- Consolidar las evidencias y el cierre de M10.

## Estado

Inicialización local y funciones de transformación y ventas verificadas.
Almacenamiento Delta probado con datos sintéticos en rutas temporales.
Las tablas Gold aceptadas de M9 permanecen sin modificaciones.
