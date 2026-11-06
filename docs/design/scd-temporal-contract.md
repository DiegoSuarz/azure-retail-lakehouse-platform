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
- Ruta y versión Delta de partida de la dimensión de destino.

Productos requiere referencias de products y categories.
Clientes requiere referencia de customers.

Las versiones deben seleccionarse como un conjunto aceptado.
Fijar versiones individuales no garantiza por sí solo una
instantánea transaccional conjunta entre varias tablas.

observed_at corresponde a la preparación de la observación
sobre ese conjunto aceptado. No se genera de nuevo al reintentar
ni se deriva del timestamp de commit de una sola entrada Delta.

El flujo simplificado no mantiene huellas ni un registro persistente de lotes.
batch_id se utiliza como dato de auditoría; no garantiza por sí solo
el reconocimiento de reintentos ni detecta su reutilización con otros datos.

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

Se aplican lotes secuencialmente, con un único escritor por dimensión.
El operador debe mantener el orden de las observaciones.
No existe un control global persistente del último lote aceptado,
incluidos los lotes sin cambios.

Cada cierre tipo 2 exige observed_at posterior al valid_from
de la versión que se cierra. No se insertan cambios retroactivos
automáticamente en períodos cerrados.

Una entrada idéntica al estado actual conserva valores y auditoría.
El almacenamiento comprueba esa igualdad y evita otro commit Delta.
Esto no equivale a reconocer cualquier lote aplicado anteriormente.

Antes de repetir un intento fallido se revisa la versión real del destino.
Una entrada antigua puede diferir del estado actual y no debe
reprocesarse automáticamente.

Cada lote contiene como máximo un estado por clave de negocio.
Los duplicados se rechazan antes de escribir.
Para representar estados sucesivos se utilizan observaciones distintas.

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
| Entrada idéntica al estado actual | Sin cambios ni otro commit Delta |
| Observación igual al inicio de una versión por cerrar | Cierre rechazado |
| Lote antiguo presentado nuevamente | Revisión manual; sin registro global |
| Timestamp sin zona horaria | Rechazado |
| Solo cambia updated_at del origen | Ninguna versión nueva |
| Cambio de nombre de categoría | Versiones nuevas para productos afectados |
| Venta exactamente al inicio de versión nueva | Coincide con esa versión |
| Varios cambios entre dos observaciones | No se presume su reconstrucción |

## Estado

Contrato temporal adaptado al flujo simplificado.
Preparación SCD y escritura Delta probadas con datos sintéticos.
Integración del ejecutor y validación completa de operación pendientes.
Este documento complementa scd-dimensions-plan.md.
