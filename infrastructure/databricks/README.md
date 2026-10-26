# Azure Databricks para desarrollo

## Objetivo y estado

Workspace desplegado desde Azure Portal.
Las ocho tablas Silver se escribieron en ADLS Gen2,
se verificaron mediante lectura Delta y se registraron en Unity Catalog.

La ejecución fue manual desde notebooks.
La orquestación automática no forma parte de esta carga inicial.

## Configuración comprobada

| Componente | Configuración |
|---|---|
| Grupo de recursos | rg-arlp-dev |
| Región | East US |
| Workspace | dbw-arlp-dev-diego01 |
| Grupo administrado | rg-arlp-dev-databricks-managed |
| Nivel | Premium |
| Tipo de workspace | Hybrid |
| Cómputo | cmp-arlp-dev-silver |
| Topología | Single node |
| Máquina | Standard_D4ds_v4: 4 núcleos y 16 GB |
| Runtime | 16.4 LTS, Spark 3.5.2 y Scala 2.13 |
| Photon | Desactivado |
| Terminación por inactividad | 15 minutos |
| Zona horaria Spark | UTC |

Se utilizó cómputo clásico conectado a la VNet del proyecto.
Serverless no se utilizó para las cargas Silver completadas.

## Red

- VNet: vnet-arlp-dev-databricks, 10.40.0.0/16.
- Subred host: snet-databricks-host, 10.40.1.0/24.
- Subred container: snet-databricks-container, 10.40.2.0/24.
- Subredes delegadas a Microsoft.Databricks/workspaces.
- NSG asociado durante el despliegue de Databricks.
- Secure Cluster Connectivity: nodos sin IP pública.
- NAT Gateway Standard utilizado: nat-arlp-dev-databricks; eliminado al finalizar la sesión.
- IP pública utilizada: pip-arlp-dev-databricks; eliminada al finalizar la sesión.
- Service endpoints de Microsoft.Storage en ambas subredes.
- Firewall de ADLS con denegación por defecto y subredes autorizadas.

La IP pública del NAT proporciona salida a Internet,
no está asignada directamente a los nodos.

## Identidad y permisos

Access Connector: ac-arlp-dev-databricks.
Autenticación mediante identidad administrada asignada por el sistema.

| Ámbito | Rol de la identidad |
|---|---|
| Cuenta starlpdevdiego01 | Storage Blob Delegator |
| Contenedor bronze | Storage Blob Data Reader |
| Contenedor silver | Storage Blob Data Contributor |

Storage Blob Delegator permite solicitar las claves de delegación
necesarias para el acceso temporal a los datos.
Los permisos de lectura y escritura se mantienen por contenedor.

No se utilizaron claves compartidas de almacenamiento.

## Unity Catalog

Credencial de almacenamiento: cred_arlp_adls.

| Ubicación externa | Destino | Acceso |
|---|---|---|
| loc_arlp_bronze | abfss://bronze@starlpdevdiego01.dfs.core.windows.net/ | Solo lectura |
| loc_arlp_silver | abfss://silver@starlpdevdiego01.dfs.core.windows.net/ | Lectura y escritura |

Los eventos de archivos y fallback mode permanecen desactivados.

Catálogo: dbw_arlp_dev_diego01.

- silver_techretail: cinco tablas de SQL Server.
- silver_external: productos de DummyJSON.
- silver_reference: mapeo de productos y tipos de cambio.

Las tablas son externas: sus archivos Delta permanecen en ADLS.

## Código y operación

Los notebooks se encuentran en notebooks/silver/ y reutilizan
los módulos de transformations/silver/.

GitHub está conectado mediante una cuenta vinculada
y la aplicación de Databricks autorizada para el repositorio.

Las cargas iniciales usan mode("error") para impedir sobrescrituras.
Las escrituras de distintas tablas son independientes.
M8 verificó la aplicación por lotes del CDC real de products
mediante MERGE, con control de aplicación persistido en Delta.

El cómputo quedó detenido al finalizar la sesión de carga.
Los datos persistentes permanecen en ADLS.

La reorganización posterior de los notebooks superó la comprobación
de sintaxis, sus nuevas rutas aún no se han probado en Databricks.

## Costos y recursos persistentes

La estimación inicial es provisional y no representa el gasto real:
[Estimación de Databricks](../../docs/costs/M7.7-estimacion-databricks.md).

El tiempo real de uso debe consultarse en Azure Cost Management.
La terminación del cómputo no elimina el NAT Gateway,
su IP pública ni el almacenamiento.

El NAT Gateway y su IP pública se eliminaron al finalizar la sesión.
El cómputo quedó detenido y se conservaron la VNet, las subredes,
el NSG, el workspace, la identidad y los datos.

Antes de la próxima sesión de cómputo:

1. Crear una IP pública Standard y un NAT Gateway Standard.
2. Asociar la IP pública al NAT Gateway.
3. Asociar el NAT Gateway a ambas subredes de Databricks.

La nueva IP pública puede diferir de la utilizada en esta sesión.

## Sesión CDC de M8

El 26 de octubre de 2026 se restablecieron temporalmente el NAT Gateway
y su IP pública, asociados a ambas subredes de Databricks.

El notebook 05_products_cdc_to_silver.ipynb se ejecutó desde
notebooks/silver/ y sus importaciones funcionaron correctamente.
Esto no sustituye la comprobación individual de los cuatro notebooks
de carga inicial reubicados en M7.

La tabla silver_techretail.products terminó con 61 productos.
El control CDC se conservó en Silver bajo _control/products_cdc_application.

Después de verificar los resultados se detuvo el clúster
y se eliminaron nuevamente el NAT Gateway y su IP pública.
