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
CDC todavía no habilitado.
Databricks permanece detenido durante la preparación local.
