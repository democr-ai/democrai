from __future__ import annotations

import json
import uuid
from typing import Any


RESULT_COLUMN_ID = "engine_model_test_generate_completion_result"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="python"))
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


async def clear_structured_result(module_sdk, stream_id: str) -> None:
    await module_sdk.effects.publish_property_update(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        [],
        action="set",
    )


async def append_structured_trace(
    module_sdk,
    stream_id: str,
    *,
    method: str,
    label: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_{method}_trace_{uuid.uuid4().hex}",
            label,
            json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True),
            open=False,
        ).to_dict(),
    )


async def append_structured_error(
    module_sdk,
    stream_id: str,
    *,
    method: str,
    message: str,
) -> None:
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Alert(
            f"engine_model_test_{method}_error_{uuid.uuid4().hex}",
            title=f"{method} error",
            description=message,
            variant="danger",
        ).to_dict(),
    )


async def append_structured_success(
    module_sdk,
    stream_id: str,
    *,
    method: str,
    result_label: str,
    result: Any,
    stats: dict[str, Any],
    extra_stats: dict[str, Any] | None = None,
) -> None:
    payload = {"status": "ok", "method": method, **dict(stats or {})}
    payload.update({key: value for key, value in dict(extra_stats or {}).items() if value is not None})
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_{method}_performance_{uuid.uuid4().hex}",
            "performance statistics",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            open=False,
        ).to_dict(),
    )
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_{method}_result_{uuid.uuid4().hex}",
            result_label,
            json.dumps(_jsonable(result), ensure_ascii=False, sort_keys=True, indent=2),
            open=True,
        ).to_dict(),
    )


async def update_structured_status(module_sdk, stream_id: str, status: str) -> None:
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
