# M4 — ADF, SHIR y fundamentos de orquestación

## Resultado

Se implementó y validó una conexión integrada desde SQL Server
local hasta ADLS Gen2 mediante Azure Data Factory.

La prueba copió las seis categorías del origen a un archivo CSV
en el contenedor operations. La carga inicial completa a Bronze
corresponde a M5.

## Recursos utilizados

| Componente | Nombre | Función |
|---|---|---|
| Azure Data Factory V2 | adf-arlp-dev-diego01 | Coordinar y ejecutar la copia |
| Self-hosted Integration Runtime | shir-arlp-dev-local | Acceder al origen desde Windows |
| Azure Key Vault Standard | kv-arlp-dev-diego01 | Conservar la contraseña de extracción |
| ADLS Gen2 | starlpdevdiego01 | Almacenar el archivo de prueba |
| SQL Server local | TechRetail_OLTP | Proporcionar las categorías |

Los recursos de Azure pertenecen a rg-arlp-dev, en East US.
SQL Server y SHIR se ejecutan en el equipo local.

## Identidades y permisos

ADF utiliza su identidad administrada asignada por el sistema.

Permisos configurados para esa identidad:

- Key Vault Secrets User sobre el almacén de secretos.
- Storage Blob Data Contributor sobre el contenedor bronze.
- Storage Blob Data Contributor sobre el contenedor operations.

La extracción utiliza retail_reader, con SELECT sobre las cinco
tablas del negocio y sin permisos de escritura.

La contraseña se obtiene del secreto sqlserver-retail-reader-password.
Su valor no se incorpora a la documentación ni al repositorio.

## Servicios vinculados

| Nombre | Tipo | Configuración principal |
|---|---|---|
| ls_key_vault | Azure Key Vault | Acceso mediante identidad administrada de ADF |
| ls_sqlserver_local | SQL Server | localhost,1433; TechRetail_OLTP; retail_reader |
| ls_adls_gen2 | ADLS Gen2 | Identidad administrada de ADF; starlpdevdiego01 |

SQL Server y ADLS utilizan shir-arlp-dev-local.

localhost identifica el equipo Windows donde se ejecuta SHIR.
No corresponde al localhost de WSL ni a un servidor de Azure.

La conexión SQL utiliza autenticación SQL, cifrado Mandatory
y Trust server certificate habilitado para el entorno local.

## Prueba integrada

- Pipeline: pl_connectivity_sqlserver_adls.
- Actividad: copy_categories_smoke_test.
- Dataset de origen: ds_sqlserver_categories.
- Tabla: dbo.categories.
- Dataset de destino: ds_adls_categories_smoke_test.
- Contenedor: operations.
- Ruta: connectivity/sqlserver/categories.csv.
- Formato: CSV UTF-8, separado por comas y con encabezado.
- Ejecución: manual.
- Tiempo de espera de la actividad: diez minutos.
- Reintentos: cero.
- Sin staging ni registro adicional de la actividad Copy.

## Evidencias

| Control | Resultado |
|---|---|
| Estado del pipeline | Succeeded |
| Estado de la actividad | Succeeded |
| Filas leídas | 6 |
| Filas escritas | 6 |
| Archivos escritos | 1 |
| Tamaño del archivo | 481 bytes |
| Duración de la actividad | 25 segundos |

Identificador de ejecución del pipeline:

    d9b87060-6da3-4d82-8152-63e019274813

Se descargó y revisó el archivo generado.

Contiene category_id, category_name, created_at y updated_at,
con las seis categorías esperadas y fechas coherentes con el origen.

La comprobación automática de consistencia de Copy no se habilitó.
La evidencia corresponde a los conteos reportados y la revisión
visual del archivo, sin una reconciliación automatizada completa.

## Costos y operación

La prueba genera consumo de ADF, operaciones de almacenamiento
y acceso al secreto de Key Vault.

El archivo genera un cargo por capacidad mientras se conserve.
Si se elimina, soft delete puede mantenerlo durante siete días.

SHIR utiliza el equipo local y requiere que este permanezca
encendido y conectado durante las ejecuciones.

El costo real de M4 todavía no se ha reconciliado con Cost Management.

## Aprendizajes y puntos clave

- Un servicio vinculado define cómo conectarse a un recurso.
- Un dataset identifica los datos y su estructura.
- Una actividad ejecuta una operación dentro del pipeline.
- SHIR permite acceder al origen local sin publicar SQL Server en Internet.
- La identidad administrada evita usar claves de almacenamiento.
- Key Vault separa la contraseña de la definición de la conexión.
- Autenticación, permisos y acceso de red son controles diferentes.
- Una ejecución exitosa debe complementarse con revisión del resultado.

## Pendientes

- Probar la reconstrucción mediante las plantillas en una etapa posterior.
- Automatizar los requisitos de reconstrucción en M15.
- Revisar el consumo reportado y la limpieza del archivo de prueba.
- Verificar los requisitos de Parquet en SHIR antes de M5.
- Implementar la carga inicial completa y sus controles en M5.

## Conclusión

La conectividad necesaria para iniciar la ingesta está validada.

Esta prueba establece la base de orquestación del proyecto.
Las cargas completas, los incrementales y las dependencias entre
Bronze, Silver, Gold y publicación se incorporarán posteriormente.

## Estado

Prueba integrada validada.
Configuración exportada y requisitos de reconstrucción documentados.
Cierre del módulo en progreso.
M4 todavía no está cerrado ni integrado en main.
