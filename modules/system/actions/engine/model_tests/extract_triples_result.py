from __future__ import annotations

import json
import uuid
from typing import Any


RESULT_COLUMN_ID = "engine_model_test_generate_completion_result"


async def clear_extract_triples_result(module_sdk, stream_id: str) -> None:
    await module_sdk.effects.publish_property_update(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        [],
        action="set",
    )


async def append_extract_triples_trace(
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
            f"engine_model_test_extract_triples_trace_{uuid.uuid4().hex}",
            label,
            json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True),
            open=False,
        ).to_dict(),
    )


async def append_extract_triples_error(
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
            f"engine_model_test_extract_triples_error_{uuid.uuid4().hex}",
            title="extract triples error",
            description=message,
            variant="danger",
        ).to_dict(),
    )


async def append_extract_triples_success(
    module_sdk,
    stream_id: str,
    *,
    graph: dict[str, Any],
    stats: dict[str, Any],
) -> None:
    entities = list(graph.get("entities") or [])
    relations = list(graph.get("relations") or [])
    payload = {"status": "ok", "method": "extract_triples", **dict(stats or {})}
    payload.update({"entities": len(entities), "relations": len(relations)})
    await module_sdk.effects.publish_collection_append(
        stream_id,
        RESULT_COLUMN_ID,
        "children",
        module_sdk.ui.Collapsible(
            f"engine_model_test_extract_triples_performance_{uuid.uuid4().hex}",
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
            f"engine_model_test_extract_triples_graph_{uuid.uuid4().hex}",
            "extracted graph",
            json.dumps(graph, ensure_ascii=False, sort_keys=True, indent=2),
            open=True,
        ).to_dict(),
    )


async def update_extract_triples_status(module_sdk, stream_id: str, status: str) -> None:
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
