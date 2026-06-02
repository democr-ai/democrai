from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.ui.engine.model.test_params import _config_form_model


async def render(params: dict, session: dict):
    row_id = int(params["id"])
    row = sdk.models.model_registry.view(row_id)
    constants = await sdk.engines.constants()
    builder = sdk.ui.load("utils/ui/yaml/models/engine_model_defaults_params")
    builder.set_store(
        "/engine_model_defaults_params",
        {
            "model_row_id": row_id,
            "config_form_model": (
                await _config_form_model(row, constants) if isinstance(row, dict) else []
            ),
        },
        scope="page",
    )
    return builder
