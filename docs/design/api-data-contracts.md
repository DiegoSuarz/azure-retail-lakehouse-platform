# Contratos de API

## Objetivo

Definir la incorporación del catálogo complementario de DummyJSON
y del tipo de cambio de BCRPData.

Estas fuentes no sustituirán los datos comerciales de TechRetail_OLTP
ni generarán pedidos o cambios del CDC simulado.

## Convenciones comunes

- Versión del contrato interno: 1.
- Solicitudes HTTPS mediante GET.
- Formato de respuesta: JSON.
- Encabezado Accept: application/json.
- User-Agent: azure-retail-lakehouse-platform/1.0.
- Fechas técnicas de extracción en UTC.
- Conservación de las respuestas originales en Bronze.
- Validación y normalización posterior en Silver.

Cada respuesta tendrá metadatos de procedencia:

- ingestion_run_id.
- source_system.
- request_url.
- extracted_at.
- http_status.
- payload_sha256.

Las fechas de extracción no sustituirán las fechas de negocio
ni las fechas de observación publicadas por las fuentes.

## DummyJSON

### Función

Proporcionar un catálogo ficticio complementario para practicar
consumo de API, paginación, normalización y relaciones entre fuentes.

No será una fuente autoritativa de ventas, inventario o precios locales.

### Endpoints

Base:

    https://dummyjson.com

Descubrimiento de categorías:

    /products/category-list

Consulta por categoría:

    /products/category/{category}?limit=30&skip=0

Categorías verificadas desde el entorno local:

- laptops.
- smartphones.
- tablets.
- mobile-accessories.

Estas categorías externas no se equipararán automáticamente
con las categorías del OLTP.

### Paginación

Las respuestas de productos incluirán products, total, skip y limit.

Se consultarán páginas hasta completar el total informado,
avanzando según la cantidad de productos recibidos.

Se comprobarán identificadores duplicados, páginas vacías inesperadas
y cambios del total durante la extracción.

La paginación no garantiza una instantánea transaccional del catálogo.
Las inconsistencias impedirán considerar completa la extracción
y requerirán revisión o una nueva ejecución acotada.

No se fijarán conteos permanentes de productos en el contrato.

### Campos internos

| Campo de origen | Campo interno | Tratamiento |
|---|---|---|
| id | external_product_id | Entero positivo |
| title | external_product_name | Texto obligatorio |
| category | external_category | Categoría seleccionada |
| description | external_description | Texto opcional |
| brand | external_brand | Texto opcional |
| sku | external_sku | Texto opcional |
| price | external_price | Decimal, sin asumir moneda |
| rating | external_rating | Decimal entre 0 y 5 |
| stock | external_stock | Entero no negativo |
| thumbnail | thumbnail_url | Texto opcional |

La identidad será source_system más external_product_id,
con source_system igual a dummyjson.

Los campos opcionales ausentes se normalizarán como nulos.
Los errores en campos obligatorios se separarán para revisión.

Los importes se convertirán mediante Decimal, evitando conversiones
intermedias a float en el procesamiento local.

external_price no se utilizará para calcular ventas ni reemplazará
list_price o unit_price del negocio.

La respuesta verificada no incluye un código de moneda.
external_currency_code permanecerá nulo mientras no exista
una definición explícita y verificable de la fuente.

No se descargarán imágenes ni se normalizarán reseñas en esta versión.
Los campos adicionales permanecerán en la respuesta original.

### Mapeo con el catálogo local

El mapeo se mantendrá en un archivo versionado:

    sources/reference/product_external_mapping.csv

Columnas previstas:

    source_system,external_product_id,product_id,mapping_type,mapping_note

Reglas:

- source_system será dummyjson.
- Las claves externas y locales deberán existir.
- mapping_type será synthetic_demo en esta versión.
- mapping_note explicará la asociación educativa.
- Cada producto local tendrá como máximo una asociación con DummyJSON.
- Cada producto externo tendrá como máximo una asociación local.
- No se establecerán asociaciones únicamente por igualdad de IDs.
- No se exigirá cobertura de los 60 productos locales.
- Los productos sin asociación conservarán su validez.

Ambos catálogos son ficticios y se generaron de manera independiente.
El mapeo demostrará integración técnica, sin afirmar que los registros
representan el mismo artículo comercial.

Los atributos externos conservarán nombres separados.
No sobrescribirán nombres, marcas, categorías o precios locales.

El archivo se creará después de inspeccionar los productos tecnológicos
extraídos. No se asignarán identificadores externos por suposición.

### Actualización

Las primeras extracciones serán manuales y completas
para las categorías seleccionadas.

Se conservará cada respuesta recibida y se mantendrá una vista
del catálogo externo más reciente validado.

No se reconstruirá un historial anterior a las extracciones realizadas.

## BCRPData

