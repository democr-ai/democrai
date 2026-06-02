from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.knowledge.extractors import (
    extractor_mime_type_rows,
    extractor_mime_type_table_model,
)


def _extractor_id(params: dict) -> str:
    route_params = (
        params.get("route_params")
        if isinstance(params.get("route_params"), dict)
        else {}
    )
    return str(route_params.get("extractor_id") or "").strip()


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/knowledge/extractors/mime_types")

    rows = extractor_mime_type_rows(sdk, extractor_id=_extractor_id(params))
    table = builder.get_component("knowledge_extractor_mime_types_table")
    if table is not None:
        table.set_property("model", extractor_mime_type_table_model(sdk))
        table.set_property("rows", rows)
        table.set_property("total_rows", len(rows))

    return builder
