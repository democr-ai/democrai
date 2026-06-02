from __future__ import annotations

from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.utils.ui.engine.available_models import (
    filter_available_items,
    load_available_items,
    model_filter_value,
)


@action("filter_engine_available_models")
@permission_required(["system.engine.model.manage"])
async def filter_engine_available_models(
    ctx: dict[str, Any], session: dict, module_sdk
):
    engine_id = int(ctx["engine_id"])
    name = model_filter_value(ctx, "engine_models_available_name_filter")
    capability = model_filter_value(ctx, "engine_models_available_capability_filter")
    items = list(ctx["items"])
    error = ""
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_models_available/all": items,
                            "/engine_models_available/filtered": filter_available_items(
                                items,
                                name=name,
                                capability=capability,
                            ),
                            "/engine_models_available/error": error,
                            "/engine_models_available/filters/name": name,
                            "/engine_models_available/filters/capability": capability,
                            "/engine_models_available/loading": False,
                        },
                    }
                }
            ]
        )
    )


@action("load_engine_available_models")
@permission_required(["system.engine.model.manage"])
async def load_engine_available_models(ctx: dict[str, Any], session: dict, module_sdk):
    engine_id = int(ctx["engine_id"])
    name = model_filter_value(ctx, "engine_models_available_name_filter")
    capability = model_filter_value(ctx, "engine_models_available_capability_filter")
    result = ctx.get("result")
    if isinstance(result, dict):
        items = [
            item
            for item in list(result.get("items") or [])
            if isinstance(item, dict)
        ]
        error = str(result.get("error") or "")
    else:
        try:
            items = await load_available_items(module_sdk, engine_id)
            error = ""
        except Exception as exc:
            items = []
            error = str(exc)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_models_available/all": items,
                            "/engine_models_available/filtered": filter_available_items(
                                items,
                                name=name,
                                capability=capability,
                            ),
                            "/engine_models_available/error": error,
                            "/engine_models_available/filters/name": name,
                            "/engine_models_available/filters/capability": capability,
                            "/engine_models_available/loading": False,
                        },
                    }
                }
            ]
        )
    )
