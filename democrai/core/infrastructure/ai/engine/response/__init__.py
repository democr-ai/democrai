from __future__ import annotations

__all__ = [
    "EngineResponseEntry",
    "EngineResponseStream",
    "EngineResponseStreamConfig",
    "EngineResponseStreamFactory",
    "EngineResponseStreamReader",
    "EngineResponseStreamWriter",
    "resolve_engine_response_stream",
]


def __getattr__(name: str):
    if name in {"EngineResponseEntry", "EngineResponseStreamReader"}:
        from democrai.core.infrastructure.ai.engine.response.reader import (
            EngineResponseEntry,
            EngineResponseStreamReader,
        )

        return {
            "EngineResponseEntry": EngineResponseEntry,
            "EngineResponseStreamReader": EngineResponseStreamReader,
        }[name]
    if name == "EngineResponseStreamWriter":
        from democrai.core.infrastructure.ai.engine.response.writer import (
            EngineResponseStreamWriter,
        )

        return EngineResponseStreamWriter
    if name == "EngineResponseStreamConfig":
        from democrai.core.infrastructure.ai.engine.response.config import (
            EngineResponseStreamConfig,
        )

        return EngineResponseStreamConfig
    if name in {"EngineResponseStreamFactory", "resolve_engine_response_stream"}:
        from democrai.core.infrastructure.ai.engine.response.factory import (
            EngineResponseStreamFactory,
            resolve_engine_response_stream,
        )

        return {
            "EngineResponseStreamFactory": EngineResponseStreamFactory,
            "resolve_engine_response_stream": resolve_engine_response_stream,
        }[name]
    if name == "EngineResponseStream":
        from democrai.core.infrastructure.ai.engine.response.stream import (
            EngineResponseStream,
        )

        return EngineResponseStream
    raise AttributeError(name)
