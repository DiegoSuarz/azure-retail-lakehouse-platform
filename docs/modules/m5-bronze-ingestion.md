# M5 — Ingesta inicial y cargas a Bronze

## Resultado

Se incorporaron a Bronze la carga inicial de SQL Server,
cuatro lotes sintéticos incrementales y las respuestas de
DummyJSON y BCRPData.

Las cargas incluyen manifiestos y comprobaciones de integridad.
La configuración de ADF se exportó y quedó versionada.

## Servicios y herramientas utilizados

| Componente | Función en M5 |
|---|---|
| Azure Data Factory | Orquestar la extracción inicial de SQL Server |
| SHIR en Windows | Acceder a SQL Server local y ejecutar la copia |
| Azure Key Vault | Proporcionar la contraseña de retail_reader |
| ADLS Gen2 | Conservar las entradas originales en bronze |
| Python y pyodbc | Capturar referencias del origen |
| PyArrow | Leer y validar los Parquet reales |
| Python y Azure CLI | Publicar y verificar lotes sintéticos y API |

Recursos existentes reutilizados:

- ADF: adf-arlp-dev-diego01.
- SHIR: shir-arlp-dev-local.
- Key Vault: kv-arlp-dev-diego01.
- ADLS Gen2: starlpdevdiego01.
- Grupo de recursos: rg-arlp-dev.
- Base de origen: TechRetail_OLTP.

ADF utiliza identidad administrada para ADLS y Key Vault.
SQL Server utiliza retail_reader con permisos de lectura.
Las publicaciones CLI utilizan la sesión Microsoft Entra del usuario.

## Carga inicial de SQL Server

Pipeline: pl_ingest_sqlserver_initial.

Datasets parametrizados:

- ds_sqlserver_table: esquema y tabla.
- ds_adls_bronze_parquet: directorio de destino.

El pipeline recorre cinco tablas secuencialmente y copia sus datos
a Parquet con compresión Snappy.

Cada ejecución utiliza una ruta nueva basada en el RunId.
Copy tiene consistencia habilitada y no permite truncamiento.

Ejecución aceptada:

    89d277f4-ddee-49a2-9d9f-588efacf9788

Inicio UTC: 2026-10-11T01:32:05Z.
Fin UTC: 2026-10-11T01:34:25Z.
Duración del pipeline: 2 minutos y 20 segundos.

| Entidad | Registros | Archivos Parquet |
|---|---:|---:|
| categories | 6 | 1 |
| products | 60 | 1 |
| customers | 500 | 1 |
| orders | 2000 | 1 |
| order_items | 5862 | 1 |
| Total | 8428 | 5 |

Las cinco copias terminaron con Succeeded y consistencia Verified.

## Validación y aceptación

Las capturas de SQL Server antes y después conservaron el mismo contenido.
El operador confirmó una ventana sin escrituras.

Los Parquet se leyeron y compararon contra el origen:
columnas, tipos compatibles, conteos, claves, relaciones y todos los valores.

Los controles comerciales coinciden con M2:

- Importe neto confirmado: PEN 15781257.30.
- Unidades confirmadas: 11682.

Una descarga adicional confirmó igualdad byte por byte de los Parquet cloud.
El manifiesto se publicó sin sobrescritura y también se verificó.

La aceptación y publicación del manifiesto utilizaron scripts y CLI.
El pipeline ADF todavía no automatiza esas operaciones.

Las capturas no detectan cambios transitorios posteriormente revertidos.
La coherencia depende también de mantener la ventana sin escrituras.

## Lotes sintéticos incrementales

Se publicaron batch_001 a batch_004 mediante Python y Azure CLI.

Ingestion_run_id:

    1c55b98a-9a92-4637-b4fe-a3528ae92565

Los diez archivos se verificaron mediante descarga y SHA-256.
Cada manifiesto original se publicó después de comprobar los datos.

Las validaciones locales cubrieron los escenarios S01–S12.
Una prueba con un archivo alterado confirmó el rechazo previo
a cualquier llamada a Azure CLI.

Los eventos se conservaron en Bronze.
No se aplicaron a SQL Server ni a tablas Silver.

## API

| Fuente | Resultado | Archivos publicados y verificados |
|---|---|---:|
| DummyJSON | 38 productos únicos, cuatro categorías y nueve páginas | 21 |
| BCRPData | 195 observaciones, 184 tasas y 11 valores n.d. | 3 |

