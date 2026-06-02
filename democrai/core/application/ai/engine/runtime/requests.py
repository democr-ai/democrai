from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeRequest:
    request_id: str
    task: asyncio.Task
    loop: asyncio.AbstractEventLoop
    cancel: object | None = None


_REQUESTS: dict[str, RuntimeRequest] = {}
_LOCK = threading.Lock()


def register_runtime_request(
    request_id: str,
    task: asyncio.Task,
    *,
    cancel: object | None = None,
) -> None:
    with _LOCK:
        _REQUESTS[request_id] = RuntimeRequest(
            request_id=request_id,
            task=task,
            loop=task.get_loop(),
            cancel=cancel,
        )


def unregister_runtime_request(request_id: str, task: asyncio.Task) -> None:
    with _LOCK:
        current = _REQUESTS.get(request_id)
        if current is not None and current.task is task:
            _REQUESTS.pop(request_id, None)


def cancel_runtime_request(request_id: str) -> bool:
    with _LOCK:
        current = _REQUESTS.get(request_id)
    if current is None or current.task.done():
        return False
    cancel = current.cancel
    if callable(cancel):
        cancel(request_id)
    current.loop.call_soon_threadsafe(current.task.cancel)
    return True
