from __future__ import annotations

from democrai.sdk.auth import permission_required
from typing import Any

from democrai.sdk.decorators import action


_STEPS = [
    {
        "id": "profile",
        "title": "Account",
        "description": "Capture owner profile and billing contact.",
        "content": "Forward navigation stays locked until this step is validated.",
    },
    {
        "id": "workspace",
        "title": "Workspace",
        "description": "Choose workspace settings and default policies.",
        "content": "Backward navigation remains available without another validation.",
    },
    {
        "id": "access",
        "title": "Access",
        "description": "Invite users and assign initial roles.",
        "content": "Direct forward jumps require every previous step to be validated.",
    },
    {
        "id": "review",
        "title": "Review",
        "description": "Confirm the configuration before activation.",
        "content": "The final step is reachable only after the earlier gates are complete.",
    },
]


def _ctx_params(ctx: dict[str, Any]) -> dict[str, Any]:
    raw = ctx.get("params")
    return dict(raw) if isinstance(raw, dict) else {}


def _ctx_value(ctx: dict[str, Any], key: str, default: Any = None) -> Any:
    params = _ctx_params(ctx)
    return ctx.get(key) if key in ctx else params.get(key, default)


def _surface_id(ctx: dict[str, Any]) -> str:
    return str(ctx.get("_surface_id") or "main").strip() or "main"


def _stream_id(ctx: dict[str, Any]) -> str | None:
    raw = ctx.get("stream_id")
    value = str(raw or "").strip()
    return value or None


def _wizard_id(ctx: dict[str, Any]) -> str:
    raw = _ctx_value(ctx, "target_wizard") or _ctx_value(ctx, "wizard_id")
    return str(raw or "components_complex_wizard_live").strip() or "components_complex_wizard_live"


def _normalize_steps(raw_steps: Any) -> list[dict[str, Any]]:
    if isinstance(raw_steps, list):
        steps = [dict(step) for step in raw_steps if isinstance(step, dict)]
        if steps:
            return steps
    return [dict(step) for step in _STEPS]


def _ids(steps: list[dict[str, Any]]) -> list[str]:
    return [str(step.get("id") or "").strip() for step in steps if str(step.get("id") or "").strip()]


def _normalize_validated(raw_validated: Any, ids: list[str]) -> list[str]:
    if not isinstance(raw_validated, list):
        return []
    valid_ids = set(ids)
    return [str(item).strip() for item in raw_validated if str(item).strip() in valid_ids]


async def _current_state(ctx: dict[str, Any], sdk) -> tuple[list[dict[str, Any]], str, list[str]]:
    wizard_id = _wizard_id(ctx)
    stream_id = _stream_id(ctx)
    surface_id = _surface_id(ctx)
    props = await sdk.effects.ask_current_component_props(
        stream_id,
        wizard_id,
        surface_id=surface_id,
    )
    source = props if isinstance(props, dict) else ctx
    steps = _normalize_steps(source.get("steps"))
    ids = _ids(steps)
    fallback = ids[0] if ids else "profile"
    active = str(source.get("active_step_id") or fallback).strip() or fallback
    if active not in ids:
        active = fallback
    validated = _normalize_validated(source.get("validated_steps"), ids)
    return steps, active, validated


def _state_payload(steps: list[dict[str, Any]], active: str, validated: list[str]) -> dict[str, Any]:
    return {
        "steps": [dict(step) for step in steps],
        "active_step_id": active,
        "validated_steps": [str(item) for item in validated],
    }


def _update_effects(
    sdk,
    ctx: dict[str, Any],
    steps: list[dict[str, Any]],
    active: str,
    validated: list[str],
) -> list[dict]:
    wizard_id = _wizard_id(ctx)
    surface_id = _surface_id(ctx)
    state = _state_payload(steps, active, validated)
    return [
        sdk.effects.ui_property_update(wizard_id, "steps", state["steps"], action="set", surface_id=surface_id),
        sdk.effects.ui_property_update(wizard_id, "active_step_id", state["active_step_id"], surface_id=surface_id),
        sdk.effects.ui_property_update(
            wizard_id,
            "validated_steps",
            state["validated_steps"],
            action="set",
            surface_id=surface_id,
        ),
    ]


