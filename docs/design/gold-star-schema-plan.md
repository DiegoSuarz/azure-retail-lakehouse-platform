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
