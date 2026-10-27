# Modelo estrella de ventas — M9

## Objetivo

Construir un modelo dimensional en Gold a partir de Silver,
con medidas reconciliadas y preparado para consumo analítico.

El desarrollo y las pruebas comenzarán localmente.
Databricks permanecerá detenido durante la preparación.

## Preguntas de negocio

- ¿Cuál es el importe de ventas confirmadas por día y mes?
- ¿Qué productos, categorías y marcas concentran las ventas?
- ¿Cuántas unidades se venden por producto?
- ¿Cómo se distribuyen las ventas por ciudad y región del cliente?
- ¿Qué descuentos se conceden?
- ¿Cuál es el ticket promedio de los pedidos confirmados?
- ¿Cómo se distribuyen los pedidos entre sus estados?
- ¿Cuál es el equivalente analítico en USD de las ventas en PEN,
  cuando existe una tasa aplicable?
- ¿Qué atributos presentan los productos locales y externos
  vinculados mediante el mapeo educativo?

## Fuentes

Entradas principales de Silver:

- categories
- products
- customers
- orders
- order_items

La dimensión de productos podrá incluir el producto 61 incorporado
por CDC en M8 aunque no tenga líneas de venta.

Fuentes complementarias de Silver:

- exchange_rates: tasas de BCRPData.
- dummyjson_products: catálogo externo.
- product_external_mapping: asociaciones educativas versionadas.

BCRPData permitirá calcular equivalentes analíticos en USD.
DummyJSON y el mapeo permitirán explorar atributos de ambos catálogos.
Las reglas de uso se definen en las secciones siguientes.

## Tablas propuestas

| Tabla | Grano |
|---|---|
| fact_sales | Una línea de pedido |
| dim_product | Un producto en la carga inicial dimensional |
| dim_customer | Un cliente en la carga inicial dimensional |
| dim_date | Un día del calendario |
| dim_order_status | Un estado de pedido |

La categoría se incorporará como atributo de dim_product.

Las claves surrogate, los atributos y las relaciones se definirán
en M9.1. El historial SCD se implementará en M10.

## Reglas de negocio

- La identidad de la línea es order_id más line_number.
- fact_sales conservará líneas de todos los estados admitidos.
- Los indicadores de ventas incluirán únicamente confirmed.
- pending y cancelled podrán analizarse por separado.
- order_date representa UTC.
- La fecha de negocio se obtendrá convirtiendo a America/Lima.
- Los importes se expresarán en PEN.
- El precio de venta procederá de order_items.unit_price.
- El precio vigente del catálogo no recalculará ventas anteriores.
- El descuento es el importe total de línea.
- Importe bruto = quantity * unit_price.
- Importe neto = importe bruto - discount_amount.
- El ticket promedio requiere contar pedidos distintos;
  no se calculará como promedio del importe de las líneas.

Las dimensiones iniciales describirán los atributos disponibles
en Silver al construir Gold. No se afirmará que esos atributos
representan todas sus versiones históricas.

## Conversión analítica con BCRPData

Se conservarán los importes originales en PEN.
Los equivalentes en USD serán valores adicionales.

La tasa expresa PEN por USD:
importe_usd = importe_pen / rate_pen_per_usd.

Antes de implementar la conversión se definirán:

- La serie y su significado económico.
- La fecha de referencia, basada en la fecha de negocio en Lima.
- La política para fines de semana y observaciones no disponibles.
- El límite de antigüedad permitido si se utiliza una tasa anterior.
- La precisión y el redondeo de los importes convertidos.

Se conservarán la fecha de la tasa efectivamente utilizada,
su valor y un indicador de disponibilidad de conversión.

Si no existe una tasa aplicable, el importe USD quedará nulo.
No se sustituirá una tasa faltante por cero ni por uno.
Las ventas sin conversión permanecerán en el modelo.

La conversión no representa ingresos originalmente cobrados en USD.
Los totales USD deberán mostrar la cobertura de conversión.

## Exploración del catálogo externo

Se construirá un dataset complementario con productos locales,
productos DummyJSON y sus asociaciones educativas.

La granularidad y el tipo de unión se definirán en M9.1.
Las uniones no deberán multiplicar las líneas de fact_sales.

Se conservarán los identificadores de ambas fuentes,
mapping_type y mapping_note.

El precio local de catálogo se identificará como PEN.
El precio externo conservará su moneda nula cuando no esté declarada.

No se supondrá equivalencia comercial entre los productos asociados.
No se asumirá USD como moneda de DummyJSON.
No se calcularán diferencias monetarias ni porcentajes de precios
entre ambos catálogos mientras falten moneda y equivalencia verificadas.

## Criterios de aceptación

- Una fila de hechos por línea de pedido, sin duplicados.
- Todas las claves dimensionales resueltas según la política definida.
- Las uniones no multiplican ni pierden líneas.
- Cantidades e importes reconciliados con Silver.
- Ventas confirmadas reconciliadas con el mismo filtro de estado.
- Fecha de negocio comprobada, incluyendo cruces de día entre UTC y Lima.
- Tipos decimales y valores conservados tras escribir y leer Delta.
- Consultas de ejemplo verificadas sobre el modelo final.
- La conversión monetaria no cambia el número de líneas de hechos.
- Tasas aplicadas trazables y ausencia de tasas futuras respecto
  a la fecha de negocio.
- Cobertura y faltantes de conversión identificados.
- Dataset externo sin asociaciones duplicadas para su grano.
- Moneda externa y carácter educativo del mapeo preservados.

## Alcance

Carga inicial dimensional y ejecución manual.
Incluye el modelo estrella de ventas, conversión analítica
con BCRPData y un dataset complementario del catálogo DummyJSON.
Publicación Parquet, Synapse y Power BI corresponden a módulos posteriores.
No se implementará historial SCD ni actualización incremental de Gold en M9.

