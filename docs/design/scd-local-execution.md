# Ejecución local del flujo SCD simplificado

## Objetivo

Comprobar cambios SCD tipo 1 y tipo 2 en productos y clientes,
utilizando datos sintéticos separados de la base aceptada de M9.

Pruebas realizadas el 6 de noviembre de 2026, hora de Lima.

## Organización

- scd_transform.py: reglas, detección, preparación y validación temporal.
- scd_storage.py: lectura versionada y aplicación mediante MERGE Delta.
- run_scd_local.py: ejecución por argumentos para una dimensión.

La inicialización y la resolución de claves de ventas permanecen
en sus módulos específicos.

## Datos de prueba

Las entradas y destinos se encuentran bajo:

data/validation/scd_simple_demo/

Cada dimensión comenzó con dos entidades en versión Delta 0.
Las entradas contienen estados completos de los atributos requeridos.
En productos, la categoría ya está incorporada en la entrada.

Estos datos son sintéticos; no modifican los destinos aceptados de M9
ni las copias de inicialización SCD de 61 productos y 500 clientes.

## Resultados por lote

| Dimensión | Lote | Tipo 1 | Tipo 2 | Combinado | Nuevos | Sin cambios | Versión resultante | Filas |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Clientes | demo-batch-1 | 0 | 0 | 1 | 1 | 1 | 1 | 4 |
| Clientes | demo-batch-2 | 1 | 2 | 0 | 1 | 0 | 2 | 7 |
| Productos | demo-products-1 | 0 | 0 | 1 | 1 | 1 | 1 | 4 |
| Productos | demo-products-2 | 1 | 2 | 0 | 1 | 0 | 2 | 7 |

Combinado significa cambio simultáneo de atributos tipo 1 y tipo 2.

Las observaciones fueron:

- Primer lote: 2026-11-05T00:00:00+00:00.
- Segundo lote: 2026-11-06T00:00:00+00:00.

Los resultados persistidos se verificaron contra las dimensiones
preparadas antes de la escritura.

## Comportamientos comprobados

- Correcciones descriptivas tipo 1 sin crear versiones adicionales.
- Propagación de correcciones a las versiones históricas afectadas.
- Cambios tipo 2 con cierre anterior e inserción de una nueva versión.
- Altas con claves nuevas calculadas desde el máximo histórico.
- Bajas lógicas mediante is_active, conservando el historial.
- Conservación de claves y procedencia de creación de filas existentes.
- Validación temporal de la entrada y del resultado preparado.

En clientes se consultó el historial persistido de la versión 2:
cuatro entidades distribuidas en siete versiones dimensionales.

## Repetición sin cambios

Se repitió el primer lote de clientes contra su resultado en versión 1:

- Tres entidades clasificadas como unchanged.
- Cuatro filas conservadas.
- changed: false.
- Versión Delta conservada en 1.

Se repitió el segundo lote de productos contra su resultado en versión 2:

- Cuatro entidades clasificadas como unchanged.
- Siete filas conservadas.
- changed: false.
- Versión Delta conservada en 2.
- Ejecución: bf71ead5-1b75-4ce6-a938-6f0b515f6ff0.

La repetición de una entrada idéntica al estado actual no modifica
los valores ni la auditoría de las filas y no crea un commit Delta.

Esto no constituye reconocimiento persistente de lotes por batch_id.

## Controles temporales

Se comprobaron escenarios sintéticos para ambas dimensiones:

- Historial contiguo válido.
- Exactamente una versión actual por entidad.
- Rechazo de intervalos de duración nula o invertidos.
- Rechazo de huecos y solapamientos.
- Rechazo de incoherencias entre is_current y valid_to.
- Rechazo de valid_from nulo.

## Operación y límites

- Un único escritor por dimensión.
- Lectura de entradas y destinos con versiones Delta explícitas.
- Comprobación de la versión de partida antes de aplicar.
- Un MERGE por dimensión cuando existen diferencias.
- Productos y clientes tienen commits independientes.
- batch_id se utiliza para auditoría.
- No existe registro persistente para reconocer lotes históricos.
- No existe recuperación automática después de fallos.
- El operador mantiene el orden de las observaciones.
- Los resultados del ejecutor se imprimen como JSON en consola.

Si una ejecución falla después de escribir, debe revisarse el destino
antes de repetirla. Una entrada antigua no debe reprocesarse
automáticamente sobre un estado posterior.

## Estado

Flujo simplificado comprobado localmente con dos lotes consecutivos
por dimensión y repeticiones sin cambios.

La ejecución y validación de este flujo en Azure permanecen pendientes.
