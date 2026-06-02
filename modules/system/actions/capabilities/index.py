from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action, validate

from modules.system.utils.actions.capabilities.index import save_capability_priorities
from modules.system.utils.ui.capabilities.list import priority_select_id


class SaveCapabilityPrioritiesPayload(BaseModel):
    capability: str = Field(min_length=1)
    priority_1: str | int | None = None
    priority_2: str | int | None = None
    priority_3: str | int | None = None

    @field_validator("capability")
    @classmethod
    def _clean_capability(cls, value: str) -> str:
        capability = value.strip().lower()
        if not capability:
            raise ValueError("capability is required")
        return capability


def _priority_payload(ctx: dict) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for priority in range(1, 4):
        field = f"priority_{priority}"
        input_id = priority_select_id(ctx["capability"], priority)
        if input_id and input_id in ctx:
            payload[field] = ctx.get(input_id)
        else:
            payload[field] = ctx.get(field)
    return payload


def _select_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _toast(module_sdk, level: str, message_key: str):
    return module_sdk.effects.notify(
        "toast",
        {
            "level": level,
            "message": module_sdk.i18n.t(message_key),
        },
    )


def _error_message_key(error: Exception) -> str:
    error_code = str(error)
    if "duplicate_model" in error_code:
        return "system.capabilities.priority.toast.duplicate"
    if "invalid_model" in error_code or "invalid literal" in error_code:
        return "system.capabilities.priority.toast.invalid_model"
    return "system.capabilities.priority.toast.error"


async def _select_update_effects(
    module_sdk,
    ctx: dict,
    values: dict[str, Any],
) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for priority in range(1, 4):
        field = f"priority_{priority}"
        await module_sdk.effects.publish_property_update(
            ctx["stream_id"],
            priority_select_id(ctx["capability"], priority),
            "value",
            _select_value(values.get(field)),
        )
    return effects


@action("open_capabilities_page")
@permission_required(["system.model.capability.list"])
async def open_capabilities_page(ctx: dict, session: dict, module_sdk):
    return module_sdk.effects.respond(
        module_sdk.effects.navigate("/system/capabilities/list", render=True)
    )


@action("save_capability_priorities")
@validate(SaveCapabilityPrioritiesPayload)
@permission_required(["system.model.capability.update"])
async def save_capability_priorities_action(ctx: dict, session: dict, module_sdk):
    priority_payload = _priority_payload(ctx)
    try:
        save_capability_priorities(
            module_sdk,
            ctx["capability"],
            priority_1=priority_payload.get("priority_1"),
            priority_2=priority_payload.get("priority_2"),
            priority_3=priority_payload.get("priority_3"),
        )
    except ValueError as exc:
        return module_sdk.effects.respond(
            _toast(module_sdk, "error", _error_message_key(exc)),
            module_sdk.effects.render(),
        )

    await _select_update_effects(module_sdk, ctx, priority_payload)

    return module_sdk.effects.respond(
        _toast(module_sdk, "success", "system.capabilities.priority.toast.saved")
    )
