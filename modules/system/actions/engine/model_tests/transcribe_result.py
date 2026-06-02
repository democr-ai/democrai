from __future__ import annotations

import json
import uuid
from typing import Any


RESULT_COLUMN_ID = "engine_model_test_generate_completion_result"


async def clear_transcribe_result(module_sdk, stream_id: str) -> None:
    await module_sdk.effects.publish_property_update(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        [],
        action="set",
    )


async def append_transcribe_trace(
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
            f"engine_model_test_transcribe_trace_{uuid.uuid4().hex}",
            label,
            json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True),
            open=False,
        ).to_dict(),
    )


async def append_transcribe_error(
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
            f"engine_model_test_transcribe_error_{uuid.uuid4().hex}",
            title="transcribe error",
            description=message,
            variant="danger",
        ).to_dict(),
    )


async def append_transcribe_success(
    module_sdk,
    stream_id: str,
    *,
    text: str,
    language: str,
    audio_bytes: int,
    audio_duration_seconds: float | None,
    stats: dict[str, Any],
) -> None:
    payload = {"status": "ok", "method": "transcribe", **dict(stats or {})}
    payload.update(
        {
            "audio_bytes": audio_bytes,
            "audio_duration_seconds": audio_duration_seconds,
            "language": language,
        }
    )
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_transcribe_performance_{uuid.uuid4().hex}",
            "performance statistics",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            open=False,
        ).to_dict(),
    )
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Text(
            f"engine_model_test_transcribe_output_{uuid.uuid4().hex}",
            text or "",
        ).to_dict(),
    )


async def update_transcribe_status(module_sdk, stream_id: str, status: str) -> None:
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
