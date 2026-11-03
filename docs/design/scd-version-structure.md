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

Antes de modificar el destino se conservará un plan de aplicación
con la asignación, batch_id, huella y versión Delta de partida.
La implementación de persistencia y recuperación se realizará
en el micromódulo correspondiente.

Un reintento reutiliza el plan aceptado.
No recalcula claves desde un destino parcialmente modificado.
Un destino con una versión inesperada bloquea la aplicación
hasta comprobar si el lote ya se aplicó o requiere recuperación.

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
La identidad del intento de recuperación se registra separadamente
en el control o informe de ejecución.

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

Un reintento ya aplicado no cambia la auditoría de las filas.
La preparación de una escritura debe fijar los valores que se conservarán
en el plan de aplicación para recuperaciones.

## Relación con hechos y referencias

Las claves de fact_sales existentes se conservan durante
la preparación de la estructura dimensional.

La resolución temporal para hechos nuevos y el tratamiento
de hechos anteriores se definirán antes de actualizar fact_sales.

product_catalog_mapping conserva claves de producto de M9.
No se interpretará su product_key como vínculo automático
con todas las nuevas versiones.
Su política de consulta o adaptación debe resolverse explícitamente.

## Persistencia y validación

build_gold_tables sigue siendo el constructor inicial de M9.
No se utiliza para reconstruir y reemplazar dimensiones SCD completas.

write_verified_gold_table comprueba una creación inicial
y recupera versionAsOf = 0.
Las actualizaciones SCD necesitarán un procedimiento propio
que identifique y valide la versión Delta resultante.

Las claves y nulabilidad son requisitos del contrato.
Se comprobarán explícitamente sobre los datos persistidos;
no se presupone que Delta imponga claves primarias o relaciones.

## Estado

Diseño de claves, vigencias y auditoría definido.
Asignación persistente, aplicación y pruebas pendientes.
