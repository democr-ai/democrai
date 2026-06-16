from __future__ import annotations

import asyncio

from democrai.core.infrastructure.ai.engine.invocation.config import (
    EngineInvocationRuntimeConfig,
)
from democrai.core.application.ai.engine.orchestrator.node_state import (
    NodeStateRepository,
)
from democrai.core.runtime.foundation.app import app_ctx


class NodeStatePublisher:
    """Publishes heartbeat, live resources and warm inventory of this node.

    Runs inside the engine orchestrator subprocess, the process that owns the
    EngineRuntime handle pool and therefore the truth about warm instances.
    """

    # Anti-drift: even with no inventory changes a full reconcile runs at
    # least this often (write-through failures, external row edits).
    _FORCE_RECONCILE_SECONDS = 30.0

    def __init__(
        self,
        *,
        node_id: str,
        repository: NodeStateRepository | None = None,
    ) -> None:
        self._node_id = node_id
        self._repository = repository or NodeStateRepository()
        self._last_inventory: frozenset | None = None
        self._last_reconcile_at = 0.0

    def publish_once(self) -> None:
        import time

        from democrai.core.application.ai.engine.runtime import get_engine_runtime
        from democrai.core.application.runtime_metrics.events import (
            build_runtime_metrics_sample,
        )

        sample = build_runtime_metrics_sample()
        self._repository.publish_heartbeat(node_id=self._node_id, sample=sample)
        instances = get_engine_runtime().active_instances()
        inventory = frozenset(
            (
                int(item.get("engine_row_id") or 0),
                int(item.get("model_registry_id") or 0),
                str(item.get("config_signature") or ""),
                str(item.get("status") or ""),
                item.get("pid"),
            )
            for item in instances
        )
        now = time.monotonic()
        if (
            inventory == self._last_inventory
            and now - self._last_reconcile_at < self._FORCE_RECONCILE_SECONDS
        ):
            return
        self._repository.reconcile_instances(
            node_id=self._node_id, instances=instances
        )
        self._last_inventory = inventory
        self._last_reconcile_at = now

    def startup_purge(self) -> None:
        deleted = self._repository.purge_node_instances(node_id=self._node_id)
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None and deleted:
            logger.info(
                f"[Engine] purged {deleted} stale instance rows "
                f"for node {self._node_id}"
            )

    def mark_offline(self) -> None:
        try:
            self._repository.mark_offline(node_id=self._node_id)
            self._repository.purge_node_instances(node_id=self._node_id)
        except Exception:
            logger = getattr(app_ctx(), "logger", None)
            if logger is not None:
                logger.debug("[Engine] offline mark failed", exc_info=True)

    async def run_until_stopped(self, stop_event: asyncio.Event) -> None:
        interval = EngineInvocationRuntimeConfig.load(
            app_ctx().config
        ).node_state_publish_seconds
        logger = getattr(app_ctx(), "logger", None)
        await asyncio.to_thread(self.startup_purge)
        try:
            while not stop_event.is_set():
                try:
                    await asyncio.to_thread(self.publish_once)
                except Exception as exc:
                    if logger is not None:
                        logger.warning(
                            f"[Engine] node state publish failed: {exc}"
                        )
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    continue
        finally:
            # mark_offline is sync and best-effort: runs on cancellation too.
            self.mark_offline()
