# Azure Databricks para desarrollo

## Objetivo

Ejecutar en Azure las transformaciones Silver verificadas localmente.
Los datos persistirán en ADLS Gen2.

## Configuración propuesta

| Componente | Configuración |
|---|---|
| Grupo de recursos | rg-arlp-dev |
| Región | East US |
| Workspace | dbw-arlp-dev-diego01 |
| Nivel | Premium |
| Cómputo | Single node |
| Tamaño candidato | Standard_D4ds_v4 |
| Alternativas | Standard_D4s_v4, Standard_D4as_v4 |
| Terminación por inactividad | 15 minutos |
| Runtime candidato | 16.4 LTS, pendiente de confirmar |
| Zona horaria Spark | UTC |

Los tres tamaños candidatos no presentan restricciones en la
consulta de Azure. Su disponibilidad en Databricks y capacidad
real siguen pendientes de comprobar.

La cuota regional es de 6 vCPU y la cuota de cada familia
candidata es de 4 vCPU. Se utilizará un único nodo.

## Red

- VNet propia con dos subredes dedicadas a Databricks.
- Conectividad segura del clúster, sin IP pública en los nodos.
- NAT Gateway e IP pública Standard para salida a Internet.
- Service endpoints de Microsoft.Storage en las subredes.
- Reglas de Storage para permitir las subredes autorizadas.
- Mantener el firewall de ADLS con denegación por defecto.

La IP pública del NAT corresponde a la salida de la red,
no a una IP pública asignada a cada nodo.

## Acceso a datos

Se utilizará un Access Connector con identidad administrada
y credenciales de almacenamiento de Unity Catalog.

Permisos iniciales previstos por contenedor:

- bronze: Storage Blob Data Reader.
- silver: Storage Blob Data Contributor.

Los permisos para otras capas se incorporarán cuando sean necesarios.
No se utilizarán claves compartidas de Storage.

## Operación y costos

El cómputo se iniciará únicamente durante las sesiones de trabajo.
Se terminará al finalizar cada sesión.

El NAT Gateway y su IP pública pueden generar cargos aunque
el cómputo esté detenido. Se retirarán al cerrar la ventana temporal,
siguiendo un procedimiento que preserve los datos y el código.

La estimación deberá incluir DBU, máquina virtual, discos,
NAT Gateway, IP pública y almacenamiento administrado.

## Estado

Propuesta de despliegue. No se han creado recursos de Databricks.

Pendientes antes de desplegar:

- Verificar los recursos reales frente a la estimación provisional.
- Confirmar runtime y tamaño ofrecidos por Databricks.
- Verificar permisos para crear recursos y asignar roles.
- Definir los comandos de despliegue y retirada.
- Confirmar habilitación y permisos de Unity Catalog.

El crédito mostrado el 20 de octubre de 2026 es USD 95.46.
Su vencimiento permanece pendiente de confirmar.

## Estimación provisional

El escenario inicial considera dos horas de cómputo y 24 horas de red.
Su referencia ajustada es aproximadamente USD 3.40, o USD 4.08 con margen del 20 %.

Supuestos y limitaciones:
[Estimación de Databricks](../../docs/costs/M7.7-estimacion-databricks.md).