DummyJSON ingestion_run_id:

    172c6634-a566-4ae8-bfc7-04ae228dae77

BCRPData ingestion_run_id:

    e7d0e002-b3a6-4de3-8157-c2a3f818cd38

BCRPData: serie PD04638PD, intervalo 2026-01-01 a 2026-09-30.

Se conservaron respuestas originales, metadatos y manifiestos.
Los 24 archivos publicados se verificaron mediante SHA-256.

La extracción y publicación se ejecutaron con scripts.
ADF todavía no coordina estas fuentes.

## Mapeo externo

sources/reference/product_external_mapping.csv contiene
seis asociaciones educativas con claves existentes y únicas.

Las asociaciones no representan equivalencias comerciales.
Los atributos externos no reemplazarán los atributos del negocio.
Su incorporación a Silver permanece pendiente.

## Configuración versionada

La exportación ARM incluye los diez recursos internos de ADF de M4 y M5.
Se revisaron datasets, parámetros, rutas y configuración de Copy.

La conexión SQL conserva una referencia a Key Vault.
No se versionaron contraseñas ni claves de autenticación.

El despliegue desde las plantillas todavía no se ha probado.
La exportación no incluye los valores de secretos, permisos RBAC,
reglas de red ni instalación y registro del nodo SHIR.

## Costos

M5 generó consumo de ejecuciones ADF, operaciones de almacenamiento
y acceso al secreto de Key Vault.

Las publicaciones y comprobaciones generaron escrituras y lecturas,
además de transferencia cuando corresponda.
Los archivos conservados generan consumo de capacidad.

Cost Management se revisó el 2026-10-11 en Azure Portal.
La vista de recursos estaba filtrada a Azure for Students y rg-arlp-dev,
para octubre de 2026.

| Recurso | Costo mostrado USD |
|---|---:|
| Data Factory | 0.02 |
| Storage account | < 0.01 |
| Key Vault | < 0.01 |
| Total mostrado del grupo | 0.02 |

Los valores están redondeados y sujetos a actualización.
El total incluye los recursos compartidos de M3, M4 y M5.
No constituye el costo exclusivo de M5 ni el crédito restante.

La revisión es provisional: pueden faltar consumos recientes.
La reconciliación definitiva por módulo permanece pendiente.
No se desplegó Databricks para este módulo.

## Revisión operativa

Comprobaciones realizadas en Azure Portal el 2026-10-11:

- Presupuesto mensual de USD 20 presente en Azure for Students.
- Consumo evaluado mostrado: USD 0.02, equivalente a 0.11%.
- ADF sin triggers configurados.
- ADF sin sesiones activas de Data Flow Debug.

Los importes son provisionales y están sujetos a actualización.
Se conservan las entradas verificadas de Bronze y los servicios
compartidos para continuar los siguientes módulos.

## Aprendizajes y puntos clave

- Una copia exitosa debe complementarse con validación del contenido.
- Los conteos iguales no garantizan valores iguales.
- Bronze conserva la procedencia y permite reprocesar los datos.
- Los hashes comprueban integridad; no sustituyen reglas de negocio.
- Un manifiesto publicado al final identifica una entrega completa.
- Los datos originales y sus metadatos tienen estructuras diferentes.
- Un valor no disponible no equivale a una tasa de cero.
- La ingesta de eventos y su aplicación son etapas distintas.
- Las rutas por ejecución evitan mezclar entregas anteriores.

## Pendientes y continuidad

- Implementar calidad y cuarentena en M6.
- Transformar y normalizar las entradas en Silver.
- Aplicar eventos, deduplicación y orden en los módulos posteriores.
- Incorporar el mapeo externo a Silver.
- Definir el tratamiento analítico de fechas sin cotización.
- Ampliar la auditoría y centralizar la orquestación.
- Revisar el consumo real y las políticas de retención.

Se prevé generar nuevos lotes sintéticos y practicar su ingesta
orquestada por ADF, condicionada al crédito disponible.
Antes de ejecutar esa etapa se revisarán saldo y costo previsto.

## Conclusión

Bronze dispone de entradas verificadas de SQL Server,
archivos incrementales y API, con procedencia documentada.

Esta base permite iniciar las reglas de calidad y las transformaciones
sin repetir las extracciones ya aceptadas.

## Estado de cierre

M5 completado para el alcance de ingesta y preservación en Bronze.
Integrado en main mediante el pull request #9.
Commit de integración: 3e44f99.
Los pendientes y limitaciones descritos conservan su alcance.
