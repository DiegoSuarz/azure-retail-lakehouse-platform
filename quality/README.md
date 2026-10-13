# Validación de calidad

## Integridad de lotes sintéticos

validate_batch_transport.py implementa los controles de transporte
DQ001–DQ004 definidos en docs/design/data-quality-rules.md.

Comprueba:

- Manifiesto, versión, identidad y fecha de publicación.
- Inventario de archivos y entrega conjunta de pedidos y líneas.
- Hashes SHA-256 y tamaños cuando estén declarados.
- Conteos, encabezados CSV y estructura JSONL.

No exige que el nombre de la carpeta coincida con batch_id.
Puede comprobar una identidad explícita mediante --expected-batch-id.

## Ejecución

Desde la raíz del repositorio:

    python quality/validate_batch_transport.py \
        --batch-dir data/incremental/functional/batch_001 \
        --report data/validation/quality_batch_001_transport.json

El informe debe estar fuera del lote y no se sobrescribe.

## Resultados

- transport_validated: integridad y estructura verificadas.
- blocked: el lote no debe avanzar a validación de negocio.

Código de salida: cero para transporte validado y uno para lote bloqueado.

El informe incluye processing_run_id, fecha UTC, entrada y errores.
records_processed permanece nulo porque no se procesan registros
de negocio en esta etapa.

El script no modifica los archivos de entrada ni publica en Azure.

## Pruebas realizadas

- batch_001 a batch_004: transport_validated.
- S16: transport_validated, con referencia inválida pendiente de DQ007.
- S18: blocked por DQ002, sin interpretar los registros.

Se comprobaron clasificaciones, códigos de salida y alcance del informe.
Los informes de prueba se generaron en una carpeta temporal y se eliminaron.

## Estado

Validación de transporte implementada y comprobada con esos casos.
Reglas de pedidos CSV nuevos y cuarentena Parquet local implementadas.
Comparación de pedidos existentes implementada y comprobada.
Eventos y controles de API pendientes.

## Calidad de pedidos nuevos

Componentes:

- reference_data.py: verifica hashes y conteos de la referencia inicial.
- record_rules.py: comprueba tipos, valores, fechas y referencias.
- new_order_rules.py: evalúa pedidos y propaga rechazos a sus líneas.
- check_new_orders.py: genera informe y cuarentena Parquet local.

Ejemplo con una anomalía deliberada:

    python quality/check_new_orders.py \
        --batch-dir data/incremental/invalid/S16 \
        --output-dir data/validation/quality_s16

La salida debe ser nueva y estar fuera del lote.
Para una entrada procedente de una ingesta real, proporcionar
--ingestion-run-id con su identificador de procedencia.
En pruebas locales sin ingesta, ese campo permanece nulo.

## Informe y cuarentena

completed_for_scope indica que terminó la evaluación de pedidos nuevos,
aunque existan rechazos. No declara aceptación completa del lote.

El informe reconcilia registros leídos, aceptados, rechazados,
en conflicto y duplicados.
Los eventos JSONL se contabilizan como no evaluados en este alcance.

Solo se generan Parquet para entidades con registros rechazados
o en conflicto.
Conservan contenido original, clave, archivo, número de registro,
identificadores, fecha UTC y lista de motivos.

Una línea inválida impide aceptar su pedido completo.
Los pedidos independientes pueden seguir aceptados.

Los registros aceptados se contabilizan en el informe.
Esta implementación todavía no publica datos aceptados en Silver.

La cuarentena se guarda localmente; no se publica aún en Azure.

## Pruebas reutilizables

    python -m unittest discover -s tests/quality -p 'test_*.py' -v

Resultados comprobados:

- batch_001: dos pedidos y dos líneas aceptados, sin cuarentena.
- S16: un pedido y una línea rechazados por referencia inválida.
- S17: un pedido y una línea rechazados por descuento inválido.
- S18: lote bloqueado por hash, sin procesamiento de registros.
- Contenido, motivos, hashes y conteos de los Parquet verificados.

Las salidas de prueba se crean en carpetas temporales y se eliminan.

## Pedidos existentes y reprocesos

La comparación utiliza la referencia inicial y evalúa la cabecera
y el conjunto completo de líneas.

