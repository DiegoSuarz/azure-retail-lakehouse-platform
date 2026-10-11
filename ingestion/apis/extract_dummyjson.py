"""Extrae las categorías tecnológicas de DummyJSON a archivos locales."""

import argparse
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from api_common import fetch_json, require, utc_now, write_json

CATEGORIES = ("laptops", "smartphones", "tablets", "mobile-accessories")


def validate_product(product, category):
    require(isinstance(product, dict), "Producto no válido")
    identifier = product.get("id")
    require(type(identifier) is int and identifier > 0, "ID inválido")
    title = product.get("title")
    require(
        isinstance(title, str) and bool(title.strip()),
        f"Título ausente: {identifier}",
    )
    require(
        product.get("category") == category,
        f"Categoría diferente: {identifier}",
    )
    for field in ("price", "rating"):
        value = product.get(field)
        require(
            type(value) is int or isinstance(value, Decimal),
            f"Valor numérico inválido: {identifier}/{field}",
        )
        number = Decimal(value)
        require(number.is_finite(), f"Valor no finito: {identifier}/{field}")
        if field == "rating":
            require(0 <= number <= 5, f"Rating fuera de rango: {identifier}")
    stock = product.get("stock")
    require(
        type(stock) is int and stock >= 0,
        f"Stock inválido: {identifier}",
    )
    return identifier


def register_response(files, root, path, metadata, row_count):
    relative = path.relative_to(root).as_posix()
    files[relative] = {
        "row_count": row_count,
        "sha256": metadata["payload_sha256"],
        "size_bytes": metadata["size_bytes"],
        "metadata_file": relative + ".metadata.json",
    }
    sidecar = path.with_name(path.name + ".metadata.json")
    files[relative + ".metadata.json"] = {
        "sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest(),
        "size_bytes": sidecar.stat().st_size,
    }


def extract(root, run_id, page_size):
    files = {}
    summaries = {}
    seen = set()
    categories_path = root / "categories.json"
    available, metadata = fetch_json(
        "https://dummyjson.com/products/category-list",
        categories_path, run_id, "dummyjson",
    )
    require(
        isinstance(available, list)
        and all(isinstance(value, str) for value in available),
        "Respuesta de categorías incompatible",
    )
    require(set(CATEGORIES) <= set(available), "Faltan categorías previstas")
    register_response(files, root, categories_path, metadata, len(available))

    for category in CATEGORIES:
        skip = 0
        page_number = 0
        expected_total = None

        while True:
            page_number += 1
            require(page_number <= 1000, "Límite de páginas superado")
            url = (
                f"https://dummyjson.com/products/category/{category}"
                f"?limit={page_size}&skip={skip}"
            )
            path = (
                root / f"category={category}"
                / f"page_{page_number:06d}.json"
            )
            data, metadata = fetch_json(url, path, run_id, "dummyjson")
            require(isinstance(data, dict), "Respuesta de productos incompatible")

            products = data.get("products")
            total = data.get("total")
            limit = data.get("limit")
            require(isinstance(products, list), "Falta la lista products")
            require(type(total) is int and total >= 0, "Total inválido")
            require(
                type(data.get("skip")) is int and data["skip"] == skip,
                "Desplazamiento de página incorrecto",
            )
            require(
                type(limit) is int and 0 <= limit <= page_size
                and len(products) <= limit,
                "Tamaño de página incompatible",
            )

            if expected_total is None:
                expected_total = total
            require(total == expected_total, "El total cambió durante la extracción")
            require(
                bool(products) or skip == total == 0,
                "Página vacía inesperada",
            )

            for product in products:
                identifier = validate_product(product, category)
                require(identifier not in seen, f"ID duplicado: {identifier}")
                seen.add(identifier)

            register_response(files, root, path, metadata, len(products))
            skip += len(products)
            require(skip <= total, "Se recibieron más productos que el total")
            print(f"PASS: {category}, página {page_number}, {len(products)} productos.")

            if skip == total:
                break

        summaries[category] = {
            "product_count": skip,
            "page_count": page_number,
        }

    return files, summaries, len(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument(
        "--output-root", type=Path, default=Path("data/apis")
    )
    args = parser.parse_args()
    if not 1 <= args.page_size <= 100:
        parser.error("--page-size debe estar entre 1 y 100.")

    run_id = str(uuid4())
    started_at = utc_now()
    ingestion_date = datetime.now(timezone.utc).date().isoformat()
    root = (
        args.output_root / "dummyjson" / "products"
        / f"ingestion_date={ingestion_date}" / f"run_id={run_id}"
    )
    root.mkdir(parents=True, exist_ok=False)
    print(f"EXTRACCIÓN: {root}")

    try:
        files, summaries, count = extract(root, run_id, args.page_size)
        write_json(root / "manifest.json", {
            "schema_version": 1,
            "source_system": "dummyjson",
            "ingestion_run_id": run_id,
            "ingestion_date": ingestion_date,
            "extraction_started_at": started_at,
            "extraction_finished_at": utc_now(),
            "categories": summaries,
            "unique_product_count": count,
            "files": files,
            "status": "completed",
            "consistency_limitation": "La API no ofrece una instantánea transaccional.",
        })
    except BaseException as error:
        write_json(root / "failure.json", {
            "status": "failed",
            "ingestion_run_id": run_id,
            "failed_at": utc_now(),
            "error_type": type(error).__name__,
            "error_message": str(error),
        })
        raise

    print(f"COMPLETADO: {count} productos únicos de cuatro categorías.")
    print(f"MANIFIESTO: {root / 'manifest.json'}")
    print("ALCANCE: extracción local; publicación en Bronze pendiente.")


if __name__ == "__main__":
    main()
