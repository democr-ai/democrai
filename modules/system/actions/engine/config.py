from __future__ import annotations

from typing import Any

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.utils.actions.engine.config import (
    upsert_engine_from_config,
)


async def _save_engine_config_common(
    ctx: dict[str, Any],
    session: dict[str, Any],
    module_sdk,
    *,
    activate_after_save: bool,
):
    from modules.system.actions.engine.lifecycle import (
        _activate_engine_or_prompt_install,
    )

    provider = str(ctx["provider"]).strip().lower() if "provider" in ctx else ""
    if not provider:
        return module_sdk.effects.respond(module_sdk.effects.render())
    requirements = await module_sdk.engines.provider_requirements(provider_id=provider)
    if not bool(requirements.get("configurable")) and not bool(requirements.get("supported")):
        return module_sdk.effects.respond(module_sdk.effects.render())

    engine_id = (
        int(ctx["engine_id"])
        if "engine_id" in ctx and ctx["engine_id"] is not None
        else None
    )

    payload = dict(ctx[str(ctx["form_id"])])
    resolved_engine_id = upsert_engine_from_config(
        module_sdk,
        provider=provider,
        engine_id=engine_id,
        payload=payload,
    )
    if resolved_engine_id is None:
        return module_sdk.effects.respond(module_sdk.effects.render())

    await module_sdk.engines.stop_engine(
        engine_registry_id=resolved_engine_id,
    )

    if not activate_after_save:
        surface_id = str(ctx.get("_surface_id") or "drawer")
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": surface_id}}]),
            module_sdk.effects.render(),
        )

    return await _activate_engine_or_prompt_install(
        module_sdk,
        engine_id=resolved_engine_id,
        provider=provider,
        session=session,
        close_surface_id=str(ctx.get("_surface_id") or "drawer"),
    )


@action("save_engine_config")
@permission_required(["system.engine.manage"])
async def save_engine_config(ctx: dict[str, Any], session: dict, module_sdk):
    return await _save_engine_config_common(
        ctx,
        session,
        module_sdk,
        activate_after_save=False,
    )


@action("save_and_activate_engine_config")
@permission_required(["system.engine.manage"])
async def save_and_activate_engine_config(
    ctx: dict[str, Any], session: dict, module_sdk
):
    return await _save_engine_config_common(
        ctx,
        session,
        module_sdk,
        activate_after_save=True,
    )


@action("delete_engine")
@permission_required(["system.engine.manage"])
async def delete_engine(ctx: dict[str, Any], session: dict, module_sdk):
    if "engine_id" not in ctx:
        return module_sdk.effects.respond(module_sdk.effects.render())

    engine_id = int(ctx["engine_id"])
    provider = str(ctx["provider"]).strip().lower() if "provider" in ctx else ""
    requirements = (
        await module_sdk.engines.provider_requirements(provider_id=provider)
        if provider
        else {}
    )
    if provider and bool(requirements.get("configurable")):
        try:
            module_sdk.models.engine_registry.delete(engine_id)
        except Exception as exc:
            module_sdk.system.log(
                f"[engine.activation] delete failed engine_id={engine_id}: {exc}",
                "error",
            )
    return module_sdk.effects.respond(module_sdk.effects.render())
