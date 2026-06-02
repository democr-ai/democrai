from __future__ import annotations

import json
import uuid
from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.ai_constants import AI_CONTEXT_POLICIES
from democrai.sdk.decorators import action
from democrai.sdk.media import media_type_from_content_type
from modules.system.utils.actions.engine.model_test_support import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    _nested_payload_value,
    _optional_int_value,
    _payload_has_path,
    _performance_stats,
    _runtime_field_names,
    _set_nested_value,
)


RESULT_COLUMN_ID = "engine_model_test_generate_completion_result"
COMPOSER_ID = "engine_model_test_generate_completion_composer"


def _provider_error_payload(
    *,
    method: str,
    model_row_id: int,
    provider_result: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "method": method,
        "model_row_id": model_row_id,
        "status": "error",
    }
    if provider_result is not None:
        payload["provider_status"] = str(provider_result.get("status") or "")
        payload["provider_error"] = str(
            provider_result.get("error") or "provider_unavailable"
        )
        if provider_result.get("model_to_load") is not None:
            payload["model_to_load"] = provider_result.get("model_to_load")
        if provider_result.get("to_unload") is not None:
            payload["to_unload"] = provider_result.get("to_unload")
    if error is not None:
        payload["exception_type"] = type(error).__name__
        payload["exception"] = str(error)
    return payload


async def _append_provider_error(
    module_sdk,
    *,
    stream_id: str,
    method: str,
    model_row_id: int,
    provider_result: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> str:
    payload = _provider_error_payload(
        method=method,
        model_row_id=model_row_id,
        provider_result=provider_result,
        error=error,
    )
    message = str(
        payload.get("exception")
        or payload.get("provider_error")
        or "provider_unavailable"
    )
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_{method}_provider_error_{uuid.uuid4().hex}",
            f"{method} provider error",
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            open=True,
        ).to_dict(),
    )
    return message


def _context_policy(value: Any) -> str:
    policy = str(value or "").strip()
    if policy and policy not in set(AI_CONTEXT_POLICIES):
        raise ValueError("invalid_context_policy")
    return policy


def _updated_generation(current: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    updated = dict(current)
    if "temperature" in payload:
        updated["temperature"] = (
            DEFAULT_TEMPERATURE
            if payload["temperature"] in (None, "")
            else float(payload["temperature"])
        )
    if "top_p" in payload:
        updated["top_p"] = (
            DEFAULT_TOP_P if payload["top_p"] in (None, "") else float(payload["top_p"])
        )
    if "top_k" in payload:
        updated["top_k"] = _optional_int_value(payload["top_k"])
    if "max_tokens" in payload:
        updated["max_tokens"] = _optional_int_value(payload["max_tokens"])
    for key, value in payload.items():
        if str(key).startswith("extra."):
            _set_nested_value(updated, str(key), value)
    return updated


def _updated_runtime(
    current: dict[str, Any],
    payload: dict[str, Any],
    runtime_options_schema: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(current)
    if "context_length" in payload:
        updated["context_length"] = _optional_int_value(payload["context_length"])
        updated.pop("n_ctx", None)
        updated.pop("max_model_len", None)
        updated.pop("num_ctx", None)
    if "context_policy" in payload:
        policy = _context_policy(payload.get("context_policy"))
        if policy:
            updated["context_policy"] = policy
        else:
            updated.pop("context_policy", None)
    for field_name in _runtime_field_names(runtime_options_schema):
        if _payload_has_path(payload, field_name):
            updated[field_name] = _nested_payload_value(payload, field_name)
    return updated


@action("save_engine_model_generate_completion_params")
@permission_required(["system.engine.model.manage"])
async def save_engine_model_generate_completion_params(ctx: dict[str, Any], session: dict, module_sdk):
    row_id = int(ctx["model_row_id"])
    row = module_sdk.models.model_registry.view(row_id)
    if not isinstance(row, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())

    extra_config = dict(row["extra_config"] or {})
    defaults = dict(extra_config.get("defaults") or {})
    available_model = dict(extra_config.get("available_model") or {})
    available_runtime = dict(available_model.get("runtime") or {})
    payload = ctx[str(ctx["form_id"])]
    updated_generation = _updated_generation(
        dict(defaults.get("generation") or {}),
        payload,
    )
    updated_runtime = _updated_runtime(
        dict(defaults.get("runtime") or {}),
        payload,
        dict(available_runtime.get("options_schema") or {}),
    )
    test_results = dict(extra_config.get("test_results") or {})
    generate_completion_result = dict(test_results.get("generate_completion") or {})
    generate_completion_result.pop("output", None)
    generate_completion_result.pop("resources", None)
    if generate_completion_result:
        test_results["generate_completion"] = generate_completion_result
    else:
        test_results.pop("generate_completion", None)
    updated_extra_config = {
        **extra_config,
        "defaults": {
            **defaults,
            "generation": updated_generation,
            "runtime": updated_runtime,
        },
    }
    if test_results:
        updated_extra_config["test_results"] = test_results
    module_sdk.models.model_registry.update(
        row_id,
        {"extra_config": updated_extra_config},
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success",
                "message": "parameters saved",
            },
        ),
        module_sdk.effects.render(),
    )


