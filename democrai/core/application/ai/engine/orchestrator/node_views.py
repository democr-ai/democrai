from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    EngineNodeInstanceRegistry,
    RuntimeNodeRegistry,
)
from democrai.core.platform.utils.timezone import utc_now_naive


@dataclass(frozen=True)
class NodeResourcesView:
    """Published node state consumed by placement.

    ``ram_gb``/``vram_gb`` expose FREE capacity (not totals like the local
    SystemResources): cross-node placement asks whether a node can take a new
    load right now. ``warm_instances`` holds (engine_row_id, model_registry_id)
    pairs with a running handle on the node.
    """

    node_id: str
    has_gpu: bool
    ram_gb: float
    vram_gb: float
    cpu_percent: float = 0.0
    warm_instances: frozenset[tuple[int, int]] = field(default_factory=frozenset)
    orchestrator_last_seen_at: datetime | None = None


def load_active_node_views(
    *,
    threshold_seconds: float,
    session_factory: Callable | None = None,
    now: datetime | None = None,
) -> list[NodeResourcesView]:
    """Return the views of nodes with a fresh orchestrator heartbeat."""
    factory = session_factory or SessionLocal
    reference = now or utc_now_naive()
    cutoff = reference - timedelta(seconds=max(1.0, float(threshold_seconds)))
    with factory() as session:
        rows = (
            session.query(RuntimeNodeRegistry)
            .filter(RuntimeNodeRegistry.status == "active")
            .filter(RuntimeNodeRegistry.orchestrator_last_seen_at.isnot(None))
            .filter(RuntimeNodeRegistry.orchestrator_last_seen_at >= cutoff)
            .all()
        )
        node_ids = [row.node_id for row in rows]
        warm_by_node: dict[str, set[tuple[int, int]]] = {}
        if node_ids:
            instances = (
                session.query(EngineNodeInstanceRegistry)
                .filter(EngineNodeInstanceRegistry.node_id.in_(node_ids))
                .filter(EngineNodeInstanceRegistry.status == "running")
                .all()
            )
            for instance in instances:
                warm_by_node.setdefault(instance.node_id, set()).add(
                    (int(instance.engine_row_id), int(instance.model_registry_id))
                )
        views: list[NodeResourcesView] = []
        for row in rows:
            vram_free_mb = int(row.vram_free_mb or 0)
            views.append(
                NodeResourcesView(
                    node_id=str(row.node_id),
                    has_gpu=bool(row.has_nvidia_gpu) or vram_free_mb > 0,
                    ram_gb=round(int(row.ram_free_mb or 0) / 1024, 2),
                    vram_gb=round(vram_free_mb / 1024, 2),
                    cpu_percent=float(row.cpu_percent or 0.0),
                    warm_instances=frozenset(warm_by_node.get(row.node_id, set())),
                    orchestrator_last_seen_at=row.orchestrator_last_seen_at,
                )
            )
        return views
