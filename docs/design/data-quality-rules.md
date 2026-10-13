# Reglas de calidad de datos

## Objetivo

Definir los controles que deben superar las entradas de Bronze
y cómo conservar las evidencias de los datos que presentan problemas.

## Alcance de M6

M6 implementará reglas reutilizables, clasificación de resultados,
informes y salidas de cuarentena.

Las primeras pruebas se ejecutarán localmente contra entradas
conservadas y escenarios sintéticos conocidos.

La aplicación de eventos, la persistencia del estado vigente,
las marcas de agua y la idempotencia se implementarán en M8.
Las tablas Delta Silver se implementarán en M7.

Una validación local no equivale a publicación en Silver.

## Resultados

| Resultado | Significado |
|---|---|
| accepted | Registro que supera todos los controles requeridos y evaluables |
| rejected | Registro que incumple una regla |
| conflict | Identidad existente con contenido contradictorio |
| pending | Evento con una dependencia o secuencia anterior pendiente |
| duplicate | Repetición equivalente, sin necesidad de una nueva aplicación |
| blocked | Lote cuya integridad o estructura impide procesarlo |

Un control que requiere una referencia no disponible se registrará
como not_evaluated. No se declarará aceptación completa del registro.

## Catálogo inicial

| Código | Control | Acción ante incumplimiento |
|---|---|---|
| DQ001 | Manifiesto presente, versión e identidad válidas | Bloquear lote |
| DQ002 | Archivos declarados, tamaños y hashes cuando estén definidos | Bloquear lote |
| DQ003 | Conteos coincidentes con el manifiesto | Bloquear lote |
| DQ004 | Encabezados CSV y estructura de archivos compatibles | Bloquear lote si no se pueden interpretar |
| DQ005 | Campos obligatorios, tipos, formatos y longitudes del contrato | Rechazar registro |
| DQ006 | Claves positivas e identidad única | Rechazar o clasificar duplicado/conflicto |
| DQ007 | Referencias a entidades existentes | Rechazar datos inválidos o dejar eventos pendientes |
| DQ008 | Cantidades, precios, descuentos y moneda válidos | Rechazar registro |
| DQ009 | Fechas coherentes y corte temporal aplicable | Rechazar registro |
| DQ010 | Pedido con líneas válidas y completas | Impedir aceptación del pedido completo |
| DQ011 | Identidad y secuencia de eventos sin contradicciones | Clasificar duplicado, conflicto o pendiente |
| DQ012 | Imagen completa y atributos estables de eventos | Rechazar evento |
| DQ013 | Transiciones de estado permitidas | Rechazar evento |
| DQ014 | Campos, categorías, claves y paginación de DummyJSON | Bloquear extracción inconsistente o rechazar registro |
| DQ015 | Serie, fechas únicas y tasas de BCRPData | Rechazar observaciones inválidas |
| DQ016 | Referencias y unicidad del mapeo externo | Bloquear incorporación del mapeo |
| DQ017 | Reconciliación de registros y controles aplicables | Impedir aceptación del resultado |

Los detalles de tipos y valores se toman de los contratos existentes.
No se introducen límites nuevos por conveniencia del validador.

## Decisiones de procesamiento

La integridad del lote se comprueba antes de las reglas de negocio.
Un hash correcto no garantiza que los registros sean válidos.

Si el archivo no puede interpretarse, se bloquea el lote.
Si se puede identificar un registro inválido, se conserva su contenido
original y se registra el motivo.

Una línea inválida impide aceptar el pedido completo.
Las demás líneas y la cabecera se identifican como dependientes
de ese rechazo. No se publicará un pedido parcial.

Una línea que referencia un producto inexistente incumple el contrato.
Un evento recibido antes de su registro o secuencia anterior puede
quedar pendiente si esa dependencia puede llegar posteriormente.

Los eventos pending se distinguen de los pedidos con status=pending.

La detección de conflictos, duplicados y secuencias requiere conocer
el estado o historial aceptado. En M6 se probará con referencias
explícitas; su integración con el estado persistente corresponde a M8.

## Valores no disponibles

Los valores n.d. de BCRPData representan tasas no disponibles.
Se conservarán con una marca de disponibilidad, sin convertirlos
en cero ni rellenarlos automáticamente.

La ausencia de una observación para un día calendario no constituye
por sí misma un error.

Los campos opcionales ausentes de DummyJSON se normalizarán como nulos.
Los errores en campos obligatorios tendrán una clasificación explícita.

## Evidencia de cuarentena

Cada registro rechazado o en conflicto conservará:

- source_system y entity.
- ingestion_run_id y processing_run_id.
- batch_id o event_id, cuando estén disponibles.
- Ruta del archivo original.
- Número de registro o línea, cuando corresponda.
- Clave de negocio, si puede recuperarse.
- Contenido original como texto.
- Lista de códigos y motivos detectados.
- Fecha UTC de evaluación.

Un registro puede tener varios motivos, pero se contará una sola vez.
Los conflictos conservarán también una referencia a la versión
con la que se compararon.

Bronze no se modificará ni se eliminará durante estas validaciones.

## Informes y reconciliación

Los informes registrarán entradas, reglas evaluadas y resultados.
Las categorías de registros serán mutuamente excluyentes.

Para entradas interpretables:

    leídos = aceptados + rechazados + conflictos + pendientes + duplicados

Los pedidos excluidos por una línea inválida deben reflejarse
en los controles de cabeceras y líneas.

En un lote bloqueado no se inventarán conteos de registros procesados.
El fallo se registrará a nivel de lote.

Las salidas de cuarentena se generan en Parquet locales.
Se publicaron evidencias verificadas en quarantine y operations,
manteniendo los eventos pendientes separados de los rechazos.

## Pruebas previstas

- Datos iniciales y lotes funcionales válidos.
- S13 y S14: conflictos de identidad y secuencia.
- S15: transición de estado inválida.
- S16: referencia a producto inexistente.
- S17: descuento superior al importe bruto.
- S18: lote bloqueado por hash incorrecto.
- S19: pedido existente con contenido diferente.
- S20: modificación de un atributo estable.
- Eventos pendientes y duplicados con referencias conocidas.

S19 también conserva una fecha anterior al corte.
Su informe puede incluir varios motivos; no es una prueba
de una única regla incumplida.

## Estado

Catálogo definido en M6.1.
Validadores de transporte, pedidos CSV, eventos, API y mapeo implementados.
Informes y cuarentena local comprobados; 25 pruebas superadas.
Diez archivos de evidencia publicados y verificados en Azure.
Los eventos se evalúan contra referencias fijas de prueba.
La aplicación de eventos y el estado persistente corresponden a M8.
Cierre técnico documentado y revisión operativa realizada.
M6 completado para su alcance e integrado en main mediante el PR #11.
