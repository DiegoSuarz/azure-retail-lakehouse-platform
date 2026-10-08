# Generación de datos incrementales

## Requisitos

Ejecutar desde la raíz del repositorio con el entorno virtual activo.
Los generadores utilizan únicamente la biblioteca estándar.

data/initial debe contener el conjunto inicial validado.

## Generación

Ejecutar en este orden:

    python tests/generators/validate_initial_data.py
    python sources/generators/generate_incremental_data.py
    python sources/generators/generate_ordering_data.py
    python sources/generators/generate_invalid_data.py

Los scripts rechazan salidas existentes para evitar sobrescrituras.

Para generar otra copia, usar el mismo --output-dir en los tres
generadores. Los validadores actuales utilizan data/incremental.

## Organización

- functional/batch_001: pedidos nuevos y cambios S01–S07.
- functional/batch_002 a batch_004: eventos S08–S12.
- invalid/S13 a invalid/S20: casos inválidos aislados.
- expectations.json: controles del primer lote.
- ordering-expectations.json: orden de entrega y estados esperados.
- invalid-expectations.json: anomalías y base requerida por caso.

Los archivos generados están excluidos de Git.
El código y la documentación permiten reconstruirlos.

## Validación

    python tests/generators/validate_incremental_data.py
    python tests/generators/validate_ordering_data.py
    python tests/generators/validate_invalid_data.py

Las comprobaciones cubren:

- Integridad y reglas del primer lote.
- Reconciliación independiente de estados, importes y unidades.
- Simulación de reprocesos, duplicados y secuencias pendientes.
- Anomalías previstas de los ocho casos inválidos.

S18 contiene un hash deliberadamente incorrecto.

S19 reutiliza un pedido inicial con contenido diferente y conserva
su fecha original, anterior al corte. No es un caso de una única
regla incumplida.

## Controles del primer lote

Resultados verificados con el conjunto inicial de semilla 42:

- Pedidos finales: 2002.
- Líneas finales: 5864.
- Pedidos confirmados: 1580.
- Variación neta confirmada: PEN 22075.57.
- Importe neto confirmado: PEN 15803332.87.
- Variación de unidades confirmadas: 6.
- Unidades confirmadas: 11688.

Los lotes adicionales de orden afectan únicamente al cliente
seleccionado y no cambian estos controles de ventas.

## Alcance

Los scripts no modifican SQL Server.

Las simulaciones locales verifican las fuentes y sus expectativas.
La aplicación en Silver, la cuarentena, las marcas de agua y
los históricos SCD se implementarán en módulos posteriores.