@action("test_engine_model_generate_completion")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_generate_completion(ctx: dict[str, Any], module_sdk):
    payload = ctx.get(COMPOSER_ID)
    if not isinstance(payload, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())

    row_id = ctx["model_row_id"]
    if not isinstance(row_id, int):
        raise ValueError("model_row_id_required")
    text = payload["text"]
    attachments = payload["attachments"]
    option_entries = payload["options"]
    selected_tools = payload["selected_tools"]
    selected_skills = payload["selected_skills"]
    selected_mcp = payload["selected_mcp"]
    stream_id = ctx["stream_id"]
    await module_sdk.effects.publish_property_update(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        [],
        action="set",
    )
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_generate_completion_submitted_{uuid.uuid4().hex}",
            "request submitted",
            json.dumps(
                {"method": "generate_completion", "status": "waiting_provider"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            open=False,
        ).to_dict(),
    )
    await module_sdk.effects.publish_ui_message(
        stream_id,
        {
            "stateUpdate": {
                "scope": "page",
                "values": {
                    "/engine_model_test/generate_completion_current_request": "",
                    "/engine_model_test/last_status": "running",
                },
            }
        },
    )
    content = [{"type": "text", "text": text}]
    for attachment in attachments:
        content_type = attachment["content_type"]
        content.append(
            {
                "type": media_type_from_content_type(content_type),
                "mime_type": content_type,
                "storage_path": attachment["storage_path"],
            }
        )
    options = {}
    for item in option_entries:
        key = str(item["key"])
        if key.startswith("extra."):
            _set_nested_value(options, key, item["value"])
        else:
            options[key] = item["value"]
    is_dev = getattr(getattr(module_sdk, "system", None), "is_dev", None)
    if callable(is_dev) and is_dev():
        print(
            "[ENGINE_MODEL_TEST] generate_completion.options | "
            + json.dumps(
                {
                    "option_entries": option_entries,
                    "options": options,
                },
                ensure_ascii=False,
                default=str,
            ),
            flush=True,
        )
    messages = [{"role": "user", "content": content}]
    try:
        provider_result = await module_sdk.ai.get_provider_by_model_registry_id(row_id)
    except Exception as exc:
        message = await _append_provider_error(
            module_sdk,
            stream_id=stream_id,
            method="generate_completion",
            model_row_id=row_id,
            error=exc,
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                [
                    {
                        "stateUpdate": {
                            "scope": "page",
                            "values": {
                                "/engine_model_test/generate_completion_current_request": "",
                                "/engine_model_test/last_status": "error",
                            },
                        }
                    }
                ]
            ),
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": message},
            ),
        )
    if provider_result.get("status") != "ok" or not provider_result.get("provider"):
        message = await _append_provider_error(
            module_sdk,
            stream_id=stream_id,
            method="generate_completion",
            model_row_id=row_id,
            provider_result=provider_result,
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                [
                    {
                        "stateUpdate": {
                            "scope": "page",
                            "values": {
                                "/engine_model_test/generate_completion_current_request": "",
                                "/engine_model_test/last_status": "error",
                            },
                        }
                    }
                ]
            ),
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": message},
            ),
        )
    provider = provider_result["provider"]
    try:
        await module_sdk.ai.warmup_provider(provider, wait=True)
    except Exception as exc:
        message = await _append_provider_error(
            module_sdk,
            stream_id=stream_id,
            method="generate_completion",
            model_row_id=row_id,
            error=exc,
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                [
                    {
                        "stateUpdate": {
                            "scope": "page",
                            "values": {
                                "/engine_model_test/generate_completion_current_request": "",
                                "/engine_model_test/last_status": "error",
                            },
                        }
                    }
                ]
            ),
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": message},
            ),
        )
    options["tools"] = selected_tools
    options["skills"] = selected_skills
    options["mcp"] = selected_mcp
    request_context = {}
    try:
        response = await provider.generate_completion(
            messages=messages,
            options=options,
            on_response=_publish_generate_completion_result(
                module_sdk,
                stream_id=stream_id,
                status="ok",
                request_context=request_context,
            ),
            on_error=_publish_generate_completion_result(
                module_sdk,
                stream_id=stream_id,
                status="error",
                request_context=request_context,
            ),
            on_message=_publish_generate_completion_message(
                module_sdk,
                stream_id=stream_id,
            ),
        )
    except Exception as exc:
        message = await _append_provider_error(
            module_sdk,
            stream_id=stream_id,
            method="generate_completion",
            model_row_id=row_id,
            error=exc,
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                [
                    {
                        "stateUpdate": {
                            "scope": "page",
                            "values": {
                                "/engine_model_test/generate_completion_current_request": "",
                                "/engine_model_test/last_status": "error",
                            },
                        }
                    }
                ]
            ),
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": message},
            ),
        )
    request_context["pipeline_id"] = str(getattr(response, "pipeline_id", "") or "")
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_model_test/generate_completion_current_request": response.id,
                            "/engine_model_test/last_status": "running",
                        },
                    }
                }
            ]
        )
    )


