# SQL Server de origen

## Base de datos

TechRetail_OLTP representa el sistema transaccional de la tienda
ficticia de artículos tecnológicos.

Entorno verificado:

- SQL Server 2022 Developer, versión 16.0.1200.5.
- Base ONLINE.
- Recuperación FULL.
- Collation Modern_Spanish_CI_AS.

La recuperación FULL requiere planificar respaldos del log si se
mantiene durante el desarrollo. Ese procedimiento aún está pendiente.

## Scripts

| Archivo | Función |
|---|---|
| 001_create_database.sql | Crear la base; se detiene si ya existe |
| 002_create_tables.sql | Crear las cinco tablas dentro de una transacción |
| 003_configure_users.sql | Crear usuarios ausentes y aplicar permisos |

Los scripts 001 y 002 son de creación inicial.
No se deben repetir sobre una instalación existente.

El script 003 requiere que retail_loader y retail_reader existan
como logins del servidor. Sus contraseñas se configuran localmente
mediante la conexión administradora y no se guardan en Git.

003 puede reaplicar los permisos previstos. No elimina permisos
adicionales ni corrige un usuario asociado a otro login.

## Accesos

| Acceso | Propósito |
|---|---|
| Identidad Windows administradora | Crear y administrar objetos |
| retail_loader | SELECT, INSERT y UPDATE sobre las cinco tablas |
| retail_reader | SELECT sobre las cinco tablas para extracción |

Los logins del proyecto no reciben roles administrativos.

## Conexiones desde WSL

La administración se verificó ejecutando sqlcmd.exe de Windows
desde WSL con autenticación integrada mediante -E.

La ruta local verificada del cliente Windows es:

C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\SQLCMD.EXE

El helper retail_admin está definido en ~/.bashrc y acepta:

    retail_admin <database> "<query>"

Utiliza localhost, autenticación Windows y salida tabular.
Su configuración reside en el equipo local.

Las conexiones de retail_loader y retail_reader utilizan el cliente
sqlcmd de Linux, autenticación SQL y el host accesible desde WSL.
La dirección de ese host puede cambiar entre sesiones de WSL.

Las contraseñas se introducen de forma oculta mediante read -s
y se suministran mediante SQLCMDPASSWORD. Se elimina la variable
al finalizar su uso.

La opción -C se utiliza para confiar en el certificado del servidor
local de desarrollo. La configuración TLS se revisará para otros entornos.

## Comprobaciones realizadas

El archivo ../../tests/sqlserver/001_validate_schema.sql permite
inspeccionar claves y restricciones.

Resultados verificados:

- Cinco tablas con las columnas previstas.
- Cinco claves primarias.
- Tres restricciones únicas.
- Cuatro claves foráneas.
- Dieciséis restricciones CHECK.
- Claves foráneas y CHECK habilitados y confiables.
- Claves foráneas con eliminación NO_ACTION.
- Quince permisos explícitos de tabla para retail_loader.
- Cinco permisos explícitos de tabla para retail_reader.

Se probaron conexiones reales desde WSL con ambos logins.

En dbo.orders se verificaron los permisos efectivos:

- retail_reader: SELECT permitido; INSERT, UPDATE y DELETE ausentes.
- retail_loader: SELECT, INSERT y UPDATE permitidos; DELETE y ALTER ausentes.
- retail_loader no pertenece a sysadmin.
- orders contiene cero registros antes de la carga sintética.

El script 003 se ejecutó correctamente sobre los usuarios existentes.

## Estado

La base, las tablas y los accesos están implementados.
La generación y carga de datos sintéticos corresponde a M2.3.