### Función y serie

Incorporar una referencia histórica del tipo de cambio.

- source_system: bcrpdata.
- series_code: PD04638PD.
- Serie: TC Interbancario (S/ por US$) - Venta.
- Frecuencia: diaria.
- Unidad: PEN por USD.

Esta serie será una referencia analítica.
No representa necesariamente el tipo de cambio aplicado
a una transacción comercial.

### Endpoint

Base:

    https://estadisticas.bcrp.gob.pe/estadisticas/series/api

Patrón:

    /PD04638PD/json/{start_date}/{end_date}/esp

Las fechas de solicitud utilizarán YYYY-MM-DD.
Se validará que las observaciones recibidas pertenezcan
al intervalo solicitado.

La carga histórica inicial solicitará el período
desde 2026-01-01 hasta 2026-09-30.

Las consultas posteriores utilizarán intervalos explícitos.
Se podrán dividir por mes para acotar el volumen y los reprocesos.

### Estructura verificada

La respuesta incluye:

- config.series: metadatos de las series consultadas.
- periods: observaciones.
- periods[].name: fecha textual.
- periods[].values: valores alineados con las series.

Para la consulta de una sola serie, se exigirá una serie
en config.series y un valor por observación.

La respuesta no incluye el código de serie en cada observación.
series_code se obtendrá de la solicitud registrada.

### Normalización

| Campo interno | Tipo | Significado |
|---|---|---|
| series_code | Texto | PD04638PD |
| observation_date | Fecha | Fecha publicada por la fuente |
| rate_pen_per_usd | Decimal | Soles por dólar |
| source_system | Texto | bcrpdata |
| extracted_at | Fecha UTC | Momento de extracción |

La clave será series_code más observation_date.

Las fechas recibidas, como 01.Set.26, se convertirán mediante
un mapeo explícito de meses en español.

La interpretación del año deberá ser coherente con el intervalo
solicitado y no dependerá del locale del equipo.

Los valores llegan como cadenas y se procesarán con Decimal.
Se conservará la precisión recibida durante la normalización.

config.series[].dec no se utilizará para redondear automáticamente
las observaciones.

La precisión y escala de almacenamiento en Delta se definirán
y validarán antes de implementar Silver.

### Valores ausentes y revisiones

No se exigirá una observación para cada día calendario.

Las fechas sin cotización no se convertirán en tasas de cero.
Los valores vacíos o no numéricos se registrarán como no disponibles,
conservando el contenido original.

Las tasas numéricas válidas deberán ser mayores que cero.

Una repetición de la clave con el mismo valor será un reproceso.
Un valor revisado podrá actualizar la vista vigente, conservando
las respuestas previas y su procedencia.

Las consultas incrementales releerán inicialmente los últimos
siete días calendario para detectar revisiones recientes.

Esta ventana no garantiza detectar revisiones más antiguas.
Se permitirá consultar nuevamente un intervalo histórico explícito.

### Uso analítico

Los indicadores comerciales iniciales permanecerán en PEN.

Si se incorpora una conversión ilustrativa a USD:

    amount_usd = amount_pen / rate_pen_per_usd

La fecha comercial se obtendrá interpretando el instante del pedido
en America/Lima.

La regla para fechas sin cotización se definirá antes de publicar
métricas convertidas. No se aplicará relleno implícito.

## Errores y reintentos

- Tiempo de espera inicial: 30 segundos por solicitud.
- Máximo: tres intentos totales por solicitud.
- Reintentos con espera creciente para fallos transitorios.
- HTTP 429: respetar Retry-After cuando esté disponible.
- HTTP 5xx y errores temporales de red: reintentos acotados.
- HTTP 400, 401, 403 y 404: registrar y revisar, sin reintento automático.
- JSON inválido o estructura incompatible: separar para revisión.

Una ejecución incompleta no se marcará como extracción exitosa.

ADF coordinará posteriormente las extracciones.
Se evitará multiplicar intentos entre los reintentos del cliente
y los de la orquestación.

## Validaciones previstas

1. Estado HTTP y respuesta JSON válida.
2. Estructura y campos requeridos.
3. Tipos, claves y duplicados.
4. Categorías seleccionadas y paginación completa.
5. Integridad de referencias del mapeo.
6. Serie, fechas y tasas de cambio.
7. Conteos y hashes de respuestas conservadas.
8. Registro de errores y extracciones incompletas.

## Referencias

- https://dummyjson.com/docs/products
- https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/api
- https://estadisticas.bcrp.gob.pe/estadisticas/series/diarias/tipo-de-cambio-nominal

## Estado

Contrato definido en M2.5.

Se verificaron respuestas de productos, categorías y tipo de cambio
desde el entorno local.

La extracción persistente, el archivo de mapeo y las transformaciones
todavía no están implementados.
