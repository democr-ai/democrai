from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.infrastructure.ai.engine.invocation.receivers.base import (
    EngineInvocationReceiver,
)


class GrpcInvocationReceiver(EngineInvocationReceiver):
    def __init__(self, *, node_id: str, service: Any) -> None:
        del node_id
        self._service = service

    def start(self, stop_event: asyncio.Event) -> list[asyncio.Task]:
        from democrai.core.application.ai.engine.orchestrator.server import (
            serve_until_stopped,
        )

        return [
            asyncio.create_task(
                serve_until_stopped(stop_event=stop_event, service=self._service),
                name="engine-invocation-grpc-server",
            )
        ]
