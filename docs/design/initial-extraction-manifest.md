# Aceptación de la extracción inicial

## Flujo actual sin manifiesto

La extracción inicial SQL Server no requiere generar ni publicar
manifest.json. Se conserva esta ruta documental para mantener enlaces.

1. Capturar el origen antes de la extracción.
2. Mantener una ventana sin escrituras durante extracción y validación.
3. Ejecutar pl_ingest_sqlserver_initial y revisar sus cinco copias.
4. Capturar el origen después de la extracción.
5. Descargar los Parquet y ejecutar validate_initial_parquet.py.
6. Comprobar que los archivos cloud coinciden con los validados.

## Revisión manual de ADF

El operador comprobará y conservará evidencia de:

- RunId, pipeline y cinco actividades Copy con estado Succeeded.
- Inicio y fin reales en UTC.
- Capturas del origen que delimiten la extracción.
- Ventana sin escrituras confirmada.
- Consistencia de las cinco copias con resultado Verified.
- Filas leídas, filas copiadas y archivos escritos coincidentes
  con el origen y los Parquet validados.

Estas comprobaciones ya no se automatizan mediante el constructor
del manifiesto. No deben sustituirse por métricas o fechas inventadas.

## Validación automática de los datos

tests/ingestion/validate_initial_parquet.py compara las referencias
del origen antes y después, columnas, tipos, claves, todos los valores
y relaciones. Genera un informe local solo si sus controles pasan.

Su informe no acredita por sí solo la revisión manual de ADF
ni la igualdad entre archivos cloud y descargados.

Las capturas no detectan cambios transitorios posteriormente revertidos.
La consistencia depende también de mantener la ventana sin escrituras.

## Finalización

La ejecución se acepta únicamente cuando pasan la validación de datos,
la revisión manual de ADF y la comparación cloud/local.
Las ejecuciones parciales o fallidas no se utilizan como entrada Silver.
La existencia de archivos o el estado Succeeded por sí solos no bastan.

## Evidencia histórica

La ejecución 89d277f4-ddee-49a2-9d9f-588efacf9788 utilizó el procedimiento
anterior con manifiesto publicado en Bronze. Esa evidencia se conserva;
las ejecuciones futuras no requieren generar otro manifiesto.
