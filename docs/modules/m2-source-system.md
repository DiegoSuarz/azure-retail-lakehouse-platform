# M2 — Fuentes y contratos

## Resultado

Se implementó el origen SQL Server y se prepararon fuentes sintéticas
reproducibles para la carga inicial y los incrementales del Lakehouse.

## Entregables

- Modelo OLTP de cinco tablas y reglas de negocio.
- Scripts de creación de base, tablas y permisos.
- Usuarios retail_loader y retail_reader con permisos diferenciados.
- Generador inicial, manifiesto y validador.
- Cargador transaccional con reconciliación previa al COMMIT.
- Dependencia pyodbc registrada en requirements.txt.
- Contratos incrementales CSV y JSONL.
- Contratos de DummyJSON y BCRPData.
- Generadores y validadores de escenarios S01–S20.
- Documentación de ejecución y configuración local.

## Evidencias de validación

La carga inicial conserva:

| Control | Resultado |
|---|---:|
| Categorías | 6 |
| Productos | 60 |
| Clientes | 500 |
| Pedidos | 2000 |
| Líneas | 5862 |
| Pedidos pending | 209 |
| Pedidos confirmed | 1578 |
| Pedidos cancelled | 213 |
| Importe neto confirmado PEN | 15781257.30 |
| Unidades confirmadas | 11682 |

Los conteos e importes fueron reconciliados con el manifiesto
y mediante consultas independientes en SQL Server.

Se comprobó igualdad byte por byte entre generaciones repetidas
del conjunto inicial y del conjunto incremental completo.

Los permisos efectivos se verificaron sobre las cinco tablas:

- retail_loader: SELECT, INSERT y UPDATE; sin DELETE ni ALTER.
- retail_reader: SELECT; sin INSERT, UPDATE, DELETE ni ALTER.

Las conexiones reales de ambos logins también fueron verificadas.

## Escenarios incrementales

- S01–S07: pedidos nuevos y cambios funcionales.
- S08–S12: reprocesos, duplicados y orden de eventos.
- S13–S20: conflictos y anomalías deliberadas.

El primer lote tiene como resultado esperado 2002 pedidos,
5864 líneas y PEN 15803332.87 de ventas netas confirmadas.

Estas cifras corresponden a una simulación local.
SQL Server conserva la carga inicial de 2000 pedidos.

## Puntos clave y aprendizajes

1. El grano y las claves compartidas preceden a la implementación.
2. La carga inicial requiere reconciliación antes de confirmarse.
3. Las claves de negocio, los eventos y los lotes tienen identidades distintas.
4. El orden de llegada no determina el orden de aplicación.
5. Un hash correcto no garantiza datos comercialmente válidos.
6. Los datos reproducibles permiten preparar pruebas verificables.
7. Los permisos deben comprobarse de forma efectiva.
8. El catálogo externo no sustituye los datos autoritativos del negocio.

## Límites y pendientes

No se implementaron todavía:

- Ingesta persistente de API ni mapeo concreto del catálogo externo.
- Canalizaciones ADF ni almacenamiento cloud del proyecto.
- Aplicación incremental en Silver ni cuarentena.
- Marcas de agua operativas ni históricos SCD.

El procedimiento de respaldo y gestión del log de SQL Server
permanece pendiente según la documentación del origen.

Los validadores actuales utilizan las rutas predeterminadas de datos.
Las simulaciones locales no acreditan el funcionamiento cloud.

## Conclusión

El proyecto dispone de un origen inicial reconciliado, contratos
definidos y escenarios reproducibles para implementar la ingesta
y el procesamiento posterior.

El cierre de integración requiere incorporar estos cambios a main
mediante pull request.
