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
| 001_create_database.sql | Crear la base, se detiene si ya existe |
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
La generación y carga inicial de datos sintéticos se completó en M2.3.

## Carga inicial de datos sintéticos

Instalar las dependencias dentro del entorno virtual:

    python -m pip install -r requirements.txt

Generar y validar los archivos antes de la carga:

    python sources/generators/generate_initial_data.py
    python tests/generators/validate_initial_data.py

Si data/initial ya contiene la generación validada, no repetir
la generación sobre esa carpeta.

Ejecutar el cargador desde la raíz del repositorio:

    python sources/sqlserver/load_initial_data.py --host <host-accesible>

El cargador utiliza SQL_SERVER_PASSWORD cuando está configurada;
si falta, solicita la contraseña de retail_loader de forma oculta.
Utiliza una transacción para las cinco tablas y rechaza tablas con datos.

Antes de confirmar, reconcilia conteos, estados, importes y unidades
contra el manifiesto. Si falla, revierte la transacción.

Carga verificada con semilla 42:

- categories: 6 registros.
- products: 60 registros.
- customers: 500 registros.
- orders: 2000 registros.
- order_items: 5862 registros.
- Unidades totales: 14792.
- Importe bruto total: PEN 21645086.45.
- Descuento total: PEN 1667089.99.
- Importe neto total: PEN 19977996.46.
- Importe neto confirmado: PEN 15781257.30.
- Unidades confirmadas: 11682.

La transacción terminó con COMMIT y una consulta independiente
posterior confirmó los totales.

## Configuración local con .env

.env contiene la configuración local y está excluido de Git.
.env.example documenta las variables sin contraseñas reales.

- SQL_SERVER_HOST y SQL_SERVER_PORT: dirección accesible desde WSL.
- SQL_SERVER_DATABASE: TechRetail_OLTP.
- SQL_SERVER_USER: retail_loader.
- SQL_SERVER_PASSWORD: contraseña local del cargador.
- SQL_SERVER_READER_USER: retail_reader.
- SQL_SERVER_READER_PASSWORD: contraseña local de extracción.

El cargador lee variables de entorno; no abre .env automáticamente.
Para cargar la configuración y ejecutar una carga inicial:

```bash
(
    set -e
    set -a
    source .env
    set +a

    python sources/sqlserver/load_initial_data.py
)
```

.env debe contener asignaciones compatibles con Bash.
Las contraseñas requieren el escapado correspondiente a esa sintaxis.
Solo se debe cargar un archivo local de confianza.

El cargador rechaza tablas que ya contienen datos.
No ejecutar nuevamente para actualizar o reemplazar una carga existente.

Las conexiones de ambos usuarios con la configuración de .env
se verificaron mediante consultas de lectura sobre los 2000 pedidos.
