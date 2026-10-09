# Organización del almacenamiento

## Objetivo

Definir contenedores y rutas del lago para el entorno dev.

Los nombres de cuenta y grupo de recursos se confirmarán antes
del despliegue. Todos los identificadores de almacenamiento
utilizarán inglés y minúsculas.

## Contenedores

| Contenedor | Responsabilidad |
|---|---|
| bronze | Entradas originales y metadatos de extracción |
| silver | Tablas Delta validadas y estado vigente |
| gold | Dimensiones, hechos y métricas en Delta |
| quarantine | Registros rechazados y sus motivos |
| serving | Exportaciones Parquet para consumo |
| operations | Auditoría y controles de procesamiento |

Los contenedores estarán dentro de una cuenta de almacenamiento
del entorno dev.

Esta separación facilita organizar accesos y responsabilidades,
pero no otorga permisos automáticamente.

## Convenciones

- Directorios y entidades en snake_case.
- Fechas de ingesta en UTC con formato YYYY-MM-DD.
- ingestion_run_id identifica una ejecución de ingesta.
- batch_id identifica un lote de la fuente.
- publication_id identifica una publicación analítica.
- Los identificadores utilizados en rutas no contendrán barras.
- Las fechas de negocio permanecerán en los datos.

Una ejecución podrá procesar varios lotes.
Un lote podrá recibirse en distintas ejecuciones de reproceso.

## Bronze

### Carga inicial de SQL Server

    sqlserver/techretail_oltp/initial/run_id=<ingestion_run_id>/<entity>/

Entidades:

- categories.
- products.
- customers.
- orders.
- order_items.

Cada directorio de entidad contendrá los archivos Parquet extraídos.

El directorio de la ejecución contendrá también un manifiesto
de extracción con corte, entidades, archivos y controles.

El manifiesto cloud de extracción será distinto del manifiesto
de generación local de M2.

### Lotes sintéticos incrementales

    synthetic/incremental/batch_id=<batch_id>/run_id=<ingestion_run_id>/

Se conservarán orders.csv, order_items.csv, changes.jsonl
y manifest.json cuando estén presentes en el lote.

El manifiesto original mantendrá los nombres y hashes
de los archivos de origen.

Los casos inválidos S13–S20 solo se cargarán en ejecuciones de prueba
explícitas; no se mezclarán con la ingesta funcional ordinaria.

### DummyJSON

    dummyjson/products/ingestion_date=<YYYY-MM-DD>/run_id=<ingestion_run_id>/category=<category>/

Cada categoría contendrá respuestas JSON por página:

    page_000001.json
    page_000002.json

Los metadatos registrarán URL, parámetros, estado HTTP,
fecha de extracción y hash del contenido conservado.

La extracción se marcará completa después de validar todas
las categorías y páginas previstas.

### BCRPData

    bcrpdata/exchange_rates/series_code=pd04638pd/ingestion_date=<YYYY-MM-DD>/run_id=<ingestion_run_id>/

Se conservarán las respuestas JSON y el intervalo solicitado.

El código de serie dentro de los datos conservará la forma
PD04638PD utilizada por la fuente.

### Preservación

Los archivos recibidos se conservarán sin cambios de negocio.
Los reprocesos tendrán otro ingestion_run_id.

No se sobrescribirán archivos de una ejecución anterior.
La preservación será una regla del procesamiento, sin habilitar
por ahora una política de inmutabilidad de Azure.

## Silver

Rutas previstas de tablas:

    techretail/categories/
    techretail/products/
    techretail/customers/
    techretail/orders/
    techretail/order_items/
    external/dummyjson_products/
    reference/product_external_mapping/
    reference/exchange_rates/

Cada ruta representará una tabla Delta completa,
incluidos sus archivos de datos y _delta_log.

Las tablas vigentes tendrán rutas estables.
No se creará una tabla independiente por cada ejecución.

El mapeo externo tendrá como origen el archivo versionado
definido en el contrato de API.

## Gold

Rutas candidatas:

    sales/dim_date/
    sales/dim_customer/
    sales/dim_product/
    sales/fact_sales/

El grano, las claves y los atributos definitivos se establecerán
antes de implementar el modelo dimensional.

Las tablas serán Delta y tendrán rutas estables.
Las métricas derivadas adicionales se definirán en el módulo Gold.

## Quarantine

    source=<source_system>/entity=<entity>/run_id=<processing_run_id>/

Los registros rechazados incluirán:

- Identidad o referencia del registro original.
- Referencia a la entrada Bronze.
- Código y descripción del rechazo.
- Identificador y fecha de procesamiento.

El formato previsto será Parquet.

Los eventos pendientes por dependencias o huecos de secuencia
se distinguirán de los registros rechazados.

## Serving

    sales/publication_id=<publication_id>/<dataset>/

Cada publicación contendrá exportaciones Parquet validadas.
Sus archivos no se mezclarán con los de otra publicación.

Un manifiesto de publicación registrará datasets, conteos,
controles y versiones de las tablas Gold utilizadas.

Synapse consultará únicamente la publicación seleccionada.
La selección se implementará en el módulo de consumo,
evitando consultar todas las publicaciones mediante un comodín.

La publicación se expondrá después de completar todos
sus datasets y validaciones.

## Operations

Directorios previstos:

    ingestion/
    processing/
    quality/
    pending_events/
    publication/

Contendrán auditoría, estados y resultados de controles.

Los formatos y mecanismos de actualización se definirán
antes de implementar cada componente.

Las marcas de agua solo avanzarán después de confirmar
el procesamiento correspondiente.

No se almacenarán contraseñas ni tokens en estos directorios.

## Particionamiento

Los segmentos de Bronze y Serving organizan archivos por procedencia
o publicación; no constituyen automáticamente particiones Delta.

No se particionarán inicialmente las pequeñas tablas Silver y Gold.
Se revisará esta decisión si el volumen y los patrones de consulta
justifican particiones.

## Seguridad y retención

- Sin acceso anónimo a contenedores.
- Autenticación mediante identidades donde la integración lo permita.
- Permisos de datos según responsabilidad de cada componente.
- ACL por directorio cuando se requiera acceso más granular.
- Sin reglas automáticas de eliminación durante la preparación inicial.

Las políticas de retención se definirán considerando reprocesos,
auditoría, time travel y presupuesto.

No se eliminarán archivos internos de tablas Delta mediante
reglas genéricas de ciclo de vida. Su mantenimiento se realizará
con mecanismos compatibles con Delta.

## Estado

Diseño definido en M3.1.
La cuenta, los contenedores y los directorios todavía no están creados.
