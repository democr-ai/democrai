from __future__ import annotations

import json
import uuid
from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action
from democrai.sdk.media import media_type_from_content_type
from modules.system.actions.engine.model_tests.generate_completion import (
    RESULT_COLUMN_ID,
    _append_provider_error,
    _message_card,
    _pipeline_steps_table,
)
from modules.system.utils.actions.engine.model_test_support import (
    _optional_int_value,
    _set_nested_value,
    _stream_chunk_text,
)


COMPOSER_ID = "engine_model_test_generate_stream_composer"


def _chunk_reasoning(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, dict):
        return str(chunk.get("reasoning") or "")
    return str(getattr(chunk, "reasoning", None) or "")


def _chunk_stats(chunk: Any) -> dict[str, Any] | None:
    stats = chunk.get("stats") if isinstance(chunk, dict) else getattr(chunk, "stats", None)
    return dict(stats) if isinstance(stats, dict) else None


def _options(option_entries: list[dict[str, Any]]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for item in option_entries:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        if key.startswith("extra."):
            _set_nested_value(options, key, item.get("value"))
        else:
            options[key] = item.get("value")
    if "max_tokens" in options:
        options["max_tokens"] = _optional_int_value(options["max_tokens"])
    if "top_k" in options:
        options["top_k"] = _optional_int_value(options["top_k"])
    return options


def _messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    content = [{"type": "text", "text": str(payload["text"] or "")}]
    for attachment in list(payload.get("attachments") or []):
        content_type = attachment["content_type"]
        content.append(
            {
                "type": media_type_from_content_type(content_type),
                "mime_type": content_type,
                "storage_path": attachment["storage_path"],
            }
        )
    return [{"role": "user", "content": content}]


async def _publish_provider_error(
    module_sdk,
    *,
    stream_id: str,
    model_row_id: int,
    provider_result: dict[str, Any],
):
    message = await _append_provider_error(
        module_sdk,
        stream_id=stream_id,
        method="generate_stream",
        model_row_id=model_row_id,
        provider_result=provider_result,
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_model_test/generate_stream_current_request": "",
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


@action("test_engine_model_generate_stream")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_generate_stream(ctx: dict[str, Any], module_sdk):
    payload = ctx.get(COMPOSER_ID)
    if not isinstance(payload, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())

    row_id = ctx["model_row_id"]
    if not isinstance(row_id, int):
        raise ValueError("model_row_id_required")
    stream_id = str(ctx["stream_id"])
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
            f"engine_model_test_generate_stream_submitted_{uuid.uuid4().hex}",
            "request submitted",
            json.dumps(
                {"method": "generate_stream", "status": "waiting_provider"},
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
                    "/engine_model_test/generate_stream_current_request": "",
                    "/engine_model_test/last_status": "running",
                },
            }
        },
    )

    try:
        provider_result = await module_sdk.ai.get_provider_by_model_registry_id(row_id)
    except Exception as exc:
        message = await _append_provider_error(
            module_sdk,
            stream_id=stream_id,
            method="generate_stream",
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
                                "/engine_model_test/generate_stream_current_request": "",
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
        provider_result = {**provider_result, "model_row_id": row_id}
        return await _publish_provider_error(
            module_sdk,
            stream_id=stream_id,
            model_row_id=row_id,
            provider_result=provider_result,
        )
    provider = provider_result["provider"]
    try:
        await module_sdk.ai.warmup_provider(provider, wait=True)
    except Exception as exc:
        message = await _append_provider_error(
            module_sdk,
            stream_id=stream_id,
            method="generate_stream",
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
                                "/engine_model_test/generate_stream_current_request": "",
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
    options = _options(list(payload.get("options") or []))
    options["tools"] = payload.get("selected_tools") or []
    options["skills"] = payload.get("selected_skills") or []
    options["mcp"] = payload.get("selected_mcp") or []
    message_id = f"engine_model_test_generate_stream_message_{uuid.uuid4().hex}"
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.MessageItem(
            message_id,
            role="assistant",
            text="",
            meta="generate_stream running",
        ).to_dict(),
    )

    pipeline_id = ""
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    last_chunk = None
    chunk_count = 0
    stream_stats: dict[str, Any] = {}

    async def _on_message(message: Any) -> None:
        nonlocal pipeline_id
        if not pipeline_id:
            pipeline_id = str(getattr(message, "pipeline_id", "") or "")
        await module_sdk.effects.publish_collection_append(
            stream_id,
            RESULT_COLUMN_ID,
            "children",
            _message_card(module_sdk, message).to_dict(),
        )

    try:
        async for chunk in provider.generate_stream(
            messages=_messages(payload),
            options=options,
            on_message=_on_message,
        ):
            stats = _chunk_stats(chunk)
            if stats is not None:
                stream_stats = stats
                continue
            last_chunk = chunk
            chunk_count += 1
            text = _stream_chunk_text(chunk)
            reasoning = _chunk_reasoning(chunk)
            if text:
                text_parts.append(text)
                await module_sdk.effects.publish_property_update(
                    stream_id,
                    message_id,
                    "text",
                    "".join(text_parts),
                )
            if reasoning:
                reasoning_parts.append(reasoning)
                await module_sdk.effects.publish_property_update(
                    stream_id,
                    message_id,
                    "reasoning",
                    "".join(reasoning_parts),
                )
    except Exception as exc:
        await module_sdk.effects.publish_collection_append(
            stream_id,
            RESULT_COLUMN_ID,
            "children",
            module_sdk.ui.MessageItem(
                f"engine_model_test_generate_stream_error_{uuid.uuid4().hex}",
                role="system",
                text=str(exc),
                meta="generate_stream error",
            ).to_dict(),
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages(
                [
                    {
                        "stateUpdate": {
                            "scope": "page",
                            "values": {
                                "/engine_model_test/generate_stream_current_request": "",
                                "/engine_model_test/last_status": "error",
                            },
                        }
                    }
                ]
            )
        )

    payload_stats = {"status": "ok", "method": "generate_stream", **stream_stats}
    payload_stats["chunks"] = chunk_count
    payload_stats["reasoning_chars"] = len("".join(reasoning_parts))
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_generate_stream_performance_{uuid.uuid4().hex}",
            "performance statistics",
            json.dumps(payload_stats, ensure_ascii=False, sort_keys=True),
            open=False,
        ).to_dict(),
    )
    if pipeline_id:
        await module_sdk.effects.publish_collection_append(
            stream_id,
            RESULT_COLUMN_ID,
            "children",
            _pipeline_steps_table(module_sdk, pipeline_id).to_dict(),
        )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_model_test/generate_stream_current_request": "",
                            "/engine_model_test/last_status": "ok",
                        },
                    }
                }
            ]
        )
    )
