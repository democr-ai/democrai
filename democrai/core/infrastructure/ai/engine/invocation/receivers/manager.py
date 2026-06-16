from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
    EngineOrchestratorProviderResolver,
)
from democrai.core.infrastructure.ai.engine.invocation.receivers.factory import (
    EngineInvocationReceiverFactory,
)


class EngineInvocationReceiverManager:
    def __init__(
        self,
        *,
        node_id: str,
        service: Any,
        config: Any | None = None,
    ) -> None:
        self._node_id = node_id
        self._service = service
        self._config = config

    def start(self, stop_event: asyncio.Event) -> list[asyncio.Task]:
        tasks: list[asyncio.Task] = []
        for name in EngineOrchestratorProviderResolver.receiver_names_from_config(
            self._config
        ):
            receiver = EngineInvocationReceiverFactory.create(
                name,
                node_id=self._node_id,
                service=self._service,
            )
            tasks.extend(receiver.start(stop_event))
        return tasks
