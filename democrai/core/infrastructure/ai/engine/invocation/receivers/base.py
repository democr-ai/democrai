from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod


class EngineInvocationReceiver(ABC):
    @abstractmethod
    def start(self, stop_event: asyncio.Event) -> list[asyncio.Task]:
        raise NotImplementedError
