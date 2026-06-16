from __future__ import annotations

import json
from typing import Any, Callable

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    EngineNodeInstanceRegistry,
    RuntimeNodeRegistry,
)
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import app_ctx


class NodeStateRepository:
    """DB writes/reads for the published node state.

    Heartbeat and resources go to RuntimeNodeRegistry; last_seen_at stays
    owned by the core runtime-metrics writer. Warm instances go to
    EngineNodeInstanceRegistry.
    """

    def __init__(self, session_factory: Callable | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    def publish_heartbeat(self, *, node_id: str, sample: dict[str, Any]) -> None:
        now = utc_now_naive()
        gpu_inventory: list[dict[str, Any]] = []
        vram_total_mb = int(sample.get("vram_total_mb") or 0)
        if vram_total_mb > 0:
            gpu_inventory.append(
                {
                    "vram_total_mb": vram_total_mb,
                    "vram_free_mb": int(sample.get("vram_free_mb") or 0),
                }
            )
        with self._session_factory() as session:
            row = (
                session.query(RuntimeNodeRegistry)
                .filter(RuntimeNodeRegistry.node_id == node_id)
                .first()
            )
            if row is None:
                row = RuntimeNodeRegistry(
                    node_id=node_id,
                    hostname=SERVER_NAME,
                    status="active",
                    created_at=now,
                )
                session.add(row)
            row.status = "active"
            row.has_nvidia_gpu = bool(sample.get("has_nvidia_gpu"))
            row.orchestrator_last_seen_at = now
            row.cpu_percent = float(sample.get("cpu_percent") or 0.0)
            row.ram_total_mb = int(sample.get("ram_total_mb") or 0)
            row.ram_free_mb = int(sample.get("ram_free_mb") or 0)
            row.vram_total_mb = vram_total_mb
            row.vram_free_mb = int(sample.get("vram_free_mb") or 0)
            row.gpu_inventory_json = json.dumps(gpu_inventory, ensure_ascii=True)
            row.resources_updated_at = now
            row.updated_at = now
            session.commit()

    def mark_offline(self, *, node_id: str) -> None:
        with self._session_factory() as session:
            row = (
                session.query(RuntimeNodeRegistry)
                .filter(RuntimeNodeRegistry.node_id == node_id)
                .first()
            )
            if row is not None:
                row.orchestrator_last_seen_at = None
                row.updated_at = utc_now_naive()
                session.commit()

    def purge_node_instances(self, *, node_id: str) -> int:
        with self._session_factory() as session:
            deleted = (
                session.query(EngineNodeInstanceRegistry)
                .filter(EngineNodeInstanceRegistry.node_id == node_id)
                .delete(synchronize_session=False)
            )
            session.commit()
            return int(deleted or 0)

    def reconcile_instances(
        self, *, node_id: str, instances: list[dict[str, Any]]
    ) -> None:
        """Make the published running inventory match the live handle pool.

        Rows in ``loading`` state are in-flight claim markers owned by the
        claim worker and are left untouched here.
        """
        now = utc_now_naive()
        running = {
            (int(item.get("engine_row_id") or 0), int(item.get("model_registry_id") or 0)): item
            for item in instances
            if str(item.get("status") or "") == "running"
        }
        with self._session_factory() as session:
            rows = (
                session.query(EngineNodeInstanceRegistry)
                .filter(EngineNodeInstanceRegistry.node_id == node_id)
                .all()
            )
            seen: set[tuple[int, int]] = set()
            for row in rows:
                key = (int(row.engine_row_id), int(row.model_registry_id))
                if key in running:
                    item = running[key]
                    row.engine_id = str(item.get("engine_id") or "")
                    row.model = str(item.get("model") or "")
                    row.config_signature = str(item.get("config_signature") or "")
                    row.status = "running"
                    row.pid = item.get("pid")
                    row.last_seen_at = now
                    row.updated_at = now
                    seen.add(key)
                elif row.status != "loading":
                    session.delete(row)
            for key, item in running.items():
                if key in seen:
                    continue
                session.add(
                    EngineNodeInstanceRegistry(
                        node_id=node_id,
                        engine_row_id=key[0],
                        model_registry_id=key[1],
                        engine_id=str(item.get("engine_id") or ""),
                        model=str(item.get("model") or ""),
                        config_signature=str(item.get("config_signature") or ""),
                        status="running",
                        pid=item.get("pid"),
                        last_seen_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.commit()

    def upsert_running_instance(
        self,
        *,
        node_id: str,
        engine_row_id: int,
        model_registry_id: int,
        engine_id: str = "",
        model: str = "",
        config_signature: str = "",
        pid: int | None = None,
    ) -> None:
        now = utc_now_naive()
        with self._session_factory() as session:
            row = (
                session.query(EngineNodeInstanceRegistry)
                .filter(EngineNodeInstanceRegistry.node_id == node_id)
                .filter(EngineNodeInstanceRegistry.engine_row_id == engine_row_id)
                .filter(
                    EngineNodeInstanceRegistry.model_registry_id == model_registry_id
                )
                .first()
            )
            if row is None:
                row = EngineNodeInstanceRegistry(
                    node_id=node_id,
                    engine_row_id=engine_row_id,
                    model_registry_id=model_registry_id,
                    created_at=now,
                )
                session.add(row)
            row.engine_id = engine_id
            row.model = model
            row.config_signature = config_signature
            row.status = "running"
            row.pid = pid
            row.last_seen_at = now
            row.updated_at = now
            session.commit()

    def remove_instance(
        self, *, node_id: str, engine_row_id: int, model_registry_id: int | None = None
    ) -> None:
        with self._session_factory() as session:
            query = (
                session.query(EngineNodeInstanceRegistry)
                .filter(EngineNodeInstanceRegistry.node_id == node_id)
                .filter(EngineNodeInstanceRegistry.engine_row_id == engine_row_id)
            )
            if model_registry_id is not None:
                query = query.filter(
                    EngineNodeInstanceRegistry.model_registry_id == model_registry_id
                )
            query.delete(synchronize_session=False)
            session.commit()


def _write_through_active() -> bool:
    return bool(getattr(app_ctx(), "engine_orchestrator_publishes_node_state", False))


def record_instance_running(
    *,
    engine_row_id: int,
    model_registry_id: int,
    engine_id: str = "",
    model: str = "",
    config_signature: str = "",
    pid: int | None = None,
) -> None:
    """Best-effort write-through from EngineRuntime handle creation.

    Never raises: the periodic publisher reconcile is the authoritative
    anti-drift path.
    """
    try:
        if not _write_through_active():
            return
        from democrai.core.application.ai.engine.runtime.environment import (
            runtime_node_id,
        )

        NodeStateRepository().upsert_running_instance(
            node_id=runtime_node_id(),
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
            engine_id=engine_id,
            model=model,
            config_signature=config_signature,
            pid=pid,
        )
    except Exception:
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.debug(
                "[Engine] instance write-through failed", exc_info=True
            )


def record_instance_removed(
    *, engine_row_id: int, model_registry_id: int | None = None
) -> None:
    """Best-effort write-through from EngineRuntime handle teardown."""
    try:
        if not _write_through_active():
            return
        from democrai.core.application.ai.engine.runtime.environment import (
            runtime_node_id,
        )

        NodeStateRepository().remove_instance(
            node_id=runtime_node_id(),
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
        )
    except Exception:
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.debug(
                "[Engine] instance write-through failed", exc_info=True
            )
