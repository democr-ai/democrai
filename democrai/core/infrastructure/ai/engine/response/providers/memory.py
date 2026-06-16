from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.infrastructure.ai.engine.response.backpressure import (
    put_with_backpressure,
)
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream


class MemoryEngineResponseStream(EngineResponseStream):
    def __init__(self, **_: Any) -> None:
        self._channels: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, channel_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=4096)
        self._channels.setdefault(channel_id, set()).add(queue)
        return queue

    def unsubscribe(self, channel_id: str, queue: asyncio.Queue) -> None:
        queues = self._channels.get(channel_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            self._channels.pop(channel_id, None)

    async def publish(self, channel_id: str, data: dict[str, Any]) -> None:
        for queue in list(self._channels.get(channel_id, ())):
            item = dict(data)
            await put_with_backpressure(
                queue,
                item,
                is_active=lambda queue=queue: self._is_subscribed(
                    channel_id, queue
                ),
            )

    def _is_subscribed(self, channel_id: str, queue: asyncio.Queue) -> bool:
        return queue in self._channels.get(channel_id, ())
