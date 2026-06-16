from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.application.ai.engine.orchestrator.node_state_publisher import (
    NodeStatePublisher,
)
from democrai.core.application.ai.engine.orchestrator.placement import (
    EnginePlacement,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.claim_worker import (
    EngineQueueClaimWorker,
)
from democrai.core.infrastructure.ai.engine.invocation.config import (
    EngineInvocationRuntimeConfig,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.maintenance import (
    EngineQueueMaintenance,
)
from democrai.core.infrastructure.ai.engine.invocation.receivers.base import (
    EngineInvocationReceiver,
)
from democrai.core.runtime.foundation.app import app_ctx


class QueueInvocationReceiver(EngineInvocationReceiver):
    def __init__(self, *, node_id: str, service: Any) -> None:
        self._node_id = node_id
        self._service = service

    def start(self, stop_event: asyncio.Event) -> list[asyncio.Task]:
        config = app_ctx().config
        runtime_config = EngineInvocationRuntimeConfig.load(config)
        runtime_config.validate_node_coordination(config)
        use_node_coordination = runtime_config.node_coordination_enabled
        app_ctx().engine_orchestrator_publishes_node_state = True
        tasks = [
            asyncio.create_task(
                EngineQueueClaimWorker(
                    node_id=self._node_id,
                    service=self._service,
                    placement=EnginePlacement(node_id=self._node_id)
                    if use_node_coordination
                    else None,
                ).run_until_stopped(stop_event),
                name="engine-invocation-queue-claim-worker",
            ),
            asyncio.create_task(
                EngineQueueMaintenance(
                    node_id=self._node_id,
                    orphan_origin_check_enabled=use_node_coordination,
                ).run_until_stopped(stop_event),
                name="engine-invocation-queue-maintenance",
            ),
            asyncio.create_task(
                NodeStatePublisher(node_id=self._node_id).run_until_stopped(
                    stop_event
                ),
                name="engine-node-state-publisher",
            ),
        ]
        return tasks