- Contenido equivalente y sin otros errores: duplicate.
- Contenido diferente o entrega incompatible: conflict.
- Las líneas de un pedido en conflicto quedan rechazadas por dependencia.

Una repetición completa equivalente no se interpreta como pedido nuevo.
Por ello, su fecha anterior al corte no impide reconocer el duplicado.
En un conflicto como S19 se conservan DQ006 y DQ009.

La cuarentena incluye reference_content_json cuando existe una
comparación con la versión original.

Pruebas adicionales realizadas:

- S19: una cabecera en conflicto y cuatro líneas rechazadas.
- Repetición idéntica: cinco registros duplicados y sin cuarentena.
- Línea modificada o ausente: conflicto, sin registros aceptados.
- Archivos de referencia sin modificaciones.

Estas comprobaciones son locales contra la referencia inicial.
No implementan todavía idempotencia persistente entre ejecuciones
ni aplican actualizaciones al estado vigente.

## Calidad de eventos

Componentes:

- event_reference.py: construye referencias de prueba del estado inicial
  y del estado esperado después de batch_001.
- event_rules.py: evalúa identidad, secuencia, imagen completa,
  atributos estables y transiciones de estado.
- check_events.py: genera informes y archivos Parquet de evidencia.

Las referencias proceden de los datos y expectativas de M2.
Son referencias de prueba; no representan un estado Silver persistente.

El evaluador compara cada evento contra una referencia fija.
No aplica cambios ni avanza secuencias durante la evaluación.

Resultados posibles: accepted, rejected, conflict, pending y duplicate.
El informe reconcilia las cinco categorías sin contar un evento dos veces.

Los rechazos y conflictos se conservan en events_quarantine.parquet.
Los pendientes se conservan por separado en events_pending.parquet.
Solo se generan estos archivos cuando existen registros correspondientes.

Las salidas conservan el contenido original, los motivos,
la procedencia y la referencia utilizada cuando corresponde.

## Pruebas de eventos realizadas

- S13: mismo event_id con contenido diferente, clasificado como conflicto.
- S14: misma clave y secuencia con otro event_id, clasificado como conflicto.
- S15: transición de cancelled a confirmed, rechazada.
- S20: modificación de un atributo estable, rechazada.
- batch_002: evento duplicado y evento pendiente por hueco de secuencia.
- Contradicciones dentro de un lote: eventos implicados en conflicto.
- Repetición idéntica dentro de un lote: una aceptación y un duplicado.

La suite conjunta de pedidos y eventos superó ocho pruebas.
También se verificaron los tamaños, hashes y contenidos de las evidencias.

La aplicación efectiva de eventos y el estado persistente corresponden
a M8. Los controles de API, mapeo externo y publicación de evidencias
en Azure siguen pendientes en M6.

## Pruebas adicionales de transporte

test_batch_transport.py comprueba cuatro defectos sobre copias temporales:

- DQ001: versión de manifiesto incompatible.
- DQ002: archivo declarado ausente.
- DQ003: conteo diferente del manifiesto.
- DQ004: encabezado CSV incompatible, conservando un hash correcto.

Todos los casos generan un informe blocked, sin procesar registros
de negocio ni modificar las entradas.

La suite conjunta superó nueve pruebas.

## Reglas de registros de API

api_record_rules.py evalúa productos de DummyJSON y valores de BCRPData.

DQ014 comprueba identificadores, títulos, categorías, campos numéricos,
rating, stock y tipos de los textos opcionales.

Los opcionales ausentes se representan como nulos.
La moneda externa permanece nula.
El contrato actual no establece un mínimo para external_price.

DQ015 exige tasas textuales y valores numéricos positivos.
Los valores vacíos, no numéricos o no finitos se conservan como
no disponibles, sin convertirlos en cero.

Los importes conservan precisión mediante Decimal.
Las funciones no modifican los registros de entrada.

test_api_records.py comprueba casos válidos e inválidos,
precisión decimal y conservación de valores originales.
La suite conjunta superó trece pruebas.

Estas funciones evalúan registros individuales.
La integridad de extracciones, paginación, fechas, duplicados,
metadatos y mapeo externo todavía requieren controles adicionales.

## Calidad de extracciones conservadas

Componentes:

- api_extraction_input.py: verifica identidad, inventario, hashes,
  tamaños, JSON y metadatos de procedencia.
