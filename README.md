# Plataforma Lakehouse de Retail Tecnológico en Azure

Proyecto de Data Engineering para una tienda ficticia de artículos
tecnológicos en Perú, con datos comerciales sintéticos.

## Objetivo

Integrar SQL Server local, API y archivos CSV/JSON en una plataforma
con arquitectura medallion, transformaciones PySpark, tablas Delta
y orquestación mediante Azure Data Factory.

El alcance incluye cargas incrementales, CDC simulado, SCD,
controles de calidad y publicación para consumo analítico.

## Arquitectura prevista

- Ingesta y orquestación: Azure Data Factory.
- Conexión con SQL Server local: Self-hosted Integration Runtime.
- Almacenamiento: ADLS Gen2.
- Transformaciones: Azure Databricks, PySpark y Delta.
- Capas de datos: Bronze, Silver y Gold.
- Publicación: Parquet y vistas en Synapse Serverless SQL.
- Visualización: Power BI Desktop.
- Secretos: Azure Key Vault.

## Documentación

- [Descripción del proyecto](docs/design/project-overview.md)
- [Arquitectura inicial](docs/design/architecture.md)
- [Plan de presupuesto](docs/costs/budget-plan.md)
- [Hoja de ruta](docs/roadmap.md)
- [Entorno de desarrollo local](docs/local-development.md)
- [Estimación original de Azure](docs/costs/M0.6-estimacion-costos-azure.xlsx)

## Estructura del repositorio

| Carpeta | Propósito |
|---|---|
| docs | Diseño, costos y procedimientos |
| infrastructure | Plantillas y configuración de infraestructura |
| sources | Base OLTP y generación de datos sintéticos |
| ingestion | Ingesta, contratos y configuración de ADF |
| transformations | Procesamiento PySpark y Delta |
| serving | SQL de consumo y archivos de Power BI |
| tests | Validaciones de datos y comportamiento |

## Convenciones

- Carpetas, scripts e identificadores técnicos en inglés.
- Documentación en español.
- Variables locales en .env, excluido de Git.
- Plantilla de configuración en .env.example.
- Sin credenciales reales en el repositorio.

## Estado

M0 completado como diseño. M1, M2, M3 y M4 completados. M5 pendiente.

El origen SQL Server y el almacenamiento en ADLS Gen2 están implementados.
La conectividad SQL Server–ADLS mediante ADF está validada.
Las cargas completas, las transformaciones y el consumo analítico
todavía están pendientes.

La disponibilidad y los costos pendientes se verificarán antes
de los despliegues correspondientes.
