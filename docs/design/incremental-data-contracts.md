# Contratos de datos incrementales

## Objetivo

Definir el intercambio de nuevos pedidos y cambios posteriores
al conjunto inicial de TechRetail_OLTP.

Estos contratos representan fuentes sintéticas para el Lakehouse.
No implican captura del log transaccional de SQL Server.

## Versión y corte

- Versión del contrato: 1.
- Corte exclusivo del conjunto inicial: 2026-10-01T00:00:00.000Z.
- Inicio inclusivo de incrementales: 2026-10-01T00:00:00.000Z.
- Moneda comercial: PEN.
- Fechas de eventos y registros: UTC, con milisegundos y sufijo Z.

El corte describe el conjunto sintético inicial. La extracción real
de SQL Server tendrá además controles para obtener una copia coherente.

## Organización de lotes

Cada lote tendrá una carpeta identificada por batch_id:

    data/incremental/<batch_id>/

Archivos admitidos:

- orders.csv y order_items.csv: nuevos pedidos y sus líneas.
- changes.jsonl: cambios de registros existentes.
- manifest.json: descripción y controles del lote.

Un lote puede contener solo CSV, solo eventos o ambos.
Si contiene orders.csv, debe contener también order_items.csv.

Los archivos de datos serán inmutables una vez publicado el manifiesto.
El manifiesto se publicará al final, cuando el lote esté completo.

batch_id identifica el lote, no sustituye las claves de los registros
ni event_id.

## Manifiesto

Campos obligatorios:

| Campo | Tipo | Significado |
|---|---|---|
| schema_version | Entero | Versión del contrato, inicialmente 1 |
| batch_id | Cadena | Identificador único del lote |
| created_at | Fecha UTC | Momento de publicación del lote |
| files | Objeto | Archivos presentes, conteos y hashes SHA-256 |

Cada entrada de files incluirá row_count y sha256.
row_count excluirá el encabezado CSV y contará eventos en JSONL.

No se procesará el lote si falta un archivo declarado, cambia un hash
o no coincide un conteo. No se publicarán pedidos de un lote incompleto.

Un batch_id repetido con el mismo contenido será un reproceso.
El mismo batch_id con contenido diferente será un conflicto.

## CSV de nuevos pedidos

Formato:

- Codificación UTF-8.
- Separador coma.
- Encabezado obligatorio y orden de columnas fijo.
- Comillas y escape conforme al módulo csv de Python.
- Importes decimales con punto y dos posiciones.
- Sin separadores de miles.
- Sin campos nulos en esta versión.

orders.csv conservará este encabezado:

    order_id,customer_id,order_date,status,currency_code,created_at,updated_at

order_items.csv conservará este encabezado:

    order_id,line_number,product_id,quantity,unit_price,discount_amount,created_at,updated_at

Las reglas de tipos y valores se definen en source-data-model.md.

## Identidad y consistencia de pedidos nuevos

- order_id debe identificar un pedido nuevo.
- La clave de línea será order_id más line_number.
- Las claves no podrán duplicarse dentro del lote.
- Todas las líneas deben pertenecer a pedidos incluidos en el lote.
- Cada pedido debe contener al menos una línea.
- Clientes y productos deben existir en el conjunto aceptado.
- currency_code debe ser PEN.
- created_at del pedido debe ser igual o posterior al corte.
- Las líneas no pueden crearse antes de su pedido.
- updated_at debe ser mayor o igual que created_at.
- Los importes deben cumplir las reglas del modelo de origen.

Los límites de una a cinco líneas y las cantidades usadas por el
generador inicial no son límites permanentes del contrato.

El precio unitario y el descuento de línea conservarán los valores
de la venta, independientemente del precio vigente del catálogo.

La repetición de una clave con idéntico contenido será un reproceso.
Una clave existente con contenido diferente no se sobrescribirá
mediante el contrato de nuevos pedidos: se registrará como conflicto.

## Eventos JSONL

changes.jsonl contendrá un objeto JSON por línea no vacía.
Cada objeto representará un cambio confirmado en el origen sintético.

Campos obligatorios:

| Campo | Tipo | Significado |
|---|---|---|
| schema_version | Entero | Versión del contrato |
| event_id | Cadena UUID | Identidad estable del evento |
| entity | Cadena | customers, products u orders |
| operation | Cadena | update en esta versión |
| event_time | Fecha UTC | Momento del cambio en el origen |
| event_sequence | Entero positivo | Secuencia por entidad y clave |
| business_key | Objeto | Clave del registro afectado |
| after | Objeto | Imagen completa posterior al cambio |

business_key contendrá:

- customer_id para customers.
- product_id para products.
- order_id para orders.

after incluirá todas las columnas de la entidad según el modelo
de origen, con su clave coincidente con business_key.

