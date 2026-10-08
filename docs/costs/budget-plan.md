# Plan de presupuesto

## Objetivo

Controlar el gasto del proyecto dentro del crédito disponible
de Azure for Students.

Las cantidades de este documento son estimaciones y asignaciones
de planificación, no representan consumo medido.

## Límites y alertas

- Límite total de gasto adicional del proyecto: USD 80.
- Presupuesto mensual de alertas: USD 20.
- Nombre del presupuesto: budget-arlp-dev-monthly.
- Alcance de las alertas: toda la suscripción, sin filtros.
- Umbrales de costo real: 25 %, 50 %, 75 % y 100 %.
- Importes correspondientes: USD 5, 10, 15 y 20.
- Notificaciones por correo.
- Sin apagado automático asociado al presupuesto.

El presupuesto mensual y el límite total son controles distintos.
Las alertas no constituyen un límite automático de gasto y pueden
recibirse después de que se haya producido el consumo.

Al alcanzar USD 60 acumulados del proyecto, se revisará el trabajo
pendiente. Al alcanzar USD 80 se detendrán las ejecuciones con costo
y se procederá a retirar los recursos temporales.

## Estimación original

Archivo de referencia:
[M0.6-estimacion-costos-azure.xlsx](M0.6-estimacion-costos-azure.xlsx).

- Exportación: 6 de octubre de 2026, 03:00:46 UTC.
- Moneda: USD.
- Región candidata: East US.
- Programa mostrado: Microsoft Customer Agreement (MCA).
- Total exportado: USD 41.1115, mostrado como USD 41.11.
- Costo inicial estimado: USD 0.

La exportación conserva los valores originales de la calculadora.
No acredita tarifas particulares de la suscripción estudiantil.

El total combina distintas duraciones de uso y no representa
un mes de funcionamiento continuo de toda la plataforma.

## Escenario provisional ajustado

| Componente | Supuesto | Costo aproximado USD |
|---|---|---:|
| Databricks | Premium, un D4s_v3, 10 horas y 0.75 DBU por hora | 6.05 |
| NAT Gateway | 168 horas y 10 GB procesados | 8.01 |
| ADLS Gen2 | 10 GB de capacidad media mensual y operaciones estimadas | 1.62 |
| Azure Data Factory | Cantidades de ejecución y operaciones de la exportación | 4.36 |
| Synapse Serverless | 0.1 TB procesados | 0.50 |
| Key Vault | 10 000 operaciones | 0.03 |
| IP pública | Una IP Standard durante 168 horas | 0.84 |
| Disco administrado | Hipótesis de un P10 durante 10 horas | 0.27 |
| Ancho de banda | 10 GB de salida a Internet, dentro de la franquicia aplicable | 0.00 |

El disco P10 figura en el Excel con USD 19.71 por un mes completo.
El ajuste provisional utiliza una referencia de 730 horas:

19.71 / 730 * 10 = USD 0.27 aproximadamente.

Con los valores sin redondear:

- Subtotal ajustado: USD 21.67 aproximadamente.
- Contingencia ilustrativa del 20 %: USD 4.33 aproximadamente.
- Referencia del escenario con contingencia: USD 26.

Este ajuste supone un solo disco que existe durante diez horas.
La cantidad, el tamaño y la duración reales de los discos de Databricks
se verificarán antes de considerar cerrada la estimación.

USD 26 no es el costo del proyecto completo. Tampoco debe multiplicarse
directamente por cada ventana, porque incluye cantidades mensuales
de otros servicios.

## Distribución del límite total

| Partida | Asignación máxima USD |
|---|---:|
| Dos ventanas de Databricks, NAT, IP y discos | 35 |
| Ingesta, almacenamiento, consultas y secretos durante el desarrollo | 20 |
| Almacenamiento administrado, monitorización y ajustes pendientes | 10 |
| Contingencia del proyecto | 15 |
| Total | 80 |

Estas asignaciones deberán revisarse con el consumo real.
La contingencia del 20 % del escenario es ilustrativa y no se suma
como una reserva adicional a los USD 80.

## Calendario de uso

| Etapa | Trabajo | Infraestructura prevista |
|---|---|---|
| Preparación | Repositorio, OLTP, datos sintéticos y código | Sin Databricks desplegado |
| Ingesta | Carga inicial, API y archivos | Recursos de ingesta y almacenamiento, ejecuciones acotadas |
| Ventana 1 | Silver, calidad, CDC y Delta | Hasta siete días de infraestructura y diez horas de cómputo |
| Preparación intermedia | Correcciones y preparación de Gold/SCD | Trabajo local, retirada de infraestructura temporal |
| Ventana 2 | Gold, SCD, time travel y pruebas integradas | Hasta siete días de infraestructura y diez horas de cómputo |
| Consumo y cierre | Synapse, Power BI y evidencias | Consultas limitadas y retirada final |

Las ventanas son objetivos iniciales de planificación.
No garantizan que el trabajo pueda completarse en veinte horas
de cómputo ni que los recursos estén disponibles.

## Reglas de operación

1. Preparar código y datos antes de abrir una ventana de Databricks.
2. Terminar el cómputo al finalizar cada sesión.
3. Controlar por separado la duración del cómputo y de la infraestructura.
4. Conservar código y configuraciones en Git y datos persistentes en ADLS.
5. Verificar el procedimiento antes de retirar el workspace temporal.
6. Revisar los recursos restantes y el consumo después de cada ventana.
7. Mantener las primeras ejecuciones manuales.
8. Recalcular el costo antes de ampliar horas, volumen o frecuencia.

## Partidas pendientes de verificar

- Disponibilidad y cuotas del nodo de Databricks.
- Cantidad, tipo, tamaño y duración de los discos reales.
- Almacenamiento administrado del workspace.
- Monitorización y volumen de registros.
- Costos de red durante períodos sin cómputo.
- Volumen real de operaciones de almacenamiento y de ADF.
- Consumo de otros recursos de la misma suscripción.
- Procedimiento de retirada y reconstrucción del workspace.

## Seguimiento

Durante las ventanas activas se revisará el consumo reportado
y se registrarán los cambios relevantes en los supuestos.

El gasto adicional del proyecto se distinguirá del consumo previo
y de otros proyectos en la suscripción.

Las decisiones sobre nuevas ejecuciones considerarán tanto
el consumo reportado como los cargos todavía pendientes de aparecer.