@action("stop_engine_model_generate_completion")
@permission_required(["system.engine.model.manage"])
async def stop_engine_model_generate_completion(ctx: dict[str, Any], module_sdk):
    payload = ctx[COMPOSER_ID]
    request_id = payload["current_request"]
    module_sdk.ai.cancel_request(request_id)
    stream_id = ctx["stream_id"]
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.MessageItem(
            f"engine_model_test_generate_completion_cancelled_{uuid.uuid4().hex}",
            role="system",
            text="request cancelled",
            meta="generate_completion cancelled",
        ).to_dict(),
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_model_test/generate_completion_current_request": "",
                            "/engine_model_test/last_status": "cancelled",
                        },
                    }
                }
            ]
        )
    )


def _publish_generate_completion_result(
    module_sdk,
    *,
    status: str,
    stream_id: str,
    request_context: dict[str, Any],
) -> Any:
    async def _publish(value: Any) -> None:
        await module_sdk.effects.publish_collection_append(
            stream_id,
            RESULT_COLUMN_ID,
            "children",
            _performance_card(module_sdk, status=status, value=value).to_dict(),
        )
        pipeline_id = str(
            getattr(value, "pipeline_id", None)
            or request_context.get("pipeline_id")
            or ""
        )
        await module_sdk.effects.publish_collection_append(
            stream_id,
            RESULT_COLUMN_ID,
            "children",
            _pipeline_steps_table(module_sdk, pipeline_id).to_dict(),
        )
        await module_sdk.effects.publish_collection_append(
            stream_id,
            RESULT_COLUMN_ID,
            "children",
            _result_card(module_sdk, status=status, value=value).to_dict(),
        )
        await module_sdk.effects.publish_ui_message(
            stream_id,
            {
                "stateUpdate": {
                    "scope": "page",
                    "values": {
                        "/engine_model_test/last_status": status,
                        "/engine_model_test/generate_completion_current_request": "",
                    },
                }
            },
        )

    return _publish


