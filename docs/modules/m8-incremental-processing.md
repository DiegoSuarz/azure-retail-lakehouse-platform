# M8 — CDC real, incrementales e idempotencia

## Resultado

Se implementó y verificó un flujo manual de CDC real para
TechRetail_OLTP.dbo.products, desde SQL Server local hasta
la tabla Delta Silver registrada en Unity Catalog.

El alcance comprende una tabla y procesamiento secuencial por lotes.

## Flujo implementado

1. Habilitar CDC nativo en SQL Server para dbo.products.
2. Conservar una base de 60 productos y su límite inicial de LSN.
3. Generar inserciones, una actualización y una eliminación controladas.
4. Extraer los cambios y guardar los lotes antes de avanzar el checkpoint.
5. Aplicar los cambios a Delta mediante MERGE.
6. Verificar los datos antes de actualizar el control de aplicación.
7. Publicar las entradas en Bronze y ejecutar la aplicación en Databricks.

La posición de extracción y la posición de aplicación se mantienen
por separado.

## Servicios y herramientas

| Componente | Uso |
|---|---|
| SQL Server Developer | Origen y captura nativa de cambios |
| SQL Server Agent | Ejecutar los trabajos de captura y limpieza CDC |
| Python y pyodbc | Extraer productos, eventos y límites de LSN |
| PySpark y Delta Lake locales | Desarrollar y comprobar la aplicación |
| Azure CLI | Publicar archivos en Bronze y verificar su contenido |
| ADLS Gen2 | Conservar entradas, tabla Silver y control de aplicación |
| Azure Databricks | Ejecutar MERGE y validaciones en Azure |
| Unity Catalog | Consultar la tabla Silver por su nombre registrado |
| Access Connector | Autenticar el acceso de Databricks al almacenamiento |
| VNet, NAT Gateway e IP pública | Proporcionar conectividad al cómputo clásico |
| Git y GitHub | Versionar código, notebook y documentación |

## Prueba realizada

| Operación CDC | Producto | Precio |
|---|---:|---:|
| Inserción, código 2 | 61 | 2500.00 |
| Inserción, código 2 | 62 | 3000.00 |
| Actualización, código 4 | 61 | 2600.00 |
| Eliminación, código 1 | 62 | 3000.00 |

Los 60 productos originales permanecieron intactos.
El origen y el destino verificado terminaron con 61 productos.

En Azure se aplicó el último evento de cada producto.
El producto 62 no estaba en la base Silver, por lo que su eliminación
no requirió borrar una fila allí. Las tres operaciones reales
se comprobaron previamente en SQL Server.

## Resultados verificados

- Extracción de cuatro eventos y continuidad de un segundo lote vacío.
- Comparación de la base CDC con los 60 productos iniciales de Azure.
- Producto 61 presente a 2600.00 y producto 62 ausente.
- Estado comercial completo coincidente con el resultado esperado.
- Procedencia CDC conservada en el producto incorporado.
- Repetición exacta del último lote reconocida sin nuevas escrituras.
- Lotes anteriores diferentes y saltos de intervalo bloqueados localmente.
- Reintento local tras simular la falta de actualización del checkpoint.
- Consulta por Unity Catalog coincidente con el destino Delta.

La ejecución en Azure se verificó el 26 de octubre de 2026,
con Databricks Runtime 16.4 LTS y zona horaria UTC.

## Artefactos principales

- ingestion/sqlserver/capture_products_baseline.py
- ingestion/sqlserver/extract_products_cdc.py
- ingestion/sqlserver/publish_products_cdc.py
- transformations/silver/products_cdc_transform.py
- transformations/silver/run_products_cdc_local.py
- notebooks/silver/05_products_cdc_to_silver.ipynb

El diseño, los límites de LSN y los resultados detallados están en
[Plan de CDC de productos](../design/products-cdc-plan.md).

## Persistencia y control

Publicación de Bronze:
9625ead0-e913-5b83-873e-27b1ccda74de.

Tabla:
dbw_arlp_dev_diego01.silver_techretail.products.

Control Delta:
abfss://silver@starlpdevdiego01.dfs.core.windows.net/_control/products_cdc_application

Último LSN aplicado:
0x0000003300004cb80003.

La huella SHA-256 permite reconocer el último lote aplicado.
El control se actualiza después de verificar el resultado.

Después de procesar el segundo lote, no debe repetirse Run all:
el primer lote es anterior a la posición de aplicación conservada.

## Alcance y limitaciones

- Ejecución manual y secuencial, sin escritores simultáneos.
- Una tabla; no se extendió CDC al resto del modelo.
- Sin orquestación continua mediante ADF o Jobs.
- MERGE y control de aplicación son transacciones independientes.
- Recuperación simulada localmente, sin caída real del proceso en Azure.
- Reconocimiento automático limitado a la repetición del último lote.
- Comparación completa en memoria adecuada para esta prueba pequeña.
- La base inicial se estableció en un escenario controlado;
  no implementa una inicialización general con escrituras concurrentes.
- La retención de CDC es de tres días; los intervalos vencidos
  requieren revisar la recuperación antes de continuar.
- No se verificó nuevamente order_items en esta sesión de Azure.

Los archivos locales de datos y checkpoints permanecen excluidos de Git.

## Operación y costos

El clúster quedó detenido.
El NAT Gateway y su IP pública se eliminaron al finalizar la sesión.

Se conservaron la VNet, subredes, NSG, workspace, identidad,
datos Bronze, tabla Silver y control de aplicación.

Antes de otra sesión de cómputo clásico debe restablecerse
la conectividad de salida.

El costo definitivo queda pendiente de revisión cuando
Azure Cost Management refleje los consumos de la sesión.

## Estado

Implementación y ejecución local y Azure verificadas.
M8 completado e integrado en main mediante el
[PR #15](https://github.com/DiegoSuarz/azure-retail-lakehouse-platform/pull/15),
commit 212e996.

El siguiente módulo previsto es M9: modelo estrella y capa Gold.
