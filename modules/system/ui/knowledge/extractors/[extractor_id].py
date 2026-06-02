from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.knowledge.extractors import (
    extractor_config_form_model,
    extractor_engine_row,
    extractor_status_variant,
)


async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    extractor_id = str(route_params.get("extractor_id") or "").strip().lower()
    row = extractor_engine_row(sdk, extractor_id)
    if row is None:
        return None

    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    merge_builders(builder, sdk.ui.load("utils/ui/yaml/knowledge/extractors/detail"))

    mime_count = int(row.get("mime_type_count") or 0)
    current_extractor = {
        "extractor_id": extractor_id,
        "registry_row_id": row.get("registry_row_id"),
        "name": str(row.get("name") or extractor_id),
        "status": str(row.get("status") or "uninstalled"),
        "status_variant": extractor_status_variant(
            str(row.get("status") or "uninstalled")
        ),
        "icon_url": str(row.get("icon_url") or "assets/engines/llamacpp.png"),
        "mime_count_label": sdk.i18n.t(
            "system.knowledge.extractors.mime_count",
            context={"count": mime_count},
        ),
        "summary": sdk.i18n.t(
            "system.knowledge.extractor_detail.mime_types_supported",
            context={"count": mime_count},
        ),
    }
    runtime_form_model = extractor_config_form_model(sdk, row, phase="runtime")
    builder.set_store("/current_extractor", current_extractor)
    builder.set_store("/current_extractor/runtime_form_model", runtime_form_model)
    builder.set_store("/current_extractor/show_runtime_config", bool(runtime_form_model))

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["knowledge_extractor_detail_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
