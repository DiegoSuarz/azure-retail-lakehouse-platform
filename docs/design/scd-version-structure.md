# Claves y estructura de versiones SCD

## Alcance

Estructura prevista para dim_product y dim_customer.
Complementa scd-dimensions-plan.md y scd-temporal-contract.md.
No modifica las tablas existentes.

## Identificadores

product_id y customer_id son claves de negocio.
product_key y customer_key identifican versiones dimensionales.

Las claves dimensionales serán long, positivas, únicas y no nulas.
Se conservarán todas las claves heredadas de M9.
Una clave no cambia, no se reutiliza y no identifica otra entidad.

Una entidad puede tener varias versiones y exactamente una actual.
is_active indica estado comercial; is_current indica versión actual.

## Asignación de nuevas claves

Se utilizará un único escritor por dimensión.
El máximo se calculará sobre todas las versiones, incluidas las cerradas.
La secuencia es independiente para productos y clientes.

Las entidades que necesitan una nueva fila se ordenarán
por su clave de negocio ascendente.
Se asignará max_key + posición, comenzando en posición 1.
En un destino vacío, max_key será 0.
Se comprobará que la asignación no exceda el rango de long.

Solo las entidades nuevas y los cambios tipo 2 reciben claves nuevas.
Los cambios tipo 1 y las filas sin cambios conservan sus claves.

No se vuelve a ejecutar row_number sobre toda la dimensión
para sustituir las claves existentes.

La preparación calcula las claves sobre una versión Delta explícita
y devuelve el plan de claves junto con el resultado dimensional completo.

El flujo simplificado no conserva automáticamente un plan persistente
para recuperar intentos interrumpidos.

Antes de escribir se comprueba que el destino siga en la versión de partida.
Si cambió, se bloquea la aplicación para revisar su estado.

Una entrada idéntica al estado actual no recibe nuevas claves.
Después de un fallo se revisa el destino antes de preparar otro intento.

Esta estrategia no admite escritores concurrentes.

## Columnas temporales

| Columna | Tipo Spark | Nulos | Regla |
|---|---|---|---|
| valid_from | timestamp | No | Inicio incluido |
| valid_to | timestamp | Sí | Fin excluido; NULL si está abierta |
| is_current | boolean | No | true si y solo si valid_to es NULL |

Los timestamps se interpretan en UTC.
Una versión cerrada requiere valid_from < valid_to.
Los intervalos de una entidad no pueden solaparse.
Las versiones sucesivas de una entidad serán contiguas.

La vigencia inicial heredada de M9 se definirá en M10.4.
No se deduce automáticamente de created_at ni de gold_processed_at.

## Procedencia de creación

gold_processing_run_id y gold_processed_at conservan la procedencia
de construcción de la fila y no se sobrescriben al cerrarla
ni al corregir atributos tipo 1.

Para una nueva versión SCD se registrará la ejecución que la construye.
Para las filas heredadas se conservarán los valores originales de M9.

Una vez aplicada la fila, esos campos permanecen inmutables.
El flujo simplificado no mantiene un registro automático
de intentos de recuperación.

## Auditoría SCD

| Columna | Tipo Spark | Nulos | Significado |
|---|---|---|---|
| scd_created_batch_id | string | No | Lote que incorpora la versión a SCD |
| scd_last_modified_batch_id | string | No | Último lote que modifica la fila |
| scd_last_modified_run_id | string | No | Ejecución que realiza esa modificación |
| scd_last_modified_at | timestamp | No | Instante UTC de modificación |

Los identificadores string deben ser no vacíos.
El lote de inicialización asignará los campos SCD a las filas de M9
sin alterar su procedencia Gold original.

Al insertar una versión, los campos SCD apuntan al lote de inserción.
Al cerrar una versión, se actualiza su auditoría de modificación.
Al aplicar tipo 1, se actualiza la auditoría de las filas corregidas.
Las filas sin cambios no reciben nuevas marcas de modificación.

Una entrada idéntica al estado actual no modifica la auditoría.
Un lote antiguo no se reconoce automáticamente como ya aplicado.
Los intentos interrumpidos requieren revisión manual.

## Relación con hechos y referencias

Las claves de fact_sales existentes se conservan durante
la preparación de la estructura dimensional.

La resolución temporal para hechos nuevos y la conservación
de hechos anteriores están definidas en scd-sales-key-resolution.md.
Sus funciones fueron probadas sin modificar fact_sales.

product_catalog_mapping conserva claves de producto de M9.
No se interpretará su product_key como vínculo automático
con todas las nuevas versiones.
Su política de consulta o adaptación debe resolverse explícitamente.

## Persistencia y validación

build_gold_tables sigue siendo el constructor inicial de M9.
No se utiliza para reconstruir y reemplazar dimensiones SCD completas.

write_verified_gold_table comprueba una creación inicial
y recupera versionAsOf = 0.
scd_storage.py aplica el resultado preparado mediante un MERGE por dimensión
y compara los datos recuperados con el resultado esperado.
Si los datos ya coinciden, conserva la versión Delta sin escribir.

Una validación posterior puede fallar después de que Delta haya escrito.
Productos y clientes no forman una transacción conjunta.
Estos casos requieren revisión manual antes de repetir la ejecución.

Las claves y nulabilidad son requisitos del contrato.
Se comprobarán explícitamente sobre los datos persistidos;
no se presupone que Delta imponga claves primarias o relaciones.

## Estado

Claves, preparación SCD y controles temporales implementados
en scd_transform.py.
Lectura y aplicación Delta implementadas en scd_storage.py.
Ejecutor integrado en run_scd_local.py.
Dos lotes consecutivos por dimensión y repeticiones sin cambios
verificados localmente; evidencia en scd-local-execution.md.
La ejecución en Azure permanece pendiente.
