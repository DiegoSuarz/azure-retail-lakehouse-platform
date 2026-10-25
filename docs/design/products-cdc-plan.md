# CDC real de productos — M8

## Objetivo

Capturar cambios reales de TechRetail_OLTP.dbo.products mediante
CDC nativo de SQL Server y aplicarlos a una tabla Delta.

El alcance inicial comprende una tabla y ejecución manual por lotes.

## Flujo

1. Habilitar CDC en la base y en dbo.products.
2. Establecer una base de comparación antes de generar cambios.
3. Ejecutar cambios controlados en SQL Server.
4. Extraer los eventos capturados dentro de un intervalo de LSN.
5. Conservar el lote antes de avanzar la posición de extracción.
6. Aplicar los eventos a una copia Delta local.
7. Verificar resultados y reprocesamiento.
8. Ejecutar el flujo validado en Azure.

La posición de extracción y la posición de aplicación se controlarán
por separado. Extraer un lote no significa haberlo aplicado a Silver.

## Alcance

- Tabla: dbo.products.
- Clave: product_id, estable durante las pruebas.
- Operaciones: inserción, actualización y eliminación.
- Captura: CDC nativo de SQL Server.
- Desarrollo y pruebas: Python, PySpark y Delta locales.
- Destino final: Silver en ADLS Gen2 mediante Databricks.
- Sin automatización continua en esta primera implementación.

Los contratos sintéticos existentes se conservan como trabajo previo.
Sus event_id y event_sequence no se asumirán como metadatos del CDC real.
El orden de procesamiento utilizará los metadatos nativos de CDC.

## Datos de prueba

Se comprobará que las claves y los SKU elegidos estén disponibles.
Los productos nuevos utilizarán una categoría existente.

Se prepararán casos separados para observar:

- Un producto insertado que permanezca en el destino.
- Una actualización de precio que permanezca en el destino.
- Una eliminación de un producto de prueba sin referencias de ventas.

No se eliminarán productos existentes referenciados por order_items.
Las pruebas respetarán los campos obligatorios, precios positivos,
unicidad de SKU y orden de fechas.

## Continuidad y recuperación

El límite inicial de captura se establecerá antes de los cambios de prueba.
Se comprobará que la base de partida corresponda al estado esperado.

Cada extracción tendrá límites de LSN identificables.
La posición de extracción solo avanzará después de conservar el lote.
La posición de aplicación solo avanzará después de verificar el resultado.

Los lotes se aplicarán en orden.
No se avanzará la posición de aplicación si falla un lote.
Si el intervalo requerido dejó de estar disponible por retención,
se detendrá el proceso para revisar la recuperación.

## Criterios de aceptación

- SQL Server captura las tres operaciones.
- Los archivos conservan claves, valores y metadatos de orden.
- Delta refleja los cambios esperados.
- Cambiar list_price no modifica precios históricos de order_items.
- Repetir el último lote no altera valores ni duplica registros.
- Un lote anterior no puede sobrescribir un estado posterior.
- Un fallo no hace avanzar indebidamente las posiciones de control.

## Estado

Diseño inicial definido.
Captura real de inserciones, actualización y eliminación verificada.
Extracción por LSN, continuidad y aplicación local a Delta verificadas.
Reprocesamiento, recuperación y ejecución en Azure pendientes.
Databricks permanece detenido durante la preparación local.

## Habilitación verificada — M8.1

El 23 de octubre de 2026 se habilitó CDC en TechRetail_OLTP
y exclusivamente en dbo.products.

Configuración:

- SQL Server Enterprise Developer, versión 17.0.1145.4.
- SQL Server Agent en ejecución, con inicio manual.
- Instancia de captura: dbo_products.
- Nueve columnas comerciales capturadas.
- Rol de acceso: cdc_products_reader.
- supports_net_changes = 0.
- Captura continua, con pollinginterval = 5 segundos.
- Retención de limpieza: 4320 minutos, equivalentes a tres días.

Los trabajos de captura y limpieza se crearon e iniciaron correctamente.
sys.dm_cdc_errors no devolvió errores.
La tabla conservó sus 60 productos.

La habilitación está verificada; la captura funcional de inserciones,
actualizaciones y eliminaciones se comprobará en M8.2.

## Captura y extracción verificadas — M8.2 y M8.3

Se conservó una base inicial de 60 productos con el LSN:
0x00000033000016f80003.

La prueba generó cuatro eventos reales:

| Operación CDC | Producto | Precio |
|---|---:|---:|
| Inserción, código 2 | 61 | 2500.00 |
| Inserción, código 2 | 62 | 3000.00 |
| Actualización, código 4 | 61 | 2600.00 |
| Eliminación, código 1 | 62 | 3000.00 |

El origen terminó con 61 productos.
Los cambios de prueba se limitaron a los productos 61 y 62.

extract_products_cdc.py consulta los cambios mediante las funciones CDC,
conservando las nueve columnas comerciales y los metadatos de orden.

El primer lote guardó cuatro eventos hasta el LSN:
0x0000003300004cb80003.

El checkpoint de extracción se actualiza después de guardar el lote.
Una segunda ejecución guardó cero eventos y conservó el mismo LSN.
Se verificó que el primer lote permaneciera disponible.

Archivos locales, excluidos de Git:

- data/validation/cdc_products/baseline.json
- data/validation/cdc_products/batch_001.json
- data/validation/cdc_products/batch_002.json
- data/validation/cdc_products/extraction_checkpoint.json

La ejecución es manual y secuencial, sin extractores simultáneos.
La recuperación ante fallos todavía debe probarse.
Los eventos aún no se han aplicado a Delta.

## Aplicación local verificada — M8.4

products_cdc_transform.py implementa:

- Conversión de registros JSON al esquema comercial de productos.
- Creación y comparación de la tabla Delta inicial.
- Aplicación del último evento por producto mediante MERGE.

Se creó una tabla local con los 60 productos de baseline.json.
Se aplicó batch_001.json, con cuatro eventos sobre dos claves.

Resultados comprobados:

- 61 productos en el estado final.
- Producto 61 presente, con precio 2600.00.
- Producto 62 ausente.
- Los 60 productos originales conservaron todos sus valores.
- El estado final completo coincidió con el resultado esperado.

La tabla de prueba se conserva en:
data/validation/cdc_products/silver/products/

La selección del último evento representa el estado vigente;
los cuatro eventos originales permanecen en el archivo de extracción.

No se actualizó todavía un checkpoint de aplicación.
La protección frente a lotes antiguos y las pruebas de recuperación
corresponden a M8.5. La ejecución en Azure permanece pendiente.
