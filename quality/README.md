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
Reglas de negocio, clasificación de registros y cuarentena pendientes.
