# Modelo de datos de origen

## Objetivo

Definir el modelo OLTP de TechRetail_OLTP y las claves compartidas
por la carga inicial, los archivos incrementales y los eventos JSON.

Los datos representarán una tienda ficticia de artículos tecnológicos
en Perú. Todos los clientes y las operaciones serán sintéticos.

## Convenciones

- Tablas y columnas en inglés, con snake_case.
- Tablas del negocio en el esquema dbo.
- Identificadores enteros positivos y estables.
- Importes expresados en PEN mediante decimal(18,2).
- Fechas técnicas en UTC mediante datetime2(3).
- Fechas de negocio para reportes interpretadas en America/Lima.
- created_at representa la creación del registro.
- updated_at representa su última modificación.
- Las claves del origen son distintas de las claves surrogate
  que se crearán posteriormente en el modelo dimensional.

Los identificadores se asignarán explícitamente durante la generación
de datos para reproducirlos y reutilizarlos en CSV y JSON.

## Entidades y grano

| Tabla | Grano | Clave primaria |
|---|---|---|
| categories | Una categoría | category_id |
| products | Un producto | product_id |
| customers | Un cliente | customer_id |
| orders | Un pedido | order_id |
| order_items | Una línea dentro de un pedido | order_id, line_number |

## categories

| Columna | Tipo previsto | Nulo | Descripción |
|---|---|---|---|
| category_id | int | No | Identificador de categoría |
| category_name | nvarchar(100) | No | Nombre único de categoría |
| created_at | datetime2(3) | No | Fecha de creación en UTC |
| updated_at | datetime2(3) | No | Fecha de modificación en UTC |

## products

| Columna | Tipo previsto | Nulo | Descripción |
|---|---|---|---|
| product_id | int | No | Identificador de producto |
| category_id | int | No | Categoría del producto |
| sku | varchar(40) | No | Código comercial único |
| product_name | nvarchar(200) | No | Nombre del producto |
| brand | nvarchar(100) | No | Marca |
| list_price | decimal(18,2) | No | Precio vigente del catálogo en PEN |
| is_active | bit | No | Disponibilidad en el catálogo |
| created_at | datetime2(3) | No | Fecha de creación en UTC |
| updated_at | datetime2(3) | No | Fecha de modificación en UTC |

Cambiar list_price no modificará el precio de ventas anteriores.
Los productos retirados se marcarán como inactivos y conservarán su clave.

## customers

| Columna | Tipo previsto | Nulo | Descripción |
|---|---|---|---|
| customer_id | int | No | Identificador de cliente |
| first_name | nvarchar(100) | No | Nombre sintético |
| last_name | nvarchar(100) | No | Apellido sintético |
| email | varchar(254) | No | Correo sintético único |
| city | nvarchar(100) | No | Ciudad |
| region | nvarchar(100) | No | Departamento o región |
| is_active | bit | No | Estado del cliente |
| created_at | datetime2(3) | No | Fecha de creación en UTC |
| updated_at | datetime2(3) | No | Fecha de modificación en UTC |

Los correos utilizarán el dominio example.com.
No se incorporarán DNI, teléfonos ni información personal real.

## orders

| Columna | Tipo previsto | Nulo | Descripción |
|---|---|---|---|
| order_id | int | No | Identificador de pedido |
| customer_id | int | No | Cliente que realiza el pedido |
| order_date | datetime2(3) | No | Fecha del pedido en UTC |
| status | varchar(20) | No | Estado del pedido |
| currency_code | char(3) | No | Moneda comercial: PEN |
| created_at | datetime2(3) | No | Fecha de creación en UTC |
| updated_at | datetime2(3) | No | Fecha de modificación en UTC |

Estados iniciales:

- pending: pedido registrado, pendiente de confirmación.
- confirmed: pedido confirmado e incluido en los indicadores de ventas.
- cancelled: pedido cancelado y excluido de esos indicadores.

Transiciones permitidas:

- pending a confirmed.
- pending a cancelled.
- confirmed a cancelled.

cancelled será un estado terminal en el alcance inicial.
Una cancelación posterior requerirá actualizar los resultados analíticos.

## order_items

| Columna | Tipo previsto | Nulo | Descripción |
|---|---|---|---|
| order_id | int | No | Pedido al que pertenece la línea |
| line_number | int | No | Número de línea dentro del pedido |
| product_id | int | No | Producto vendido |
| quantity | int | No | Unidades de la línea |
| unit_price | decimal(18,2) | No | Precio unitario de la venta en PEN |
| discount_amount | decimal(18,2) | No | Descuento total de la línea en PEN |
| created_at | datetime2(3) | No | Fecha de creación en UTC |
| updated_at | datetime2(3) | No | Fecha de modificación en UTC |

El mismo producto podrá aparecer en distintas líneas de un pedido.
La identidad de la línea será order_id más line_number.

unit_price conservará el precio acordado al registrar la venta.
discount_amount será un importe total de línea, no un porcentaje
ni un descuento unitario.

Medidas derivadas:

- Importe bruto de línea: quantity * unit_price.
- Importe neto de línea: quantity * unit_price - discount_amount.

No se almacenarán totales redundantes en orders.
Los totales del pedido se obtendrán a partir de sus líneas.

En el alcance inicial no se modelarán envío ni impuestos
como componentes separados.

## Relaciones

- products.category_id referencia categories.category_id.
- orders.customer_id referencia customers.customer_id.
- order_items.order_id referencia orders.order_id.
- order_items.product_id referencia products.product_id.

No se aplicarán eliminaciones físicas en cascada.
La desactivación de clientes y productos preservará las referencias
de los pedidos históricos.

## Reglas de integridad

- Identificadores y line_number mayores que cero.
- quantity mayor que cero.
- list_price y unit_price mayores que cero.
- discount_amount entre cero y el importe bruto de la línea.
- currency_code igual a PEN.
- status limitado a pending, confirmed y cancelled.
- updated_at mayor o igual que created_at.
- Unicidad de category_name, sku y email.
- Todas las claves foráneas deben encontrar su registro padre.
- Cada pedido publicado para análisis debe tener al menos una línea.

Las restricciones locales de columna y las relaciones se implementarán
en SQL Server. Las reglas que abarcan varios registros, como la existencia
de líneas por pedido, también se comprobarán mediante validaciones.

Las transiciones de estado y la coherencia temporal entre entidades
se validarán al generar y aplicar cambios.

## Preparación para incrementales

Los CSV de nuevos pedidos y líneas conservarán las claves y tipos
definidos en este modelo.

Los eventos JSON de cambios incluirán event_id, entity,
operation, event_time y las claves del registro afectado.

event_time determinará el momento del cambio en el origen.
Las fechas de ingesta se registrarán por separado en el Lakehouse.

Los contratos detallados definirán el orden de aplicación,
los empates temporales y la deduplicación.

## Preparación para SCD

Se evaluará conservar historial de atributos como:

- Ciudad y región del cliente.
- Categoría, nombre, marca y precio de catálogo del producto.

La selección definitiva entre SCD tipo 1 y tipo 2 se documentará
antes de implementar las dimensiones.

El precio de catálogo y el precio unitario de una venta tendrán
significados distintos y se conservarán por separado.

## Estado

Modelo propuesto en M2.1.
Las tablas y las restricciones todavía no están implementadas.
