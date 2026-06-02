from __future__ import annotations

import json
from typing import Any

from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.platform.utils.identity import to_int_or_zero


def json_loads(value: str, default: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return default
    return json.loads(raw)


async def resolve_provider(request: Any, *, event_hook: Any = None):
    resolved = await resolve_provider_result(
        request,
        allow_prompt=True,
        event_hook=event_hook,
    )
    status = (resolved or {}).get("status")
    provider = (resolved or {}).get("provider")
    if status != "ok" or provider is None:
        raise RuntimeError(provider_unavailable_error(resolved))
    return provider


async def validate_provider(request: Any) -> dict[str, Any]:
    return validate_selector(request)


async def resolve_provider_result(
    request: Any,
    *,
    allow_prompt: bool,
    event_hook: Any = None,
):
    selector_type = request.selector_type
    from democrai.core.application.ai.orchestrator import model_orchestrator

    if selector_type == "model_registry_id":
        model_registry_id = to_int_or_zero(request.model_registry_id)
        resolved = await model_orchestrator.get_provider_by_model_registry_id(
            model_registry_id,
            confirm_swap=request.confirm_swap,
            event_hook=event_hook,
        )
    elif selector_type in {"objective", "capability"}:
        capabilities = json_loads(request.capabilities_json, [])
        if not isinstance(capabilities, list):
            raise RuntimeError("engine_orchestrator_capabilities_list_required")
        objective = request.objective or request.capability
        if not objective:
            raise RuntimeError("engine_orchestrator_objective_required")
        resolved = await model_orchestrator.get_provider_for_objective(
            objective,
            confirm_swap=request.confirm_swap,
            required_capabilities=[
                item for item in capabilities if item
            ],
            prefer_local=optional_bool(request, "prefer_local"),
            event_hook=event_hook,
        )
    else:
        raise RuntimeError(f"engine_orchestrator_selector_unknown:{selector_type}")
    if (
        allow_prompt
        and not request.confirm_swap
        and (resolved or {}).get("status") == "need_confirmation"
    ):
        if event_hook is not None:
            result = event_hook("waiting_hitl", dict(resolved or {}))
            if hasattr(result, "__await__"):
                await result
        decision = await ask_resource_swap_confirmation(
            request=request,
            resolved=dict(resolved or {}),
        )
        if not decision.ok:
            return {
                "status": "error",
                "error": resource_swap_error(decision.error),
            }
        if decision.action != "approve":
            return {
                "status": "error",
                "error": "engine_resource_swap_denied",
            }
        request.confirm_swap = True
        return await resolve_provider_result(
            request,
            allow_prompt=False,
            event_hook=event_hook,
        )
    return resolved


def validate_selector(request: Any) -> dict[str, Any]:
    selector_type = request.selector_type
    from democrai.core.application.ai.orchestrator import model_orchestrator

    if selector_type == "model_registry_id":
        model_registry_id = to_int_or_zero(request.model_registry_id)
        model = model_orchestrator.get_model_by_registry_id(model_registry_id)
        if model is None:
            raise RuntimeError(f"model_registry_row_not_found:{model_registry_id}")
        engine = getattr(model, "engine", None)
        provider_id = getattr(engine, "provider", None)
        if not provider_id:
            raise RuntimeError(f"model_registry_engine_not_found:{model_registry_id}")
        if getattr(model, "status", None) != "active":
            raise RuntimeError(f"model_registry_row_not_active:{model_registry_id}")
        if getattr(engine, "status", None) != "active":
            raise RuntimeError(
                f"engine_registry_row_not_active:{getattr(engine, 'id', '-')}"
            )
        return {
            "status": "ok",
            "selector_type": selector_type,
            "model_registry_id": model.id,
            "engine": provider_id,
        }
    if selector_type in {"objective", "capability"}:
        capabilities = json_loads(request.capabilities_json, [])
        if not isinstance(capabilities, list):
            raise RuntimeError("engine_orchestrator_capabilities_list_required")
        objective = request.objective or request.capability
        if not objective:
            raise RuntimeError("engine_orchestrator_objective_required")
        model = model_orchestrator.get_model_for_objective(
            objective,
            required_capabilities=[
                item for item in capabilities if item
            ],
            prefer_local=optional_bool(request, "prefer_local"),
        )
        if model is None:
            raise RuntimeError(f"no_model_configured_for_objective:{objective}")
        engine = getattr(model, "engine", None)
        return {
            "status": "ok",
            "selector_type": selector_type,
            "model_registry_id": model.id,
            "engine": getattr(engine, "provider", None),
        }
    raise RuntimeError(f"engine_orchestrator_selector_unknown:{selector_type}")


def optional_bool(message: Any, field_name: str) -> bool | None:
    has_field = getattr(message, "HasField", None)
    if callable(has_field):
        try:
            if not has_field(field_name):
                return None
        except ValueError:
            return bool(getattr(message, field_name))
    value = getattr(message, field_name, None)
    return None if value is None else bool(value)


def provider_unavailable_error(resolved: Any) -> str:
    payload = dict(resolved or {}) if isinstance(resolved, dict) else {}
    error = payload.get("error", "")
    if error:
        return error
    status = payload.get("status") or "unknown"
    details = {
        key: payload.get(key)
        for key in ("model_to_load", "to_unload", "model_registry_id", "engine")
        if payload.get(key) is not None
    }
    if details:
        return (
            "engine_orchestrator_provider_unavailable:"
            f"status={status}:details={json.dumps(json_value(details), ensure_ascii=True)}"
        )
    return f"engine_orchestrator_provider_unavailable:status={status}"


async def ask_resource_swap_confirmation(*, request: Any, resolved: dict[str, Any]):
    from democrai.core.application.auth.roles import ACCESS_LEVEL_FULL
    from democrai.core.application.runtime_prompt.grpc.client import RuntimePromptClient

    to_unload = resolved.get("to_unload") or []
    has_candidates = bool(to_unload)
    question = (
        "The requested model requires unloading active models. Continue?"
        if has_candidates
        else "Insufficient resources were reported and no unload candidates are available. Try loading anyway?"
    )
    actions = (
        [
            {"id": "approve", "label": "Unload and continue"},
            {"id": "deny", "label": "Cancel"},
        ]
        if has_candidates
        else [
            {"id": "approve", "label": "Try loading anyway"},
            {"id": "deny", "label": "Cancel"},
        ]
    )
    client = RuntimePromptClient()
    try:
        metadata = {
            "kind": "engine_resource_swap",
            "model_to_load": resolved.get("model_to_load"),
            "to_unload": to_unload,
        }
        async with ai_pipeline_step(
            type="runtime_prompt",
            name="engine_resource_swap",
            input={
                "question": question,
                "actions": [dict(action) for action in actions],
                "metadata": metadata,
            },
        ) as step:
            decision = await client.ask(
                question=question,
                actions=actions,
                required_role="super",
                required_access_level=ACCESS_LEVEL_FULL,
                request_context=json_loads(request.request_context_json, {}),
                metadata=metadata,
            )
            if isinstance(step, dict):
                step["output"] = {
                    "ok": bool(decision.ok),
                    "action": decision.action,
                    "error": decision.error,
                    "prompt_id": decision.prompt_id,
                }
                if not decision.ok:
                    step["status"] = "error"
                elif decision.action != "approve":
                    step["status"] = "denied"
            return decision
    finally:
        await client.close()


def resource_swap_error(error: str | None) -> str:
    value = error or ""
    if value == "runtime_prompt_denied":
        return "engine_resource_swap_denied"
    if value == "runtime_prompt_timeout":
        return "engine_resource_swap_confirmation_timeout"
    if value == "runtime_prompt_forbidden":
        return "engine_resource_swap_forbidden"
    if value in {
        "runtime_prompt_session_required",
        "runtime_prompt_user_required",
        "runtime_prompt_no_active_connection",
    }:
        return "engine_resource_swap_confirmation_unavailable"
    return value or "engine_resource_swap_confirmation_unavailable"
