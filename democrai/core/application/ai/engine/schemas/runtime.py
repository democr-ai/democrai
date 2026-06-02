from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EngineUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class EngineMethodResponse:
    result: Any
    usage: EngineUsage = field(default_factory=EngineUsage)
    duration_ms: float = 0.0
    tokens_per_second: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def stats(self) -> dict[str, Any]:
        payload = {
            "token_input": self.usage.prompt_tokens,
            "token_output": self.usage.completion_tokens,
            "token_total": self.usage.total_tokens,
            "tps": self.tokens_per_second,
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "total_tokens": self.usage.total_tokens,
            "tokens_per_second": self.tokens_per_second,
            "duration_ms": self.duration_ms,
        }
        payload.update(self.metadata)
        return payload

    def model_dump(self, *args, **kwargs) -> dict[str, Any]:
        return {
            "result": _dump_value(self.result),
            "usage": self.usage.to_dict(),
            "duration_ms": self.duration_ms,
            "tokens_per_second": self.tokens_per_second,
            "metadata": self.metadata,
            "stats": self.stats,
        }

    def __getattr__(self, name: str) -> Any:
        return getattr(self.result, name)

    def __iter__(self):
        return iter(self.result)

    def __len__(self) -> int:
        return len(self.result)

    def __getitem__(self, key: Any) -> Any:
        return self.result[key]

    def __bool__(self) -> bool:
        return bool(self.result)

    def __eq__(self, other: Any) -> bool:
        return self.result == other


@dataclass(frozen=True)
class EngineStreamFinal:
    usage: EngineUsage = field(default_factory=EngineUsage)
    duration_ms: float = 0.0
    tokens_per_second: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def stats(self) -> dict[str, Any]:
        return EngineMethodResponse(
            result=None,
            usage=self.usage,
            duration_ms=self.duration_ms,
            tokens_per_second=self.tokens_per_second,
            metadata=self.metadata,
        ).stats

    def model_dump(self, *args, **kwargs) -> dict[str, Any]:
        return {
            "type": "engine_stream_final",
            "usage": self.usage.to_dict(),
            "duration_ms": self.duration_ms,
            "tokens_per_second": self.tokens_per_second,
            "metadata": self.metadata,
            "stats": self.stats,
        }


def _dump_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    if isinstance(value, list):
        return [_dump_value(item) for item in value]
    if isinstance(value, tuple):
        return [_dump_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dump_value(item) for key, item in value.items()}
    if isinstance(value, bytes | bytearray):
        return f"<bytes:{len(value)}>"
    return value
