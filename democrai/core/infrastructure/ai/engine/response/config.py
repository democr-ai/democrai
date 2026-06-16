from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _get(config: Any | None, key: str, default: Any) -> Any:
    getter = getattr(config, "get", None)
    return getter(key, default) if callable(getter) else default


def _params(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError("engine_response_stream_params_must_be_mapping")
    return dict(value)


@dataclass(frozen=True)
class EngineResponseStreamConfig:
    provider_type: str = "memory"
    params: dict[str, Any] = field(default_factory=dict)
    ttl_seconds: int = 3600
    maxlen: int = 10000

    @classmethod
    def load(cls, config: Any | None = None) -> "EngineResponseStreamConfig":
        provider_type = str(
            _get(config, "ai.engine_orchestrator.response_stream.type", "memory")
            or "memory"
        )
        return cls(
            provider_type=provider_type.strip() or "memory",
            params=_params(
                _get(config, "ai.engine_orchestrator.response_stream.params", {})
            ),
            ttl_seconds=max(
                60,
                int(
                    _get(
                        config,
                        "ai.engine_orchestrator.response_stream.ttl_seconds",
                        3600,
                    )
                    or 3600
                ),
            ),
            maxlen=max(
                100,
                int(
                    _get(config, "ai.engine_orchestrator.response_stream.maxlen", 10000)
                    or 10000
                ),
            ),
        )
