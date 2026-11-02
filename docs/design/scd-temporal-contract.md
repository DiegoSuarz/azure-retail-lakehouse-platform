# Contrato temporal de dimensiones SCD

## Alcance

M10 procesará estados observados de productos y clientes.
El historial representa cuándo se observó cada estado para SCD,
no necesariamente cuándo comenzó su vigencia real en el negocio.

No se reconstruyen automáticamente estados intermedios omitidos
entre observaciones ni historia anterior a la base aceptada.

## Evidencia del origen

Silver conserva created_at y updated_at de productos,
clientes y categorías, además de metadatos de procesamiento.

El control actual verifica presencia y updated_at >= created_at.
No garantiza actualización automática por modificación,
zona horaria de origen ni vigencia efectiva de negocio.

La aplicación CDC de productos conserva el último estado
por producto dentro del lote. LSN y secuencia ordenan eventos,
pero no constituyen timestamps de vigencia dimensional.

## Referencias de entrada

Cada lote SCD debe identificar:

- batch_id estable.
- Dimensión de destino.
- observed_at explícito en UTC.
- Rutas y versiones Delta de las entradas Silver utilizadas.
- Estado completo de los atributos requeridos por entidad.
- Huella del contenido y metadatos que permita reconocer reintentos.

Productos requiere referencias de products y categories.
Clientes requiere referencia de customers.

Las versiones deben seleccionarse como un conjunto aceptado.
Fijar versiones individuales no garantiza por sí solo una
instantánea transaccional conjunta entre varias tablas.

observed_at corresponde a la preparación de la observación
sobre ese conjunto aceptado. No se genera de nuevo al reintentar
ni se deriva del timestamp de commit de una sola entrada Delta.

Un mismo batch_id con contenido o referencias diferentes se rechaza.
La implementación de huellas y control persistente se desarrollará
en los micromódulos de idempotencia y recuperación.

## Semántica de fechas

- observed_at: instante declarado para la observación del lote.
- effective_at: igual a observed_at en este contrato.
- processed_at: instante de procesamiento del intento.
- valid_from: effective_at que inicia una versión.
- valid_to: effective_at que termina una versión; NULL si sigue abierta.
- created_at y updated_at del origen: evidencia técnica,
  no disparadores temporales automáticos del SCD.

Se utilizarán timestamps UTC con precisión de microsegundos.
Las entradas temporales deben incluir Z o un desplazamiento explícito
y normalizarse a UTC. No se aceptan timestamps sin zona horaria.
La sesión Spark se configurará en UTC.

Los cambios se detectan comparando los atributos definidos en la matriz.
Una variación exclusiva de updated_at no crea una versión dimensional.

## Intervalos

La vigencia utiliza inicio incluido y fin excluido:

valid_from <= instante AND
(valid_to IS NULL OR instante < valid_to)

Al crear una versión tipo 2:
- La versión anterior termina en effective_at.
- La nueva comienza exactamente en effective_at.
- La nueva tiene valid_to = NULL e is_current = true.
- La anterior tiene is_current = false.

Una venta situada exactamente en el límite corresponde a la nueva versión.
No se resta un segundo ni un microsegundo al cerrar la anterior.

Los cambios tipo 1 no modifican períodos de vigencia.

## Orden y cambios atrasados

Se aplicarán lotes secuencialmente, sin escritores simultáneos.
Cada lote nuevo debe tener observed_at estrictamente posterior
al último lote aceptado para esa dimensión, incluso si este no creó versiones.

Un reintento idéntico se reconoce antes de evaluar su antigüedad.
Un lote diferente con fecha igual o anterior se bloquea para revisión.
M10 no insertará automáticamente cambios retroactivos en períodos cerrados.

Cada lote contendrá como máximo un estado por clave de negocio.
Estados duplicados o contradictorios se rechazan antes de escribir.
Para representar varios estados observados de la misma entidad,
se requieren lotes sucesivos con instantes distintos.

## Categorías de productos

El estado de producto se construye con la versión declarada de categorías.
Si cambia category_name para una categoría, el cambio observado afecta
a los productos asociados según la matriz tipo 2.

Su effective_at será el observed_at del lote de productos,
aunque products.updated_at no haya cambiado.
No se deduce la fecha del cambio conjunto usando solo el producto.

## Inicialización y hechos anteriores

La base heredada de M9 conservará sus claves dimensionales.
M10.4 definirá el inicio y el tratamiento de las ventas anteriores
sin atribuirles un historial de negocio no demostrado.

No se aplicarán nuevos lotes hasta aceptar esa inicialización.
La resolución temporal posterior utilizará order_date_utc,
no una fecha truncada al día, para compararla con vigencias timestamp.

El tratamiento de hechos anteriores al inicio, ventas tardías
y correcciones de relaciones se precisará antes de modificar fact_sales.

## Bajas

Una ausencia en el lote no prueba una eliminación.
is_active = false explícito produce el cambio tipo 2 acordado.
Las bajas físicas permanecen fuera de la aplicación automática
hasta disponer de un contrato específico.

## Escenarios de aceptación temporal

| Escenario | Resultado |
|---|---|
| Cambio observado y procesado después | Vigencia desde observed_at |
| Reintento idéntico | Mismo observed_at; ninguna versión duplicada |
| Lote distinto con igual observed_at | Bloqueado |
| Lote nuevo anterior al último aceptado | Bloqueado |
| Timestamp sin zona horaria | Rechazado |
| Solo cambia updated_at del origen | Ninguna versión nueva |
| Cambio de nombre de categoría | Versiones nuevas para productos afectados |
| Venta exactamente al inicio de versión nueva | Coincide con esa versión |
| Varios cambios entre dos observaciones | No se presume su reconstrucción |

## Estado

Contrato temporal definido para historial por observación.
Implementación y pruebas pendientes.
Este documento complementa scd-dimensions-plan.md.