En JSON, los identificadores se representarán como enteros,
is_active como booleano y los importes como cadenas decimales
de dos posiciones para evitar ambigüedad de precisión.

created_at se conservará.
updated_at será igual a event_time.
event_time debe ser igual o posterior al corte y estrictamente
posterior a updated_at del registro inicial afectado.

No se admitirán insert ni delete en esta versión.
La desactivación de clientes y productos se expresará como update
de is_active.

## Atributos que pueden cambiar

customers:

- first_name, last_name, email, city, region e is_active.

products:

- category_id, product_name, brand, list_price e is_active.
- sku permanecerá estable en esta versión.

orders:

- status, respetando las transiciones permitidas.
- customer_id, order_date, currency_code y created_at permanecerán estables.

Las claves de negocio no cambiarán.
Las líneas de ventas existentes no se modificarán en esta versión.

## Orden de cambios

event_sequence será estrictamente creciente y consecutiva por
combinación de entity y business_key, comenzando en 1 tras el corte.

event_time será no decreciente en esa secuencia.
Si varios cambios comparten fecha, event_sequence resolverá su orden.

La hora de ingesta se registrará por separado y no determinará
el orden de negocio.

No se garantiza orden de llegada entre archivos o lotes.
Los eventos originales se conservarán en Bronze.

Un evento con una secuencia pendiente anterior no se aplicará
hasta resolver el hueco. Se registrará para seguimiento.

Si un cambio afecta un pedido nuevo del mismo lote, primero se
validarán e incorporarán el pedido y sus líneas.

## Deduplicación y conflictos

- event_id repetido con contenido equivalente: no aplicar nuevamente.
- event_id repetido con contenido diferente: conflicto.
- Misma entidad, clave y secuencia con eventos distintos: conflicto.
- Un evento atrasado no debe sobrescribir una versión posterior.
- Las comparaciones de contenido JSON ignorarán el orden de sus campos.

Los errores estructurales se separarán para revisión.
Las dependencias ausentes o huecos de secuencia podrán mantenerse
pendientes hasta resolver su causa.

No se descartarán eventos originales por llegar fuera de orden.

## Estados de pedido

Transiciones admitidas:

- pending a confirmed.
- pending a cancelled.
- confirmed a cancelled.

cancelled será terminal.
Un evento que viole la transición será rechazado para su aplicación.

Una cancelación posterior de un pedido confirmado deberá retirar
su contribución de las métricas de ventas confirmadas.

## Validaciones previstas

1. Integridad del manifiesto y de los archivos.
2. Columnas y campos obligatorios.
3. Tipos, formatos y versión del contrato.
4. Unicidad de claves y eventos.
5. Relaciones entre pedidos, líneas, clientes y productos.
6. Fechas, moneda, cantidades, precios y descuentos.
7. Coherencia de imágenes completas y atributos estables.
8. Secuencias, duplicados y conflictos.
9. Transiciones de estado.
10. Reconciliación de conteos e importes aceptados.

## Ejemplos de formato

Estos ejemplos ilustran la estructura del contrato.
No constituyen un lote listo para procesar: no incluyen manifiesto
y sus referencias deben validarse contra los datos aceptados.

### orders.csv

```csv
order_id,customer_id,order_date,status,currency_code,created_at,updated_at
2001,1,2026-10-01T10:00:00.000Z,pending,PEN,2026-10-01T10:00:00.000Z,2026-10-01T10:00:00.000Z
```

### order_items.csv

```csv
order_id,line_number,product_id,quantity,unit_price,discount_amount,created_at,updated_at
2001,1,1,2,2500.00,250.00,2026-10-01T10:00:00.000Z,2026-10-01T10:00:00.000Z
```

La línea representa dos unidades a PEN 2500.00 cada una.
El descuento total de línea es PEN 250.00 y el importe neto
es PEN 4750.00.

### changes.jsonl

El siguiente evento confirma el pedido del ejemplo anterior.
Debe escribirse como un único objeto en una sola línea:

```json
{"schema_version":1,"event_id":"e22c9af1-3fb2-4c1d-91d2-83ae490cd784","entity":"orders","operation":"update","event_time":"2026-10-01T11:00:00.000Z","event_sequence":1,"business_key":{"order_id":2001},"after":{"order_id":2001,"customer_id":1,"order_date":"2026-10-01T10:00:00.000Z","status":"confirmed","currency_code":"PEN","created_at":"2026-10-01T10:00:00.000Z","updated_at":"2026-10-01T11:00:00.000Z"}}
```

after contiene la imagen completa del pedido.
La clave coincide con business_key y updated_at coincide con event_time.

El pedido y su línea se incorporarán antes de aplicar este evento.
Reprocesar el mismo evento no debe duplicar su efecto.

## Estado

Contrato definido en M2.4.
La generación de lotes y su procesamiento todavía no están implementados.
Los escenarios de cambios y el corte se concretarán en M2.6.
