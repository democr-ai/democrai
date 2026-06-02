from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.ui.knowledge.extractors import (
    extractor_config_form_model,
    extractor_engine_row,
)


async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    extractor_id = str(route_params.get("extractor_id") or "").strip().lower()
    row = extractor_engine_row(sdk, extractor_id)
    if row is None:
        return None

    form_model = extractor_config_form_model(sdk, row, phase="install")
    if not form_model:
        return None

    builder = sdk.ui.load("utils/ui/yaml/knowledge/extractors/install_config")
    builder.set_store(
        "/extractor_install_config",
        {
            "extractor_id": extractor_id,
            "form_model": form_model,
        },
    )
    return builder
