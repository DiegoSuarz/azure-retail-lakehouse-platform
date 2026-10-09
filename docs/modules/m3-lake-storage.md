# M3 — Almacenamiento del Lakehouse

## Resultado

Se creó el almacenamiento del proyecto en Azure y se verificó
la escritura y lectura de un archivo mediante Azure Portal.

La organización de contenedores y rutas está definida en
[Organización del almacenamiento](../design/lake-storage-layout.md).

## Configuración implementada

| Elemento | Configuración |
|---|---|
| Suscripción | Azure for Students |
| Grupo de recursos | rg-arlp-dev |
| Región | East US |
| Cuenta de almacenamiento | starlpdevdiego01 |
| Tipo | StorageV2 |
| Rendimiento | Standard |
| Redundancia | LRS |
| Espacio de nombres jerárquico | Habilitado |
| Nivel de acceso predeterminado | Hot |
| Transferencia segura | Habilitada |
| TLS mínimo | 1.2 |
| Acceso anónimo a blobs | Deshabilitado |
| Acceso mediante claves de cuenta | Deshabilitado |
| Autorización predeterminada del Portal | Microsoft Entra ID |
| Acceso de red pública | Limitado a redes e IP autorizadas |
| SFTP y NFS v3 | Deshabilitados |
| Cifrado | Claves administradas por Microsoft |
| Eliminación temporal de blobs | Siete días |
| Eliminación temporal de contenedores | Siete días |

La IP pública autorizada puede cambiar y deberá revisarse
si aparecen problemas de acceso desde el equipo local.

## Organización de contenedores

| Contenedor | Responsabilidad |
|---|---|
| bronze | Datos originales y metadatos de ingesta |
| silver | Datos limpios y cambios aplicados en Delta |
| gold | Modelo dimensional y resultados analíticos en Delta |
| quarantine | Registros rechazados y motivos |
| serving | Publicaciones Parquet para consumo |
| operations | Manifiestos, auditoría y controles de ejecución |

Los seis contenedores se verificaron en Azure Portal con acceso
Private y estado Available.

Las rutas internas están diseñadas, pero todavía no se han
materializado mediante las cargas del proyecto.

## Acceso verificado

Se asignó Storage Blob Data Contributor al usuario de desarrollo
con alcance sobre la cuenta de almacenamiento.

La asignación se comprobó en Azure Portal.

El rol Owner permite administrar recursos, pero no concede por sí
solo permisos de datos mediante Microsoft Entra ID.

Los accesos de ADF y Databricks se configurarán y validarán
en sus módulos correspondientes.

## Prueba de escritura y lectura

Fecha de validación: 9 de octubre de 2026.

Archivo: storage-smoke-test.txt.
Contenedor: operations.
Tipo: Block blob.
Autorización: Microsoft Entra ID.

Resultados:

- Carga completada desde Azure Portal.
- Descarga completada.
- Contenido descargado comprobado visualmente.
- Archivo conservado temporalmente como evidencia.

Esta prueba confirma el acceso del usuario a ese archivo.
No sustituye las pruebas de integración con ADF o Databricks.

## Costos y protección

Las operaciones de almacenamiento y la capacidad utilizada
pueden consumir crédito.

El costo real de M3 todavía no se ha cuantificado.
No se considera gratuito por el tamaño reducido de la prueba.

Los datos eliminados temporalmente continúan ocupando capacidad
facturable durante su período de retención.

Se mantiene el plan económico definido en
[Plan de presupuesto](../costs/budget-plan.md).

## Aprendizajes clave

- La cuenta de almacenamiento aloja los servicios y su configuración.
- Los contenedores agrupan datos y permiten delimitar permisos.
- Los blobs almacenan archivos y sus propiedades.
- ADLS Gen2 incorpora organización jerárquica para cargas analíticas.
- Un contenedor llamado silver no crea automáticamente tablas Delta.
- Una tabla Delta combina archivos de datos y un registro transaccional.
- Los permisos de administración y de datos son distintos.
- La autorización y las restricciones de red deben cumplirse conjuntamente.
- Cerrar el Portal no elimina recursos ni detiene cargos de almacenamiento.
- La eliminación temporal protege datos y prolonga su almacenamiento.

## Conclusiones

El proyecto dispone de almacenamiento accesible y organizado
para comenzar la integración de las fuentes.

La separación de capas permitirá conservar originales, transformar
datos y publicar resultados con responsabilidades explícitas.

## Pendientes

- Configurar y comprobar los accesos de los servicios consumidores.
- Materializar las rutas durante las cargas correspondientes.
- Cuantificar el consumo real de almacenamiento y operaciones.
- Revisar la IP autorizada cuando cambie la conexión local.
- Retirar el archivo de prueba después de registrar la evidencia.
- Revisar las etiquetas del grupo de recursos y corregir enviroment
  a environment si la corrección todavía no se realizó.

## Estado de cierre

M3 completado para el alcance de almacenamiento e integrado en main.
Commit de integración: f55124b.
Los pendientes descritos conservan su alcance.
