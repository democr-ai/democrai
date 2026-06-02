from __future__ import annotations

import json
import uuid
from typing import Any


RESULT_COLUMN_ID = "engine_model_test_generate_completion_result"


async def clear_synthesize_result(module_sdk, stream_id: str) -> None:
    await module_sdk.effects.publish_property_update(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        [],
        action="set",
    )


async def append_synthesize_trace(
    module_sdk,
    stream_id: str,
    *,
    label: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_synthesize_trace_{uuid.uuid4().hex}",
            label,
            json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True),
            open=False,
        ).to_dict(),
    )


async def append_synthesize_error(
    module_sdk,
    stream_id: str,
    *,
    message: str,
) -> None:
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Alert(
            f"engine_model_test_synthesize_error_{uuid.uuid4().hex}",
            title="synthesize error",
            description=message,
            variant="danger",
        ).to_dict(),
    )


async def append_synthesize_success(
    module_sdk,
    stream_id: str,
    *,
    method: str = "synthesize",
    audio_source: str,
    content_type: str,
    audio_bytes: int,
    prompt_chars: int,
    duration_seconds: float | None,
    stats: dict[str, Any],
    stream_chunks: int | None = None,
) -> None:
    payload = {"status": "ok", "method": method, **dict(stats or {})}
    payload.update(
        {
            "prompt_chars": prompt_chars,
            "audio_bytes": audio_bytes,
            "audio_duration_seconds": duration_seconds,
            "content_type": content_type,
            "stream_chunks": stream_chunks,
        }
    )
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        _performance_card(
            module_sdk,
            payload=payload,
        ).to_dict(),
    )
    if audio_source:
        await module_sdk.effects.publish_collection_append(
            stream_id,
            RESULT_COLUMN_ID,
            "children",
            module_sdk.ui.Audio(
                f"engine_model_test_synthesize_audio_{uuid.uuid4().hex}",
                source=audio_source,
                title="synthesize output",
                autoplay=True,
                controls=True,
                width=640,
                height=140,
            ).to_dict(),
        )


async def update_synthesize_status(module_sdk, stream_id: str, status: str) -> None:
    await module_sdk.effects.publish_ui_message(
        stream_id,
        {
            "stateUpdate": {
                "scope": "page",
                "values": {
                    "/engine_model_test/last_status": status,
                },
            }
        },
    )


def _performance_card(
    module_sdk,
    *,
    payload: dict[str, Any],
):
    return module_sdk.ui.Collapsible(
        f"engine_model_test_synthesize_performance_{uuid.uuid4().hex}",
        "performance statistics",
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        open=False,
    )
