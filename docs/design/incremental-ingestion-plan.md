# Ingesta de lotes sintéticos a Bronze

## Objetivo

Conservar los cuatro lotes funcionales de M2 en Bronze,
sin modificar su contenido ni aplicar sus eventos.

## Origen y destino

Origen local:

    data/incremental/functional/<batch_id>/

Destino dentro del contenedor bronze:

    synthetic/incremental/batch_id=<batch_id>/run_id=<ingestion_run_id>/

Cuenta: starlpdevdiego01.

Una ejecución de ingesta utilizará un UUID compartido por los cuatro
lotes. Cada nueva ejecución tendrá un identificador diferente.

## Implementación

Un script Python utilizará Azure CLI con autenticación Microsoft Entra.
No utilizará claves de almacenamiento ni contraseñas en el código.

Lotes incluidos: batch_001, batch_002, batch_003 y batch_004.

## Procedimiento por lote

1. Validar estructura, nombres admitidos y entrega conjunta de CSV.
2. Calcular conteos y hashes de los datos locales.
3. Preparar una copia temporal y contrastar su contenido.
4. Subir los archivos de datos sin sobrescribir objetos existentes.
5. Descargar los archivos publicados y comprobar sus hashes.
6. Registrar los resultados en el informe de ejecución.

No se genera ni publica un manifiesto.
El procesamiento no debe iniciarse mientras se prepara la entrega.
La publicación de varios archivos no es una transacción atómica.

## Auditoría y fallos

Se guardará un informe local con el identificador de ingesta,
fechas UTC, rutas y resultados de verificación por lote.

Un fallo detendrá la ejecución.
Los lotes ya publicados conservarán su estado.
La aceptación requiere revisar el informe y todos los archivos esperados;
la existencia de una carpeta no acredita finalización.

No se eliminarán automáticamente archivos parciales.
No se reintentará una ejecución con otro identificador sin revisar
primero los resultados de la ejecución anterior.

## Alcance

No se modificarán SQL Server ni las tablas Silver.
Los casos inválidos S13–S20 permanecerán fuera de esta ingesta.
Los archivos de expectativas son controles de prueba, no datos del lote.

La deduplicación y el orden de eventos se implementarán posteriormente.

## Costos

La publicación y verificación generarán operaciones de almacenamiento,
transferencia cuando corresponda y capacidad por los archivos conservados.

## Estado

Lotes funcionales validados localmente.
Cargador implementado y cuatro lotes funcionales publicados en Bronze.
La publicación histórica incluyó diez archivos, contando los manifiestos,
verificados mediante descarga y SHA-256.
El flujo actual prepara seis archivos de datos y no publica manifiestos.
Su preparación local se comprobó sin realizar una publicación nueva.
Ejecución: 1c55b98a-9a92-4637-b4fe-a3528ae92565.
La aplicación de eventos en Silver permanece pendiente.
