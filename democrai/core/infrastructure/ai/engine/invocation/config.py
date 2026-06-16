from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from democrai.core.platform.utils.normalize import normalize_bool


def _get(config: Any | None, key: str, default: Any) -> Any:
    getter = getattr(config, "get", None)
    return getter(key, default) if callable(getter) else default


class EngineInvocationRuntimeConfig(BaseModel):
    node_coordination_enabled: bool = False
    queue_claim_poll_seconds: float = 2.0
    queue_lease_seconds: int = 120
    queue_max_attempts: int = 3
    queue_keepalive_seconds: float = 10.0
    queue_retention_seconds: int = 86400
    placement_force_claim_age_seconds: float = 10.0
    node_state_active_threshold_seconds: float = 10.0
    node_state_publish_seconds: float = 2.0

    @classmethod
    def load(cls, config: Any | None = None) -> "EngineInvocationRuntimeConfig":
        max_attempts = _get(config, "ai.engine_orchestrator.queue.max_attempts", None)
        return cls(
            node_coordination_enabled=normalize_bool(
                _get(
                    config,
                    "ai.engine_orchestrator.node_coordination.enabled",
                    False,
                ),
                default=False,
            ),
            queue_claim_poll_seconds=max(
                0.1,
                float(
                    _get(
                        config,
                        "ai.engine_orchestrator.queue.claim_poll_seconds",
                        2.0,
                    )
                    or 2.0
                ),
            ),
            queue_lease_seconds=max(
                5,
                int(
                    _get(config, "ai.engine_orchestrator.queue.lease_seconds", 120)
                    or 120
                ),
            ),
            queue_max_attempts=max(1, int(3 if max_attempts is None else max_attempts)),
            queue_keepalive_seconds=max(
                1.0,
                float(
                    _get(config, "ai.engine_orchestrator.queue.keepalive_seconds", 10)
                    or 10
                ),
            ),
            queue_retention_seconds=max(
                60,
                int(
                    _get(config, "ai.engine_orchestrator.queue.retention_seconds", 86400)
                    or 86400
                ),
            ),
            placement_force_claim_age_seconds=max(
                0.0,
                float(
                    _get(
                        config,
                        "ai.engine_orchestrator.placement.force_claim_age_seconds",
                        10,
                    )
                    or 10
                ),
            ),
            node_state_active_threshold_seconds=max(
                1.0,
                float(
                    _get(
                        config,
                        "ai.engine_orchestrator.node_state.active_threshold_seconds",
                        10,
                    )
                    or 10
                ),
            ),
            node_state_publish_seconds=max(
                0.5,
                float(
                    _get(config, "ai.engine_orchestrator.node_state.publish_seconds", 2)
                    or 2
                ),
            ),
        )

    def validate_node_coordination(self, config: Any | None = None) -> None:
        if not self.node_coordination_enabled:
            return
        problems: list[str] = []
        db_type = str(_get(config, "database.type", "sqlite")).strip().lower()
        if db_type != "postgres":
            problems.append(
                "database.type=postgres is required for node coordination"
            )
        node_id = str(_get(config, "network.node_id", "")).strip()
        if not node_id:
            problems.append(
                "network.node_id must be set explicitly (the hostname default "
                "can collide across nodes)"
            )
        threshold = self.node_state_active_threshold_seconds
        publish = self.node_state_publish_seconds
        if threshold < 2 * publish:
            problems.append(
                "node_state.active_threshold_seconds must be at least twice "
                f"node_state.publish_seconds (threshold={threshold}, "
                f"publish={publish}): otherwise live nodes look permanently stale"
            )
        if problems:
            raise RuntimeError(
                "engine_orchestrator_node_coordination_config_invalid: "
                + "; ".join(problems)
            )
