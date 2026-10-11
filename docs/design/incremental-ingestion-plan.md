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

1. Validar identidad, versión y archivos declarados en el manifiesto.
2. Comprobar conteos y hashes SHA-256 de los archivos locales.
3. Subir los archivos de datos sin sobrescribir objetos existentes.
4. Descargar los archivos publicados y comprobar sus hashes.
5. Publicar el manifiesto original después de verificar los datos.
6. Descargar el manifiesto y compararlo byte por byte con el original.

El manifiesto original se conservará sin cambios.
Su created_at representa la publicación sintética del lote,
no el momento real de ingesta en Azure.

## Auditoría y fallos

Se guardará un informe local con el identificador de ingesta,
fechas UTC, rutas y resultados de verificación por lote.

Un fallo detendrá la ejecución.
Los lotes ya publicados conservarán su estado.
Un lote sin manifiesto se considerará incompleto.

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
Los diez archivos se verificaron mediante descarga y hash SHA-256.
Ejecución: 1c55b98a-9a92-4637-b4fe-a3528ae92565.
La aplicación de eventos en Silver permanece pendiente.
