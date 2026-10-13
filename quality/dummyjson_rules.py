"""Evalúa una extracción conservada de DummyJSON."""

import re
from urllib.parse import parse_qs, urlparse

from quality.api_extraction_input import ExtractionError, parse_json, require
from quality.api_record_rules import CATEGORIES, evaluate_product


def evaluate_dummyjson(manifest, responses, payloads):
    require(
        manifest.get("source_system") == "dummyjson",
        "DQ014", "Fuente incompatible",
    )
    summaries = manifest.get("categories")
    require(
        isinstance(summaries, dict) and set(summaries) == CATEGORIES,
        "DQ014", "Categorías del manifiesto incompatibles",
    )
    available = responses.get("categories.json")
    require(
        isinstance(available, list)
        and all(isinstance(value, str) for value in available),
        "DQ014", "Lista de categorías incompatible",
    )
    require(CATEGORIES <= set(available), "DQ014", "Faltan categorías previstas")
    require(
        type(manifest["files"]["categories.json"].get("row_count")) is int
        and manifest["files"]["categories.json"]["row_count"] == len(available),
        "DQ003", "Conteo de categorías diferente",
    )

    records = []
    seen = set()
    expected_files = {"categories.json"}

    for category in sorted(CATEGORIES):
        pattern = rf"category={re.escape(category)}/page_(\d{{6}})\.json"
        pages = sorted(
            (int(match.group(1)), name)
            for name in responses
            if (match := re.fullmatch(pattern, name))
        )
        require(bool(pages), "DQ014", f"Sin páginas: {category}")
        require(
            [number for number, _ in pages] == list(range(1, len(pages) + 1)),
            "DQ014", f"Páginas discontinuas: {category}",
        )
        expected_files.update(name for _, name in pages)
        offset = 0
        expected_total = None

        for number, name in pages:
            data = responses[name]
            require(isinstance(data, dict), "DQ014", f"Página incompatible: {name}")
            products = data.get("products")
            total = data.get("total")
            limit = data.get("limit")
            require(isinstance(products, list), "DQ014", f"Falta products: {name}")
            require(
                type(total) is int and total >= 0,
                "DQ014", f"Total inválido: {name}",
            )
            require(
                type(data.get("skip")) is int and data["skip"] == offset,
                "DQ014", f"Desplazamiento incorrecto: {name}",
            )
            require(
                type(limit) is int and limit >= 0 and len(products) <= limit,
                "DQ014", f"Tamaño de página incompatible: {name}",
            )

            provenance = parse_json(
                payloads[name + ".metadata.json"], "DQ004", name
            )
            request = urlparse(provenance["request_url"])
            query = parse_qs(request.query)
            require(
                request.path == f"/products/category/{category}",
                "DQ014", f"Endpoint diferente de la categoría: {name}",
            )
            try:
                requested_skip = int(query["skip"][0])
                requested_limit = int(query["limit"][0])
                require(
                    len(query["skip"]) == len(query["limit"]) == 1,
                    "DQ014", f"Parámetros repetidos: {name}",
                )
            except (KeyError, ValueError, IndexError) as error:
                raise ExtractionError(
                    "DQ014", f"Parámetros de paginación inválidos: {name}"
                ) from error
            require(
                requested_skip == offset and requested_limit > 0
                and limit <= requested_limit,
                "DQ014", f"Solicitud incompatible con la página: {name}",
            )

            if expected_total is None:
                expected_total = total
            require(total == expected_total, "DQ014", f"Total cambiante: {category}")
            require(
                bool(products) or offset == total == 0,
                "DQ014", f"Página vacía inesperada: {name}",
            )
            metadata = manifest["files"][name]
            require(
                type(metadata.get("row_count")) is int
                and metadata["row_count"] == len(products),
                "DQ003", f"Conteo diferente: {name}",
            )

            for position, product in enumerate(products, 1):
                result = evaluate_product(product, category)
                identifier = product.get("id") if isinstance(product, dict) else None
                if type(identifier) is int and identifier > 0:
                    require(
                        identifier not in seen,
                        "DQ014", f"Identificador repetido: {identifier}",
                    )
                    seen.add(identifier)
                records.append({
                    **result,
                    "source_file": name,
                    "record_number": position,
                    "business_key": {"external_product_id": identifier},
                })

            offset += len(products)
            require(offset <= total, "DQ014", f"Total excedido: {category}")
            require(
                number == len(pages) or offset < total,
                "DQ014", f"Páginas adicionales después del total: {category}",
            )

        require(offset == expected_total, "DQ014", f"Extracción incompleta: {category}")
        summary = summaries[category]
        require(
            isinstance(summary, dict)
            and type(summary.get("product_count")) is int
            and type(summary.get("page_count")) is int
            and summary["product_count"] == offset
            and summary["page_count"] == len(pages),
            "DQ017", f"Resumen diferente: {category}",
        )

    require(
        set(responses) == expected_files,
        "DQ014", "Respuestas adicionales o incompatibles",
    )
    require(
        type(manifest.get("unique_product_count")) is int
        and manifest["unique_product_count"] == len(seen),
        "DQ017", "Conteo de identificadores únicos diferente",
    )
    return records