- dummyjson_rules.py: evalúa categorías, paginación, identificadores,
  productos y controles del manifiesto.
- bcrpdata_rules.py: evalúa serie solicitada, intervalo, fechas,
  tasas y controles del manifiesto.

Resultados de las extracciones conservadas de M5:

- DummyJSON: 38 productos aceptados.
- BCRPData: 195 observaciones aceptadas.
- BCRPData: 184 tasas disponibles y 11 no disponibles.

Los conteos describen esas extracciones; no son límites del contrato.

Las pruebas comprueban paginación incorrecta, productos inválidos,
fechas inválidas, tasas negativas y fechas duplicadas.
Los defectos se introducen en copias en memoria.

Cuando existen observaciones rechazadas de BCRPData, no se declara
superada la reconciliación completa de controles del manifiesto.

Los evaluadores no modifican los archivos conservados.
El informe persistente, la cuarentena de API y la evaluación
del mapeo externo siguen pendientes.

## Informes y cuarentena de API

check_api_extraction.py evalúa una extracción conservada y genera
report.json en una carpeta nueva, fuera de la entrada.

El informe registra procedencia, conteos, reconciliación,
disponibilidad de tasas, errores y archivos de cuarentena.

completed_for_scope indica evaluación terminada, aunque existan rechazos.
blocked indica que la extracción no superó los controles previos;
en ese caso no se declaran registros procesados.

Solo se genera cuarentena Parquet cuando existen registros rechazados.
Cada fila conserva la respuesta original completa, su SHA-256,
la posición del registro mediante JSON Pointer, clave, motivos,
identificadores y fecha UTC de evaluación.

Las extracciones reales de M5 generaron informes sin rechazos:
38 productos de DummyJSON y 195 observaciones de BCRPData,
con 184 tasas disponibles y 11 no disponibles.

test_api_reports.py comprueba:

- Producto inválido: 37 aceptados y uno rechazado, con evidencia íntegra.
- Hash incorrecto: extracción bloqueada, sin cuarentena de registros.

La suite conjunta superó veinte pruebas.
Los informes permanecen locales; su publicación en Azure está pendiente.

## Informes y cuarentena de API

check_api_extraction.py evalúa una extracción conservada y genera
report.json en una carpeta nueva, fuera de la entrada.

El informe registra procedencia, conteos, reconciliación,
disponibilidad de tasas, errores y archivos de cuarentena.

completed_for_scope indica evaluación terminada, aunque existan rechazos.
blocked indica que la extracción no superó los controles previos;
en ese caso no se declaran registros procesados.

Solo se genera cuarentena Parquet cuando existen registros rechazados.
Cada fila conserva la respuesta original completa, su SHA-256,
la posición del registro mediante JSON Pointer, clave, motivos,
identificadores y fecha UTC de evaluación.

Las extracciones reales de M5 generaron informes sin rechazos:
38 productos de DummyJSON y 195 observaciones de BCRPData,
con 184 tasas disponibles y 11 no disponibles.

test_api_reports.py comprueba:

- Producto inválido: 37 aceptados y uno rechazado, con evidencia íntegra.
- Hash incorrecto: extracción bloqueada, sin cuarentena de registros.

La suite conjunta superó veinte pruebas.
Los informes permanecen locales; su publicación en Azure está pendiente.

## Calidad del mapeo externo

check_product_mapping.py implementa DQ016.

Comprueba encabezados, identificadores positivos, referencias existentes,
unicidad por producto local y externo, tipo de asociación y nota educativa.

El catálogo externo debe superar la evaluación de DummyJSON.
La referencia local utiliza el conjunto inicial con hashes verificados.

El archivo real contiene seis asociaciones válidas.
No se exige cobertura de todos los productos locales.

Cualquier asociación inválida bloquea la incorporación del archivo completo.
Las asociaciones repetidas identifican todas las filas implicadas.
El informe conserva el hash del mapeo, la referencia de extracción,
los conteos y los motivos de rechazo.

test_product_mapping.py superó dos pruebas, incluidos cinco casos:
referencia local inexistente, referencia externa inexistente,
producto local repetido, producto externo repetido y nota vacía.

Las pruebas utilizan copias temporales y conservan el archivo original.
La incorporación del mapeo a Silver sigue pendiente.
