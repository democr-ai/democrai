from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, Field, field_validator

from democrai.sdk.ai_constants import AICapability
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action, validate

from modules.system.utils.actions.engine.model_test_support import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    _completion_tokens_per_second,
    _response_text,
    _response_usage,
    _test_result,
)
from modules.system.utils.actions.datatable import (
    datatable_payload,
    datatable_remote_request,
    datatable_response,
    datatable_update_effects,
)

TABLE_ID = "system_mcp_servers_table"


class McpTestFormPayload(BaseModel):
    model_row_id: int = Field(gt=0)
    prompt: str = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def _clean_prompt(cls, value: str) -> str:
        prompt = value.strip()
        if not prompt:
            raise ValueError("prompt is required")
        return prompt


class McpTestPayload(BaseModel):
    mcp_id: int
    system_mcp_test_form: McpTestFormPayload


def _json_config(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    parsed = json.loads(str(value))
    if not isinstance(parsed, dict):
        raise ValueError("mcp_config_must_be_json_object")
    return parsed


def _payload(ctx: dict[str, Any]) -> dict[str, Any]:
    payload = dict(ctx[str(ctx["form_id"])])
    payload["config"] = _json_config(payload.get("config"))
    return payload


def _toast(module_sdk, variant: str, key: str) -> dict[str, Any]:
    return module_sdk.effects.notify(
        "toast",
        {
            "title": module_sdk.i18n.t("system.mcp.title"),
            "variant": variant,
            "text": module_sdk.i18n.t(key),
            "duration": 2400,
        },
    )


def _table_payload(module_sdk, ctx: dict[str, Any]) -> dict[str, Any]:
    page, page_size, filters, sort = datatable_remote_request(ctx)
    listing = module_sdk.models.mcp_server_registry.list(
        page=page,
        page_size=page_size,
        filters=filters,
        sort=sort,
    )
    return datatable_payload(
        listing,
        page=page,
        page_size=page_size,
        filters=filters,
    )


def _table_response(module_sdk, ctx: dict[str, Any]):
    payload = _table_payload(module_sdk, ctx)
    return datatable_response(module_sdk, TABLE_ID, payload)


def _mcp_test_state_update(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "stateUpdate": {
            "scope": "page",
            "values": {
                "/system/mcp/test/last_result": result,
                "/system/mcp/test/last_status": str(result.get("status") or ""),
                "/system/mcp/test/trace_events": list(
                    result.get("trace_events") or []
                ),
            },
        }
    }


def _mcp_test_response(module_sdk, result: dict[str, Any], *, error: Exception | None = None):
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([_mcp_test_state_update(result)]),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "error" if error is not None else "success",
                "message": (
                    str(error)
                    if error is not None
                    else module_sdk.i18n.t("system.mcp.test.completed")
                ),
            },
        ),
    )


def _event_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _mcp_pipeline_message_entry(message: Any) -> dict[str, str]:
    event_type = str(
        getattr(message, "type", "")
        or (message.get("type") if isinstance(message, dict) else "")
        or "pipeline.message"
    ).strip()
    name = str(
        getattr(message, "name", "")
        or (message.get("name") if isinstance(message, dict) else "")
        or ""
    ).strip()
    status = str(
        getattr(message, "status", "")
        or (message.get("status") if isinstance(message, dict) else "")
        or ""
    ).strip()
    payload = (
        getattr(message, "payload", None)
        if not isinstance(message, dict)
        else message.get("payload")
    )
    title = event_type
    if name:
        title = f"{title} | {name}"
    if status:
        title = f"{title} | {status}"
    return {"title": title, "text": _event_value(payload) or "-"}


@action("list_mcp_servers")
@permission_required(["system.engine.model.manage"])
async def list_mcp_servers(ctx: dict[str, Any], session: dict, module_sdk):
    return _table_response(module_sdk, ctx)


@action("save_mcp_server")
@permission_required(["system.engine.model.manage"])
async def save_mcp_server(ctx: dict[str, Any], session: dict, module_sdk):
    entity_id = ctx["id"]
    try:
        if entity_id == "new":
            module_sdk.models.mcp_server_registry.create(_payload(ctx))
        else:
            module_sdk.models.mcp_server_registry.update(int(entity_id), _payload(ctx))
    except Exception as exc:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("system.mcp.title"),
                    "variant": "error",
                    "text": str(exc),
                    "duration": 2400,
                },
            )
        )
    return module_sdk.effects.respond(
        _toast(module_sdk, "success", "system.mcp.toast.saved"),
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
        module_sdk.effects.render(),
    )


