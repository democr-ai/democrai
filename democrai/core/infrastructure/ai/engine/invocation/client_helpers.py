from __future__ import annotations

import inspect
import json
from typing import Any

from democrai.core.application.ai.pipeline_context import AiPipelineMessage
from democrai.core.runtime.foundation.app import current_request_context_payload


def build_request_context_json(*, origin: str, request_id: str) -> str:
    """Serialize the current request context for an engine invocation,
    falling back to a background-channel envelope when none is active.

    Shared by invocation transports."""
    request_context = current_request_context_payload(origin)
    if not request_context:
        request_context = {
            "request_id": request_id,
            "channel": "background",
            "module_name": "core",
            "action_name": origin,
        }
    return json.dumps(request_context, ensure_ascii=True)


async def call_pipeline_callback(callback: Any, value: Any) -> None:
    """Deliver a stream message to an optional on_message callback,
    upgrading dict payloads to AiPipelineMessage."""
    if callback is None:
        return
    if isinstance(value, dict):
        value = AiPipelineMessage(**value)
    result = callback(value)
    if inspect.isawaitable(result):
        await result
