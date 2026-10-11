# Datos de referencia

## Mapeo de productos externos

product_external_mapping.csv relaciona seis productos locales
con productos de la extracción validada de DummyJSON.

Columnas:

- source_system: fuente externa.
- external_product_id: identificador externo.
- product_id: identificador de TechRetail_OLTP.
- mapping_type: synthetic_demo.
- mapping_note: explicación de la asociación educativa.

Se seleccionaron tres laptops y tres smartphones.
Las claves existen en ambos catálogos y las asociaciones son únicas
por producto local y externo.

Las asociaciones no representan equivalencias comerciales.
No sustituyen nombres, marcas, categorías ni precios locales.
No se establecieron por igualdad de identificadores.

El archivo permitirá practicar JOIN entre fuentes.
Los atributos externos conservarán nombres separados.
Los productos sin asociación seguirán siendo válidos.

## Estado

Archivo creado y referencias verificadas.
Incorporación a Silver pendiente.
