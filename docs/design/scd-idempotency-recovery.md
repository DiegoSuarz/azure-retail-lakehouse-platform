# Idempotencia y recuperación de lotes SCD

## Objetivo

Aplicar cada lote una sola vez y recuperar intentos interrumpidos
sin duplicar versiones ni recalcular claves ya planificadas.

Se admite un único escritor por dimensión.
No se aplica otro lote mientras exista uno pendiente de recuperación.

## Identidad del lote

batch_id identifica el lote lógico.
run_id identifica un intento de ejecución.

La identidad verificable del lote incluye:

- batch_id y dimensión.
- observed_at normalizado a UTC.
- Rutas y versiones Delta de las entradas utilizadas.
- Huella determinista de los atributos de entrada.
- Versión de las reglas de transformación.

La huella debe contemplar nombres, tipos, valores y nulos.
No debe depender del orden físico de las filas.

Un batch_id conocido con identidad diferente se rechaza.
Un reintento idéntico se reconoce antes de comprobar el orden temporal.

## Preparación persistente

Antes de modificar el destino se conserva:

- Identidad del lote.
- Ruta y versión Delta de partida del destino.
- Asignación de claves nuevas.
- Resultado dimensional completo preparado.
- Valores fijos de procedencia y auditoría.
- Estado y referencias de los artefactos de recuperación.

Los artefactos preparados se guardan en destinos exclusivos del lote.
Se verifican después de escribirlos y se registran sus versiones.

Un reintento reutiliza los artefactos aceptados.
No genera nuevas claves ni sustituye las marcas temporales de las filas.
Cada intento puede tener su propio run_id en el registro operativo.

Los argumentos y referencias de ejecución mantienen el flujo sin
manifiestos de entrada. El registro operativo documenta su aplicación.

## Aplicación por dimensión

Los cambios de filas existentes y las inserciones de nuevas versiones
se aplicarán mediante una única operación MERGE de Delta por dimensión.

El resultado preparado conserva todas las claves anteriores.
No se eliminan filas dimensionales.

Cierre e inserción no se ejecutan como escrituras independientes.
Una dimensión no debe quedar persistida con cierres pendientes de reemplazo.

Antes de aplicar se comprueba la versión Delta de partida.
Esta comprobación presupone el único escritor acordado;
no sustituye un mecanismo de bloqueo entre escritores concurrentes.

## Recuperación

| Estado observado | Acción |
|---|---|
| Lote aceptado e identidad coincidente | Devolver el resultado registrado |
| Preparación incompleta y destino intacto | Revisar o completar los artefactos |
| Preparación verificada y destino en versión de partida | Aplicar el resultado |
| Destino modificado y aceptación sin registrar | Comprobar commit y resultado persistido |
| Versión del destino o contenido inesperados | Bloquear para revisión |

Una escritura puede terminar aunque falle la actualización del informe.
Por eso el estado del informe no demuestra por sí solo qué contiene Delta.

La aceptación exige identificar la versión resultante y comprobar
su esquema, contenido y controles SCD contra el resultado preparado.

## Lotes sin cambios

Un lote sin cambios se registra como aceptado sin modificar las filas.
Su observed_at actualiza el control del último lote aceptado.

Un lote nuevo debe tener observed_at estrictamente posterior
al último aceptado para esa dimensión, incluso después de un lote vacío.

## Varias dimensiones

Productos y clientes tienen commits Delta independientes.
No se presupone una transacción conjunta entre tablas.

El registro conserva el progreso por dimensión.
La ejecución conjunta solo termina cuando ambas están aceptadas.
Una aplicación parcial debe recuperarse antes de iniciar otro lote.

## Pruebas de aceptación

- Reintento después de completar un lote.
- Mismo batch_id con contenido diferente.
- Reutilización de claves y auditoría del plan.
- Fallo antes de aplicar.
- Fallo después del commit y antes de registrar aceptación.
- Destino con versión inesperada.
- Lote sin cambios y control del orden temporal.
- Aplicación parcial entre productos y clientes.

## Estado

Contrato definido.
Implementación y pruebas pendientes.