def _publish_generate_completion_message(
    module_sdk,
    *,
    stream_id: str,
) -> Any:
    async def _publish(message: Any) -> None:
        await module_sdk.effects.publish_collection_append(
            stream_id,
            RESULT_COLUMN_ID,
            "children",
            _message_card(module_sdk, message).to_dict(),
        )

    return _publish


def _message_card(module_sdk, message: Any):
    label = _message_label(message)
    body = json.dumps(message.payload, ensure_ascii=False, sort_keys=True)
    item_id = f"engine_model_test_pipeline_message_{uuid.uuid4().hex}"
    return module_sdk.ui.Collapsible(
        item_id,
        label,
        body,
        open=False,
    )


def _message_label(message: Any) -> str:
    event_type = str(message.type or "")
    labels = {
        "skill.resolve.started": "skill selection started",
        "skill.resolve.finished": "skill selection finished",
        "skill.injected.started": "skill context injection started",
        "skill.injected.finished": "skill context injection finished",
        "skill.execution.started": "skill execution started",
        "skill.execution.finished": "skill execution finished",
        "tool.call": "tool call",
        "tool.result": "tool result",
        "agent.call": "agent call",
        "agent.response": "agent response",
        "agent.failed": "agent failed",
        "agent.pipeline.started": "agent pipeline started",
        "agent.pipeline.finished": "agent pipeline finished",
        "llm.request": "llm request",
        "llm.response": "llm response",
        "engine.call.started": "engine call started",
        "engine.call.finished": "engine call finished",
        "request.finished": "request finished",
    }
    label = labels.get(event_type, event_type)
    if message.status:
        label = f"{label} ({message.status})"
    if message.name:
        label = f"{label}: {message.name}"
    return label


def _result_card(module_sdk, *, status: str, value: Any):
    item_id = f"engine_model_test_generate_completion_{status}_{uuid.uuid4().hex}"
    output = str(value) if status == "error" else _response_content(value)
    return module_sdk.ui.MessageItem(
        item_id,
        role="assistant" if status == "ok" else "system",
        text=output or "",
        reasoning=_response_reasoning(value),
        meta=f"generate_completion {status}",
    )


def _response_content(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("content") or "")
    return str(getattr(value, "content", None) or "")


def _response_reasoning(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("reasoning") or "")
    return str(getattr(value, "reasoning", None) or "")


def _performance_card(module_sdk, *, status: str, value: Any):
    usage = getattr(value, "usage", None)
    payload = _performance_stats(
        status=status,
        method="generate_completion",
        token_input=getattr(usage, "prompt_tokens", None) if usage else None,
        token_output=getattr(usage, "completion_tokens", None) if usage else None,
        token_total=getattr(usage, "total_tokens", None) if usage else None,
        tps=getattr(value, "tokens_per_second", None),
        request_id=getattr(value, "request_id", ""),
        pipeline_id=getattr(value, "pipeline_id", ""),
        finish_reason=getattr(value, "finish_reason", ""),
        reasoning_chars=len(_response_reasoning(value)),
    )
    return module_sdk.ui.Collapsible(
        f"engine_model_test_generate_completion_performance_{uuid.uuid4().hex}",
        "performance statistics",
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        open=False,
    )


def _pipeline_steps_table(module_sdk, pipeline_id: str):
    resolved_pipeline_id = str(pipeline_id or "").strip()
    rows = []
    if resolved_pipeline_id:
        result = module_sdk.models.ai_model_pipeline_steps.all(
            filters={"pipeline_id": resolved_pipeline_id},
            sort={"field": "timestamp", "direction": "asc"},
        )
        rows = result["rows"]
    return module_sdk.ui.DataTable(
        f"engine_model_test_generate_completion_pipeline_steps_{uuid.uuid4().hex}",
        model=module_sdk.models.ai_model_pipeline_steps.table_model(),
        rows=rows,
        paginated=False,
    )
