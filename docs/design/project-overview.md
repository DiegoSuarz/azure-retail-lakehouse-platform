# Descripción del proyecto

## Identidad

- Nombre: Plataforma Lakehouse de Retail Tecnológico en Azure.
- Repositorio: azure-retail-lakehouse-platform.
- Código del proyecto: arlp.
- Entorno inicial: dev.
- Negocio: tienda ficticia de artículos tecnológicos en Perú.
- Datos comerciales: sintéticos.
- Moneda comercial: PEN.
- Documentación: español.
- Carpetas, scripts e identificadores técnicos: inglés.

## Objetivo

Construir una plataforma de Data Engineering que integre datos de
distintas fuentes, procese cargas iniciales e incrementales y publique
información analítica sobre ventas de artículos tecnológicos.

El proyecto aplicará arquitectura medallion, tablas Delta,
orquestación, controles de calidad y gestión de históricos,
con un presupuesto limitado de Azure for Students.

## Fuentes de datos

| Fuente | Función |
|---|---|
| SQL Server local: TechRetail_OLTP | Carga inicial de clientes, productos, pedidos y detalle de pedidos |
| CSV sintéticos | Nuevos pedidos y sus detalles |
| JSON sintéticos | Eventos de cambios en clientes, productos y estados de pedidos |
| API DummyJSON | Catálogo ficticio complementario de productos tecnológicos |
| API BCRPData | Información histórica y diaria del tipo de cambio USD/PEN |

Las series de BCRPData y el mapeo del catálogo externo se definirán
durante la preparación de las fuentes.

Las API externas no se considerarán fuentes autoritativas de las
ventas sintéticas. Sus identificadores se relacionarán explícitamente
con las claves del negocio.

## Alcance funcional

1. Extraer una carga inicial coherente desde SQL Server local.
2. Incorporar API y archivos CSV/JSON en la ingesta.
3. Preservar los datos originales en Bronze.
4. Limpiar, validar y estandarizar los datos en Silver.
5. Construir un modelo estrella y métricas comerciales en Gold.
6. Procesar cargas incrementales de forma idempotente.
7. Aplicar CDC simulado y SCD tipo 1 y tipo 2.
8. Explorar MERGE, evolución de esquemas y time travel en Delta.
9. Orquestar las cargas con Azure Data Factory.
10. Publicar datos para Synapse Serverless y Power BI Desktop.
11. Incorporar auditoría, cuarentena y seguimiento de costos.

## Indicadores iniciales

- Ventas netas de pedidos confirmados, después de descuentos.
- Unidades vendidas.
- Ticket promedio.
- Productos con mayores ventas.
- Clientes recurrentes.

Las fórmulas, el tratamiento de cancelaciones y el grano de cada
indicador se documentarán antes de implementar Gold.

El cálculo del margen comercial queda fuera del alcance inicial.

## Límites

- Un único entorno de desarrollo.
- Procesamiento por lotes.
- Datos sintéticos, sin información personal real.
- CDC simulado mediante eventos, sin captura del log de SQL Server.
- SQL Server permanecerá en el equipo local.
- Power BI Desktop con importación y actualización manual.
- Sin requisitos de disponibilidad ni operación productiva continua.

## Condiciones de consistencia

La carga inicial y los incrementales compartirán claves de negocio.

Se definirá un corte temporal para separar la carga inicial de los
eventos posteriores y evitar pérdidas o duplicados.

Los eventos de cambio tendrán identificador, operación, fecha y claves
de negocio. Se establecerán reglas de ordenamiento y deduplicación.

## Restricciones económicas

- Límite total de gasto adicional del proyecto: USD 80.
- Presupuesto mensual de alertas: USD 20.
- Revisión del alcance pendiente al alcanzar USD 60 acumulados.
- Retirada de recursos temporales al finalizar cada ventana de uso.

La estimación inicial no garantiza el costo final ni la disponibilidad
de los recursos. Antes de desplegar Databricks se verificarán cuotas,
discos, almacenamiento administrado y procedimiento de retirada.

## Criterios de éxito

- Una ejecución completa desde las fuentes hasta el consumo analítico.
- Reprocesar una carga sin duplicar registros de negocio.
- Demostrar cambios e históricos con resultados verificables.
- Identificar y separar registros que incumplan reglas de calidad.
- Reconciliar cantidades e importes entre fuentes y resultados.
- Mantener código, configuración y documentación reproducibles.
- Completar el trabajo dentro del límite económico definido.

## Capa de orquestación

Azure Data Factory (ADF) coordinará el flujo de procesamiento
desde la ingesta hasta la publicación de datos para consumo.

Sus responsabilidades serán:

- Ejecutar la carga inicial de SQL Server local mediante SHIR.
- Coordinar la ingesta de API y archivos CSV/JSON.
- Invocar notebooks de Databricks para procesar Bronze, Silver y Gold.
- Definir dependencias entre actividades y capas.
- Administrar parámetros, reintentos y tiempos de espera.
- Ejecutar controles de calidad y condicionar el avance a sus resultados.
- Coordinar la publicación de las exportaciones Parquet para consumo.
- Registrar el estado de las ejecuciones y los errores.

Las primeras ejecuciones serán manuales. Los desencadenadores
programados se incorporarán cuando el flujo esté validado
y su frecuencia sea compatible con el presupuesto.

ADF coordinará las actividades; las transformaciones de datos
se implementarán en PySpark sobre Databricks.
