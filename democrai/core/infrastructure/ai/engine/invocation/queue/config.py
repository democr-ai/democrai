from __future__ import annotations


ENGINE_INVOCATION_QUEUE_NOTIFY_CHANNEL = "engine_invocation_queue"


def engine_response_stream_key(request_id: str) -> str:
    return f"democrai:engine:resp:{request_id}"
