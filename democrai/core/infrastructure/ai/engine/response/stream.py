from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any


class EngineResponseStream(ABC):
    @abstractmethod
    def subscribe(self, channel_id: str) -> asyncio.Queue:
        raise NotImplementedError

    @abstractmethod
    def unsubscribe(self, channel_id: str, queue: asyncio.Queue) -> None:
        raise NotImplementedError

    async def unsubscribe_async(self, channel_id: str, queue: asyncio.Queue) -> None:
        self.unsubscribe(channel_id, queue)

    async def aclose(self) -> None:
        return None

    @abstractmethod
    async def publish(self, channel_id: str, data: dict[str, Any]) -> None:
        raise NotImplementedError
