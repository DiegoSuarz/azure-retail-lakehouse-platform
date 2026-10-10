# Hoja de ruta

## Objetivo

Desarrollar una plataforma Lakehouse para una tienda ficticia
de artículos tecnológicos, desde las fuentes hasta el consumo
analítico, con documentación en español.

Los módulos representan entregables. Su ejecución podrá agruparse
en ventanas de uso de Azure para controlar los costos.

## Módulos

| Módulo | Alcance | Estado |
|---|---|---|
| M0 | Identidad, alcance, arquitectura, suscripción y presupuesto | Completado como diseño |
| M1 | Repositorio, documentación y entorno local | Completado |
| M2 | SQL Server OLTP, datos sintéticos y contratos de fuentes | Completado |
| M3 | ADLS Gen2 y organización del almacenamiento | Completado |
| M4 | ADF, SHIR y fundamentos de orquestación | Completado |
| M5 | Ingesta inicial y cargas a Bronze | Pendiente |
| M6 | Reglas de calidad, validaciones y cuarentena | Pendiente |
| M7 | Transformaciones PySpark y tablas Delta en Silver | Pendiente |
| M8 | CDC simulado, incrementales e idempotencia | Pendiente |
| M9 | Modelo estrella y capa Gold | Pendiente |
| M10 | Dimensiones con SCD tipo 1 y tipo 2 | Pendiente |
| M11 | MERGE, evolución de esquemas, time travel y retención | Pendiente |
| M12 | Publicación Parquet y vistas en Synapse Serverless | Pendiente |
| M13 | Modelo analítico y visualizaciones en Power BI Desktop | Pendiente |
| M14 | Auditoría, monitorización y seguimiento operativo | Pendiente |
| M15 | Infraestructura reproducible con Bicep | Pendiente |
| M16 | Integración continua y comprobaciones de seguridad | Pendiente |
| M17 | Procedimientos de ejecución, recuperación y retirada | Pendiente |
| M18 | Evidencias, documentación final y presentación de portafolio | Pendiente |

## Micromódulos de M1

| Micromódulo | Entregable | Estado |
|---|---|---|
| M1.1 | Repositorio y estructura inicial | Completado |
| M1.2 | .gitignore y .env.example | Completado |
| M1.3 | Documentación de diseño, presupuesto y roadmap | Completado |
| M1.4 | Entorno virtual y verificación de herramientas locales | Completado |
| M1.5 | Primer commit, publicación en GitHub y cierre | Completado |

## Dependencias principales

- Los contratos y claves de M2 preceden a las cargas de M5.
- ADLS y la orquestación básica preceden a la ingesta.
- Los controles de calidad condicionan el avance de Silver a Gold.
- Los incrementales requieren corte temporal, ordenamiento y deduplicación.
- SCD requiere definir qué atributos conservan historial.
- La publicación para consumo requiere resultados reconciliados.
- La automatización programada requiere validar funcionamiento y costo.

La orquestación de ADF evolucionará a lo largo de los módulos.
M4 establecerá su base, las actividades de transformación y publicación
se incorporarán cuando sus implementaciones estén disponibles.

Los controles mínimos de auditoría, seguridad y costos se aplicarán
desde las primeras cargas. M14 y M16 ampliarán y consolidarán
estos controles.

## Plan de ejecución económica

La preparación de fuentes, contratos y código se realizará localmente
antes de desplegar Databricks.

Se plantean dos ventanas iniciales:

1. Silver, calidad, CDC y fundamentos de Delta.
2. Gold, SCD, time travel y pruebas integradas.

Cada ventana tiene como objetivo hasta siete días de infraestructura
y diez horas de cómputo. Estas cantidades deberán ajustarse según
el consumo y el avance real.

El trabajo posterior de monitorización, Bicep y CI podrá requerir
ejecuciones adicionales. Se estimará su costo antes de realizarlas,
no se considera incluido automáticamente en las dos ventanas.

El detalle económico se encuentra en
[costs/budget-plan.md](costs/budget-plan.md).

## Condiciones previas al despliegue de Databricks

- Verificar disponibilidad y cuotas del nodo seleccionado.
- Confirmar elegibilidad del servicio en la suscripción.
- Completar la estimación de discos y almacenamiento administrado.
- Definir monitorización y volumen de registros.
- Verificar el procedimiento de retirada y reconstrucción.
- Confirmar que la ventana cabe en el presupuesto restante.

## Criterio de cierre de cada módulo

Un módulo se marcará como completado cuando:

1. Su entregable esté implementado.
2. Las comprobaciones pertinentes tengan resultados verificables.
3. La documentación refleje el comportamiento final.
4. Los cambios estén registrados en Git.
5. Los recursos temporales y costos asociados estén revisados.

## Estado de implementación

M2 está completado e integrado en main.
M3 está completado e integrado en main.
M4 está completado e integrado en main.
El siguiente módulo es M5: ingesta inicial y cargas a Bronze.
La conectividad integrada de ADF está implementada.
Las cargas completas y las capas de procesamiento siguen pendientes.

Las comprobaciones de disponibilidad y costos pendientes de M0
se resolverán antes de los despliegues correspondientes.

## Cierres de módulos

- [M2 — Fuentes y contratos](modules/m2-source-system.md)
- [M3 — Almacenamiento del Lakehouse](modules/m3-lake-storage.md)
- [M4 — ADF, SHIR y fundamentos de orquestación](modules/m4-data-orchestration.md)