@action("delete_mcp_server")
@permission_required(["system.engine.model.manage"])
async def delete_mcp_server(ctx: dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    entity_id = item["id"]
    try:
        module_sdk.models.mcp_server_registry.delete(int(entity_id))
    except Exception as exc:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("system.mcp.title"),
                    "variant": "error",
                    "text": str(exc),
                    "duration": 2400,
                },
            )
        )
    payload = _table_payload(module_sdk, ctx)
    return module_sdk.effects.respond(
        _toast(module_sdk, "success", "system.mcp.toast.deleted"),
        *datatable_update_effects(module_sdk, TABLE_ID, payload),
    )


@action("test_mcp_with_llm")
@validate(McpTestPayload, strip_extra=True)
@permission_required(["system.engine.model.manage"])
async def test_mcp_with_llm(ctx: dict[str, Any], module_sdk):
    try:
        payload = ctx["system_mcp_test_form"]
        mcp_id = ctx["mcp_id"]
        model_row_id = payload["model_row_id"]
        prompt = payload["prompt"]

        mcp = module_sdk.models.mcp_server_registry.view(mcp_id)
        if not isinstance(mcp, dict):
            raise ValueError("mcp_not_found")
        if not bool(mcp.get("enabled")):
            raise ValueError("mcp_not_enabled")
        mcp_name = str(mcp.get("name") or "").strip()
        enabled_mcp_names = {
            str(getattr(server, "name", "") or "").strip()
            for server in module_sdk.ai.list_mcp_servers()
        }
        if mcp_name not in enabled_mcp_names:
            raise ValueError("mcp_not_available")

        model = module_sdk.models.model_registry.view(model_row_id)
        if not isinstance(model, dict):
            raise ValueError("model_not_found")
        if AICapability.TOOL_CALLING not in list(model.get("capabilities") or []):
            raise ValueError("model_without_tool_calling")

        provider_result = await module_sdk.ai.get_provider_by_model_registry_id(model_row_id)
        if provider_result.get("status") != "ok" or not provider_result.get("provider"):
            message = str(provider_result.get("error") or "provider_unavailable")
            result = _test_result(
                status="error",
                method="mcp",
                output=message,
            )
            return _mcp_test_response(module_sdk, result, error=RuntimeError(message))

        provider = provider_result["provider"]
        warmup = await module_sdk.ai.warmup_provider(provider, wait=True)
        warmup_ms = warmup.get("warmup_ms")
        if warmup.get("status") != "ok":
            message = str(warmup.get("error") or "provider_warmup_failed")
            result = _test_result(
                status="error",
                method="mcp",
                output=message,
                warmup_ms=warmup_ms,
            )
            return _mcp_test_response(module_sdk, result, error=RuntimeError(message))
        trace_events: list[dict[str, str]] = []
        stream_id = str(ctx.get("stream_id") or "").strip()

        async def _append_trace_entry(entry: dict[str, str]) -> None:
            trace_events.append(entry)
            if stream_id:
                await module_sdk.effects.publish_state_patch(
                    stream_id,
                    "/system/mcp/test/trace_events",
                    "append",
                    entry,
                    scope="page",
                )

        async def _on_message(message: Any) -> None:
            await _append_trace_entry(_mcp_pipeline_message_entry(message))

        if stream_id:
            await module_sdk.effects.publish_state_patch(
                stream_id,
                "/system/mcp/test/trace_events",
                "set",
                [],
                scope="page",
            )
        run_started = time.perf_counter()
        response = await provider.generate_completion(
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": DEFAULT_TEMPERATURE,
                "top_p": DEFAULT_TOP_P,
                "mcp": [mcp_name],
                "tool_choice": "auto",
            },
            on_message=_on_message,
        )
        duration_ms = round((time.perf_counter() - run_started) * 1000.0, 2)
        usage = _response_usage(response)
        completion_tokens = usage.get("completion_tokens")
        output = _response_text(response)
        tool_call_count = len(getattr(response, "tool_calls", None) or [])
        if not output:
            output = f"tool_calls={tool_call_count}"
        result = _test_result(
            status="ok",
            method="mcp",
            output=output,
            warmup_ms=warmup_ms,
            duration_ms=duration_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=completion_tokens,
            total_tokens=usage.get("total_tokens"),
            tokens_per_second=_completion_tokens_per_second(
                completion_tokens,
                duration_ms,
            ),
            resources={"mcp": mcp_name, "model_row_id": model_row_id},
        )
        result["trace_events"] = trace_events
        return _mcp_test_response(module_sdk, result)
    except Exception as exc:
        result = _test_result(status="error", method="mcp", output=str(exc))
        if "trace_events" in locals():
            result["trace_events"] = trace_events
            result.setdefault("resources", {})["trace_events"] = trace_events
        return _mcp_test_response(module_sdk, result, error=exc)
