from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any


class StreamProvider(ABC):
    """Interface for real-time Pub/Sub streaming."""

    @abstractmethod
    def subscribe(self, channel_id: str) -> asyncio.Queue:
        """Subscribes to a channel and returns a queue."""

    @abstractmethod
    def unsubscribe(self, channel_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribes from a channel."""

    @abstractmethod
    async def broadcast(self, channel_id: str, data: Any) -> None:
        """Broadcasts data to all subscribers of a channel."""
