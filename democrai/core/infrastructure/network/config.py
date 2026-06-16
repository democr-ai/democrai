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
        raise RuntimeError("network_stream_params_must_be_mapping")
    return dict(value)


@dataclass(frozen=True)
class NetworkStreamConfig:
    provider_type: str = "memory"
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, config: Any | None = None) -> "NetworkStreamConfig":
        provider_type = str(_get(config, "network.stream.type", "memory") or "memory")
        return cls(
            provider_type=provider_type.strip() or "memory",
            params=_params(_get(config, "network.stream.params", {})),
        )
