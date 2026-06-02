from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.model.runtime import (
    active_job_items,
    active_model_items,
    engine_rows_by_id,
    loaded_model_items,
)


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/models/model_list")
    merge_builders(builder, page_builder)

    engines_by_id = engine_rows_by_id(sdk)
    active_rows = (
        sdk.models.model_registry.all(
            filters={"status": "active"},
            sort={"field": "name", "direction": "asc"},
        ).get("rows")
        or []
    )
    loaded_rows = await sdk.engines.list_loaded_models()
    active_job_rows = await sdk.engines.list_active_jobs()

    builder.set_store(
        "/system/model/active/items",
        active_model_items(list(active_rows), engines_by_id),
        scope="page",
    )
    builder.set_store(
        "/system/model/loaded/items",
        loaded_model_items(list(loaded_rows), engines_by_id),
        scope="page",
    )
    builder.set_store(
        "/system/model/jobs/items",
        active_job_items(list(active_job_rows), engines_by_id),
        scope="page",
    )

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["system_model_list_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
