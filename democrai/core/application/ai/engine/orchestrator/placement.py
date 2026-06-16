from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from democrai.core.infrastructure.ai.engine.invocation.config import (
    EngineInvocationRuntimeConfig,
)
from democrai.core.application.ai.engine.orchestrator.node_views import (
    NodeResourcesView,
    load_active_node_views,
)
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import app_ctx


_ORIGIN_AFFINITY_BONUS = 30


class EnginePlacement:
    """Decides whether this node should claim a queue row or defer to a
    better-scored peer.

    Every node runs the same comparison over the published views — itself
    included, through its own published view, for symmetry. The published
    state is advisory: past ``force_claim_age_seconds`` whoever can serve the
    row claims it, so stale views cost a suboptimal placement, never a stuck
    request. Ties break deterministically on the smallest node_id.
    """

    def __init__(self, *, node_id: str) -> None:
        config = app_ctx().config
        runtime_config = EngineInvocationRuntimeConfig.load(config)
        self._node_id = node_id
        self._threshold_seconds = runtime_config.node_state_active_threshold_seconds
        self._force_claim_age_seconds = (
            runtime_config.placement_force_claim_age_seconds
        )

    def load_views(self) -> list[NodeResourcesView]:
        """Snapshot of the active node views; the claim worker loads it once
        per tick and shares it across every row decision."""
        return load_active_node_views(threshold_seconds=self._threshold_seconds)

    def should_claim(
        self,
        row: dict[str, Any],
        target: dict[str, Any] | None = None,
        views: list[NodeResourcesView] | None = None,
        score_cache: dict[Any, int | None] | None = None,
    ) -> bool:
        if views is None:
            views = self.load_views()
        eligible_node_ids = self._engine_install_eligible_node_ids(
            str((target or {}).get("engine_id") or "")
        )
        if eligible_node_ids is not None:
            if self._node_id not in eligible_node_ids:
                return False
            views = [view for view in views if view.node_id in eligible_node_ids]
        if not any(view.node_id == self._node_id for view in views):
            # Own state not published yet (fresh start): claiming beats
            # deferring to a comparison this node cannot take part in.
            return True
        age_reference = row.get("available_at") or row.get("created_at")
        if age_reference is not None:
            age = (utc_now_naive() - age_reference).total_seconds()
            if age >= self._force_claim_age_seconds:
                return True
        scores: dict[str, int] = {}
        for view in views:
            score = self._cached_score(row, view, score_cache)
            if score is None:
                continue
            scores[view.node_id] = score
        my_score = scores.get(self._node_id)
        if my_score is None:
            return False
        best = max(scores.values())
        if my_score < best:
            return False
        best_nodes = sorted(
            node_id for node_id, score in scores.items() if score == best
        )
        return best_nodes[0] == self._node_id

    def _cached_score(
        self,
        row: dict[str, Any],
        view: NodeResourcesView,
        score_cache: dict[Any, int | None] | None,
    ) -> int | None:
        if score_cache is None:
            return self._score(row, view)
        key = (
            view.node_id,
            str(row["selector_type"]),
            row.get("model_registry_id"),
            row.get("objective"),
            str(row.get("capabilities_json") or "[]"),
            row.get("prefer_local"),
            row.get("origin_node_id") if row.get("prefer_local") else None,
        )
        if key not in score_cache:
            score_cache[key] = self._score(row, view)
        return score_cache[key]

    def _score(self, row: dict[str, Any], view: NodeResourcesView) -> int | None:
        from democrai.core.application.ai.orchestrator import model_orchestrator

        try:
            capabilities = json.loads(str(row.get("capabilities_json") or "[]"))
        except Exception:
            capabilities = []
        score = model_orchestrator.score_selector_for_view(
            selector_type=str(row["selector_type"]),
            model_registry_id=row.get("model_registry_id"),
            objective=row.get("objective"),
            required_capabilities=[item for item in capabilities if item],
            prefer_local=row.get("prefer_local"),
            view=view,
        )
        if score is None:
            return None
        # prefer_local was a single-box hint; here it becomes affinity
        # to the node that received the request.
        if row.get("prefer_local") and view.node_id == row.get("origin_node_id"):
            score += _ORIGIN_AFFINITY_BONUS
        return score

    def _engine_install_eligible_node_ids(self, engine_id: str) -> set[str] | None:
        if not engine_id:
            return None
        from democrai.core.infrastructure.database import SessionLocal
        from democrai.core.infrastructure.database.models import (
            EngineNodeInstallRegistry,
            RuntimeNodeRegistry,
        )

        cutoff = utc_now_naive() - timedelta(
            seconds=max(1.0, float(self._threshold_seconds))
        )
        with SessionLocal() as session:
            rows = (
                session.query(
                    EngineNodeInstallRegistry.node_id,
                    RuntimeNodeRegistry.status,
                    RuntimeNodeRegistry.orchestrator_last_seen_at,
                )
                .outerjoin(
                    RuntimeNodeRegistry,
                    RuntimeNodeRegistry.node_id == EngineNodeInstallRegistry.node_id,
                )
                .filter(EngineNodeInstallRegistry.engine_id == engine_id)
                .filter(EngineNodeInstallRegistry.status == "installed")
                .all()
            )
        if not rows:
            return None
        eligible: set[str] = set()
        for node_id, status, last_seen_at in rows:
            resolved_node_id = str(node_id)
            if resolved_node_id == self._node_id:
                eligible.add(resolved_node_id)
                continue
            if status == "active" and last_seen_at is not None and last_seen_at >= cutoff:
                eligible.add(resolved_node_id)
        return eligible
