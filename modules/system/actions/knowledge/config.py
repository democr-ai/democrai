from __future__ import annotations

from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


def _form_payload(ctx: dict[str, Any]) -> dict[str, Any]:
    payload = ctx.get("knowledge_runtime_config_form")
    if isinstance(payload, dict):
        return dict(payload)
    payload = ctx.get("config")
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _embedding_change_warning_response(module_sdk, payload: dict[str, Any]):
    count = module_sdk.knowledge.count_existing_embeddings()
    builder = module_sdk.ui.load("utils/ui/yaml/knowledge/embedding_model_change_warning")
    builder.set_data(
        "/knowledge/embedding_model_change_warning",
        {
            "config": payload,
            "text": module_sdk.i18n.t(
                "system.knowledge.config.embedding_change.text",
                context={"count": count},
            ),
        },
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            module_sdk.effects.build_aux_surface_messages(builder, "modal")
        )
    )


@action("save_knowledge_runtime_config")
@permission_required(["system.knowledge.extractor.manage"])
async def save_knowledge_runtime_config(ctx: dict[str, Any], session: dict, module_sdk):
    payload = _form_payload(ctx)
    confirmed = bool(ctx.get("confirm_embedding_model_change"))
    try:
        module_sdk.knowledge.update_runtime_config(
            payload,
            confirm_embedding_model_change=confirmed,
        )
    except RuntimeError as exc:
        if str(exc) == "knowledge_embedding_model_change_requires_rebuild":
            return _embedding_change_warning_response(module_sdk, payload)
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": str(exc)},
            ),
            module_sdk.effects.render(),
        )
    except ValueError as exc:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": str(exc)},
            ),
            module_sdk.effects.render(),
        )

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "modal"}}]),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success",
                "message": module_sdk.i18n.t("system.knowledge.config.toast.saved"),
            },
        ),
        module_sdk.effects.render(),
    )
