# Escenarios de datos incrementales

## Objetivo

Preparar escenarios reproducibles para validar nuevos pedidos,
CDC simulado, deduplicación y cambios de atributos.

Los resultados descritos son expectativas de prueba.
El procesamiento incremental todavía no está implementado.

## Corte temporal

- Conjunto inicial: registros anteriores a 2026-10-01T00:00:00.000Z.
- Incrementales: registros desde ese instante, inclusive.
- Fechas técnicas y eventos: UTC.
- Interpretación de fechas comerciales: America/Lima.

El corte corresponde al conjunto sintético.
No constituye una marca de agua de extracción real de SQL Server.

TechRetail_OLTP conservará el conjunto inicial mientras se preparan
los incrementales como archivos independientes.

## Identidad y reproducibilidad

Los escenarios partirán de data/initial y su manifiesto validado.

El generador deberá:

- Verificar los hashes del conjunto inicial.
- Seleccionar claves existentes a partir de los datos.
- Asignar claves nuevas sin colisiones.
- Utilizar fechas e identificadores de eventos deterministas.
- Producir imágenes completas para los eventos.
- Publicar cada manifiesto después de escribir sus archivos.
- Rechazar carpetas de salida que ya contengan datos.

No se supondrá que un pedido específico tiene un estado determinado:
se seleccionarán pedidos por su estado real en el conjunto inicial.

## Escenarios funcionales

| Código | Caso | Resultado esperado |
|---|---|---|
| S01 | Nuevos pedidos y líneas válidos | Incorporar todas las claves nuevas |
| S02 | Cliente cambia de ciudad y región | Actualizar el estado vigente y preparar evidencia para SCD |
| S03 | Producto cambia de precio de catálogo | Actualizar list_price sin modificar ventas anteriores |
| S04 | Pedido pending pasa a confirmed | Incorporar su importe y unidades a ventas confirmadas |
| S05 | Pedido confirmed pasa a cancelled | Retirar su contribución de ventas confirmadas |
| S06 | Producto se desactiva | Preservar su clave y las referencias históricas |
| S07 | Pedido nuevo del lote recibe un evento | Incorporar primero el pedido y sus líneas; aplicar después el evento |

Los cambios de atributos no determinan todavía qué dimensiones
utilizarán SCD tipo 1 o tipo 2.

## Escenarios de reproceso y orden

| Código | Caso | Resultado esperado |
|---|---|---|
| S08 | Reprocesar el mismo lote sin cambios | No duplicar registros ni aplicar cambios nuevamente |
| S09 | Repetir un evento idéntico en otro lote | Reconocer event_id y evitar una segunda aplicación |
| S10 | Recibir secuencia 2 antes de secuencia 1 | Mantener el evento pendiente hasta resolver el hueco |
| S11 | Dos cambios comparten event_time | Resolver el orden mediante event_sequence |
| S12 | Recibir nuevamente un evento anterior ya aplicado | No sobrescribir el estado posterior |

El orden de llegada no sustituirá el orden de negocio.
Las secuencias serán consecutivas por entidad y clave.

## Escenarios de rechazo y conflicto

| Código | Caso | Resultado esperado |
|---|---|---|
| S13 | event_id repetido con contenido diferente | Registrar conflicto y no aplicar el evento contradictorio |
| S14 | Misma entidad, clave y secuencia con otro event_id | Registrar conflicto |
| S15 | Pedido cancelled intenta volver a confirmed | Rechazar la transición |
| S16 | Línea referencia un producto inexistente | Separar el registro y evitar publicar el pedido incompleto |
| S17 | Descuento supera el importe bruto | Rechazar la línea y evitar publicar el pedido incompleto |
| S18 | Falta un archivo declarado o cambia su hash | Bloquear el lote antes del procesamiento de negocio |
| S19 | Pedido existente reaparece con contenido diferente | Registrar conflicto sin sobrescribirlo como pedido nuevo |
| S20 | Evento modifica un atributo estable | Rechazar su aplicación |

Los casos inválidos se mantendrán separados de los lotes funcionales.
Cada caso identificará qué regla incumple deliberadamente.

Un archivo válido según su hash puede contener datos inválidos
según las reglas del negocio.

## Controles esperados

Se preparará un archivo de expectativas separado del manifiesto
de transporte, para registrar:

- Escenarios incluidos y orden de entrega.
- Claves nuevas y eventos únicos.
- Registros aceptados, pendientes, rechazados y en conflicto.
- Estado final esperado de los registros modificados.
- Conteos finales de pedidos y líneas.
- Variación de ventas netas confirmadas y unidades confirmadas.

Los importes se calcularán con Decimal a partir de las líneas.
Una cancelación descontará la contribución del pedido confirmado.
Un cambio de list_price no alterará unit_price histórico.

Los escenarios de rechazo partirán de una base conocida y se probarán
de forma aislada para no contaminar los controles funcionales.

## Límite de implementación

M2 preparará las fuentes y sus resultados esperados.

La aplicación efectiva de eventos, las marcas de agua y la idempotencia
se implementarán en los módulos de procesamiento incremental.

La conservación del historial dimensional se implementará
en el módulo de SCD.

## Estado

Escenarios S01–S20 generados y comprobados localmente en M2.6.
Las comprobaciones incluyen reconciliación del primer lote,
simulación de orden y reprocesos, y anomalías deliberadas.

La ejecución se documenta en
[Generación incremental](../../sources/generators/INCREMENTAL.md).

El procesamiento cloud y los históricos SCD siguen pendientes.
