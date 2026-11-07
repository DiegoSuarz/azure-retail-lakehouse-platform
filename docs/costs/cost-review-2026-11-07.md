# Revisión provisional de costos — 7 de noviembre de 2026

## Alcance

Consulta de Azure Cost Management para Azure for Students.
Período seleccionado: 1 de octubre a 7 de noviembre de 2026.
Moneda: USD.
Fuente: exportación cost-analysis.csv, con 47 registros diarios
agrupados por grupo de recursos.

## Consumo observado

| Grupo de recursos | Costo USD |
|---|---:|
| rg-arlp-dev | 4.803047 |
| rg-arlp-dev-databricks-managed | 1.220295 |
| Total | 6.023342 |

El portal muestra USD 6.02 después del redondeo.
El total incluye ambos grupos de recursos y trabajo de varios módulos.
No representa exclusivamente el costo de M9 o M10.

## Límites de la revisión

Los registros del 7 de noviembre suman aproximadamente USD 0.000708.
Esta exportación no permite considerar definitivo el costo de la
ejecución M10 realizada ese día.

El archivo no contiene el detalle por servicio o recurso necesario
para atribuir los importes a cada módulo.
La previsión del portal no se considera consumo real.

## Recursos temporales

Después de la demostración M10:

- El cómputo de Databricks quedó detenido.
- Ambas subredes quedaron sin asociación al NAT Gateway.
- El NAT Gateway y su IP pública fueron eliminados.
- Los datos y el informe de ejecución permanecen en ADLS.

## Seguimiento

Repetir la consulta para el mismo período cuando se hayan incorporado
los cargos pendientes y comparar los resultados.
La consulta de costos no requiere iniciar el cómputo de Databricks.

La revisión del costo definitivo de M9 y M10 permanece pendiente.
Esta revisión complementa el plan de presupuesto y no modifica sus límites.