def _status_toast(sdk, title: str, text: str, variant: str = "info") -> dict:
    return sdk.effects.notify(
        "toast",
        {"title": title, "text": text, "variant": variant, "duration": 2200},
    )


def _previous_validated(ids: list[str], target_idx: int, validated: list[str]) -> bool:
    validated_set = set(validated)
    return all(step_id in validated_set for step_id in ids[:target_idx])


def _step_title(steps: list[dict[str, Any]], step_id: str) -> str:
    for step in steps:
        if str(step.get("id") or "").strip() == step_id:
            return str(step.get("title") or step_id).strip() or step_id
    return step_id


@action("wizard_validate_current")
@permission_required(["components.documentation.view"])
async def wizard_validate_current(ctx: dict, sdk) -> dict:
    steps, active, validated = await _current_state(ctx, sdk)
    if active not in validated:
        validated = [*validated, active]

    return sdk.effects.respond(
        *_update_effects(sdk, ctx, steps, active, validated),
        _status_toast(sdk, "Wizard", f"Step '{_step_title(steps, active)}' validated.", "success"),
    )


@action("wizard_next")
@permission_required(["components.documentation.view"])
async def wizard_next(ctx: dict, sdk) -> dict:
    steps, active, validated = await _current_state(ctx, sdk)
    ids = _ids(steps)
    active_idx = ids.index(active) if active in ids else 0

    if active not in set(validated):
        return sdk.effects.respond(
            *_update_effects(sdk, ctx, steps, active, validated),
            _status_toast(sdk, "Wizard", "Validate the current step before continuing.", "warning"),
        )

    next_active = ids[min(active_idx + 1, len(ids) - 1)] if ids else active
    return sdk.effects.respond(*_update_effects(sdk, ctx, steps, next_active, validated))


@action("wizard_prev")
@permission_required(["components.documentation.view"])
async def wizard_prev(ctx: dict, sdk) -> dict:
    steps, active, validated = await _current_state(ctx, sdk)
    ids = _ids(steps)
    active_idx = ids.index(active) if active in ids else 0
    prev_active = ids[max(active_idx - 1, 0)] if ids else active
    return sdk.effects.respond(*_update_effects(sdk, ctx, steps, prev_active, validated))


@action("wizard_go_to")
@permission_required(["components.documentation.view"])
async def wizard_go_to(ctx: dict, sdk) -> dict:
    steps, active, validated = await _current_state(ctx, sdk)
    target = str(_ctx_value(ctx, "step_id", "") or "").strip()
    ids = _ids(steps)
    if target not in ids:
        return sdk.effects.respond(*_update_effects(sdk, ctx, steps, active, validated))

    active_idx = ids.index(active) if active in ids else 0
    target_idx = ids.index(target)
    if target_idx > active_idx and not _previous_validated(ids, target_idx, validated):
        return sdk.effects.respond(
            *_update_effects(sdk, ctx, steps, active, validated),
            _status_toast(
                sdk,
                "Wizard",
                "Validate every previous step before jumping forward.",
                "warning",
            ),
        )
    return sdk.effects.respond(*_update_effects(sdk, ctx, steps, target, validated))


@action("wizard_dispatch")
@permission_required(["components.documentation.view"])
async def wizard_dispatch(ctx: dict, sdk) -> dict:
    intent = str(ctx.get("intent") or "").strip().lower()
    if intent == "next":
        return await wizard_next(ctx, sdk)
    if intent == "prev":
        return await wizard_prev(ctx, sdk)
    if intent == "step_click":
        return await wizard_go_to(ctx, sdk)
    return sdk.effects.respond()


@action("wizard_reset")
@permission_required(["components.documentation.view"])
async def wizard_reset(ctx: dict, sdk) -> dict:
    steps = [dict(step) for step in _STEPS]
    active = steps[0]["id"]
    return sdk.effects.respond(
        *_update_effects(sdk, ctx, steps, active, []),
        _status_toast(sdk, "Wizard", "Wizard reset.", "info"),
    )
