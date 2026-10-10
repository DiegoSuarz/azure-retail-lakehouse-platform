# Configuración de Azure Data Factory

## Objetivo

Conservar la configuración exportada desde ADF Studio en M4.

Cuenta de Data Factory: adf-arlp-dev-diego01.
Grupo de recursos: rg-arlp-dev.
Región: East US.

## Archivos

| Archivo dentro de arm/ | Contenido |
|---|---|
| ARMTemplateForFactory.json | SHIR, servicios vinculados, datasets y pipeline |
| ARMTemplateParametersForFactory.json | Valores de los parámetros del entorno dev |
| factory/adf-arlp-dev-diego01_ARMTemplateForFactory.json | Recurso Data Factory e identidad administrada |
| factory/adf-arlp-dev-diego01_ARMTemplateParametersForFactory.json | Parámetros del recurso Data Factory |

Las plantillas enlazadas del ZIP no se incorporaron porque
la plantilla principal contiene los siete recursos internos
utilizados en esta etapa.

## Configuración conservada

- Integration Runtime: shir-arlp-dev-local.
- Servicios vinculados: ls_key_vault, ls_sqlserver_local y ls_adls_gen2.
- Datasets: ds_sqlserver_categories y ds_adls_categories_smoke_test.
- Pipeline: pl_connectivity_sqlserver_adls.
- Actividad: copy_categories_smoke_test.

El dataset de destino especifica categories.csv.
La actividad conserva fileExtension con valor .txt, generado
por Studio; el archivo obtenido utiliza el nombre explícito del dataset.

## Credenciales

La conexión SQL contiene una referencia al secreto
sqlserver-retail-reader-password de Key Vault.

La exportación revisada no contiene la contraseña SQL,
claves de registro de SHIR ni claves de almacenamiento.

Los nombres de recursos, endpoints y usuarios son configuración,
no credenciales de autenticación.

## Requisitos de reconstrucción

Para reconstruir una instalación se requiere:

1. Disponer de SQL Server y TechRetail_OLTP.
2. Configurar retail_reader y sus permisos de lectura.
3. Disponer de ADLS Gen2 y los contenedores correspondientes.
4. Disponer de Key Vault y crear el secreto con el valor correcto.
5. Crear Data Factory con identidad administrada.
6. Aplicar los permisos RBAC de esa identidad en Key Vault y ADLS.
7. Desplegar las definiciones internas de ADF.
8. Instalar y registrar el nodo Windows de SHIR.
9. Configurar el acceso de red y validar las conexiones.

Las plantillas no conservan el valor del secreto, las asignaciones
RBAC, las reglas de red de ADLS y Key Vault, ni la instalación
y el registro del nodo local.

La plantilla del recurso Data Factory incluye principalId y tenantId
de la identidad exportada. Son metadatos del entorno de origen;
una identidad recreada recibirá su propio identificador.
Se revisarán estos campos antes de preparar un despliegue reutilizable.

Los parámetros contienen los nombres y endpoints del entorno dev.
Deberán revisarse antes de usar las plantillas en otro entorno.

## Alcance de validación

La configuración de origen funcionó en la prueba integrada de M4.
Los cuatro archivos exportados se comprobaron como JSON válido.

Todavía no se ha probado un despliegue desde estas plantillas.
La exportación constituye una referencia versionada, no una
reconstrucción completa validada.

La automatización de infraestructura se ampliará en M15 con Bicep.
