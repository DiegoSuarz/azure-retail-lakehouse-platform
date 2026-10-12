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
Comparación de claves existentes, eventos y controles de API pendientes.

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

El informe reconcilia registros leídos, aceptados y rechazados.
Los eventos JSONL se contabilizan como no evaluados en este alcance.

Solo se generan Parquet para entidades con registros rechazados.
Conservan contenido original, clave, archivo, número de registro,
identificadores, fecha UTC y lista de motivos.

Una línea inválida impide aceptar su pedido completo.
Los pedidos independientes pueden seguir aceptados.

Los registros aceptados se contabilizan en el informe.
Esta implementación todavía no publica datos aceptados en Silver.

La cuarentena se guarda localmente; no se publica aún en Azure.

## Pruebas reutilizables

    python tests/quality/test_new_orders.py

Resultados comprobados:

- batch_001: dos pedidos y dos líneas aceptados, sin cuarentena.
- S16: un pedido y una línea rechazados por referencia inválida.
- S17: un pedido y una línea rechazados por descuento inválido.
- S18: lote bloqueado por hash, sin procesamiento de registros.
- Contenido, motivos, hashes y conteos de los Parquet verificados.

Las salidas de prueba se crean en carpetas temporales y se eliminan.