## Estado

M9.0: alcance inicial documentado.
Diseño detallado e implementación pendientes.

## Diseño dimensional — M9.1

### dim_product

Grano inicial: un producto de Silver.
Clave surrogate: product_key, bigint.
Clave del origen: product_id, int.

Atributos:

- sku
- product_name
- brand
- category_id
- category_name
- list_price, decimal(18,2), precio vigente en PEN
- is_active

Se incluirán todos los productos válidos, aunque no tengan ventas.
La categoría se incorpora mediante una relación muchos a uno.
La dimensión inicial describe el estado disponible en Silver,
sin reconstruir versiones históricas anteriores.

### dim_customer

Grano inicial: un cliente de Silver.
Clave surrogate: customer_key, bigint.
Clave del origen: customer_id, int.

Atributos:

- first_name
- last_name
- city
- region
- is_active

El correo no se publicará en Gold porque no es necesario
para las preguntas de negocio definidas.

### Asignación de claves de producto y cliente

Las claves surrogate serán independientes de las claves del origen.

En la primera carga se asignarán enteros consecutivos según
el identificador de origen, con orden determinista y sin duplicados.

La correspondencia entre clave surrogate y clave de origen
quedará persistida en las dimensiones Delta.
No se regenerarán claves sobre dimensiones existentes.

Las futuras cargas deberán reutilizar las claves asignadas
y reservar nuevas claves para registros o versiones nuevos.
La actualización y el historial corresponden a módulos posteriores.

No se utilizará monotonically_increasing_id para asignar estas claves.

### dim_date

Grano: un día calendario.
Clave: date_key, int, con formato YYYYMMDD.
Atributo único: full_date, date.

Atributos adicionales:

- year
- quarter
- month_number
- month_name
- day_of_month
- day_of_week, de lunes 1 a domingo 7
- day_name
- is_weekend

Los nombres de meses y días se definirán explícitamente en español.
El calendario cubrirá años completos que contengan las fechas
de negocio de los pedidos aceptados.

La fecha del pedido se obtendrá convirtiendo order_date
desde UTC a America/Lima antes de extraer el día.

### dim_order_status

Grano: un estado de pedido.
Clave: order_status_key, int.

Correspondencia fija:

| order_status_key | status | status_name | counts_as_sale |
|---|---|---|---|
| 1 | pending | Pendiente | false |
| 2 | confirmed | Confirmado | true |
| 3 | cancelled | Cancelado | false |

Los estados desconocidos impedirán aceptar la carga.

### fact_sales

Grano: una línea de pedido.
Clave de negocio única: order_id más line_number.

Referencias dimensionales:

- product_key
- customer_key
- date_key
- order_status_key

Identificadores conservados:

- order_id
- line_number

Campos comerciales:

- order_date_utc, timestamp
- currency_code, igual a PEN
- quantity, int
- unit_price_pen, decimal(18,2)
- gross_amount_pen
- discount_amount_pen
- net_amount_pen

Las precisiones de importes derivados se definirán en M9.2.

No se sumarán unit_price_pen ni claves como medidas.
Los pedidos se contarán mediante order_id distinto.
Las ventas se filtrarán por counts_as_sale = true.

Campos adicionales para conversión:

- exchange_rate_series_code
- exchange_rate_date
- rate_pen_per_usd, decimal(20,14)
- conversion_available, boolean
- gross_amount_usd
- discount_amount_usd
- net_amount_usd

La selección de tasa, precisión y redondeo se definirán en M9.2.
Cuando la conversión no esté disponible, sus importes serán nulos.
La incorporación de tasas conservará todas las líneas y su unicidad.

### Integridad dimensional

Las referencias obligatorias sin dimensión impedirán aceptar la carga.
M9 no sustituirá silenciosamente claves faltantes por valores ficticios.

Se comprobará la unicidad de las claves de origen y surrogate,
y la ausencia de referencias huérfanas.
Los productos o clientes inactivos no se eliminarán por ese motivo.

### ref_exchange_rates

Grano: una observación por series_code y observation_date.
Clave compuesta: series_code más observation_date.

Campos:

- series_code
- observation_date
- rate_pen_per_usd, decimal(20,14)
- available
- raw_value

Se conservarán las observaciones disponibles y no disponibles.
La tabla no inventará filas para días ausentes en la fuente.
La selección de una tasa para cada venta será una regla explícita
de transformación, no una modificación del dato original.

### product_catalog_mapping

Grano: una asociación educativa por source_system
y external_product_id.

Partirá del mapeo validado y utilizará uniones con referencias
obligatorias a productos locales y externos.
Las referencias faltantes impedirán aceptar el dataset.

Campos locales:

- product_key
- product_id
- local_sku
- local_product_name
- local_brand
- local_category_name
- local_list_price_pen

Campos externos:

- source_system
- external_product_id
- external_product_name
- external_category
- external_brand
- external_sku
- external_price
- external_currency_code
- external_rating
- external_stock

Campos del mapeo:

- mapping_type
- mapping_note

La versión actual contiene seis asociaciones educativas.
No se exigirá que todos los productos locales o externos estén asociados.
Las claves de ambos catálogos no se equipararán por igualdad numérica.

Este dataset permanecerá separado de fact_sales.
Los precios no se restarán ni dividirán entre fuentes.

### Procedencia y reproducibilidad

Las salidas incorporarán gold_processing_run_id y gold_processed_at.
La ejecución registrará las rutas y versiones Delta de las entradas,
para identificar el estado de Silver utilizado en la construcción.

Las tablas Gold se crearán sin sobrescribir destinos existentes.
La escritura entre tablas no constituye una transacción conjunta.
Una carga parcial no se declarará completada.
