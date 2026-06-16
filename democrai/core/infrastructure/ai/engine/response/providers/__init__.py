from __future__ import annotations

__all__ = ["MemoryEngineResponseStream", "RedisEngineResponseStream"]


def __getattr__(name: str):
    if name == "MemoryEngineResponseStream":
        from democrai.core.infrastructure.ai.engine.response.providers.memory import (
            MemoryEngineResponseStream,
        )

        return MemoryEngineResponseStream
    if name == "RedisEngineResponseStream":
        from democrai.core.infrastructure.ai.engine.response.providers.redis import (
            RedisEngineResponseStream,
        )

        return RedisEngineResponseStream
    raise AttributeError(name)
