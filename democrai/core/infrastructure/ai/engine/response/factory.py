from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
import threading
from typing import Any, Callable

from democrai.core.infrastructure.ai.engine.response.config import (
    EngineResponseStreamConfig,
)
from democrai.core.infrastructure.ai.engine.response.stream import (
    EngineResponseStream,
)
from democrai.core.runtime.foundation.app import app_ctx


ProviderEntry = (
    type[EngineResponseStream] | str | Callable[[], type[EngineResponseStream]]
)


@dataclass(frozen=True)
class _ProviderDefinition:
    entry: ProviderEntry
    cross_process: bool | None = None


class EngineResponseStreamFactory:
    _shared_lock = threading.Lock()
    _shared_streams: dict[tuple[str, str], EngineResponseStream] = {}
    _registry: dict[str, _ProviderDefinition] = {
        "memory": _ProviderDefinition(
            (
                "democrai.core.infrastructure.ai.engine.response.providers.memory:"
                "MemoryEngineResponseStream"
            ),
            cross_process=False,
        ),
        "redis": _ProviderDefinition(
            (
                "democrai.core.infrastructure.ai.engine.response.providers.redis:"
                "RedisEngineResponseStream"
            ),
            cross_process=True,
        ),
    }

    @classmethod
    def register(
        cls,
        name: str,
        provider_entry: ProviderEntry,
        *,
        cross_process: bool | None = None,
    ) -> None:
        cls._registry[str(name).strip().lower()] = _ProviderDefinition(
            provider_entry,
            cross_process=cross_process,
        )

    @classmethod
    def has_provider(cls, provider_type: str) -> bool:
        raw = str(provider_type or "").strip()
        definition = cls._definition_for(raw)
        if definition is None:
            return False
        if isinstance(definition.entry, str):
            module_name, _, attr_name = definition.entry.partition(":")
            return bool(module_name and attr_name)
        try:
            provider_cls = cls._resolve_entry(definition.entry)
        except Exception:
            return False
        return issubclass(provider_cls, EngineResponseStream)

    @classmethod
    def get_stream(cls, config: Any | None = None) -> EngineResponseStream:
        stream_config = EngineResponseStreamConfig.load(config)
        params = dict(stream_config.params)
        params.setdefault("ttl_seconds", stream_config.ttl_seconds)
        params.setdefault("maxlen", stream_config.maxlen)
        return cls.get_provider(stream_config.provider_type, **params)

    @classmethod
    def get_shared_stream(cls, config: Any | None = None) -> EngineResponseStream:
        stream_config = EngineResponseStreamConfig.load(config)
        params = dict(stream_config.params)
        params.setdefault("ttl_seconds", stream_config.ttl_seconds)
        params.setdefault("maxlen", stream_config.maxlen)
        provider_type = str(stream_config.provider_type or "memory").strip().lower()
        key = (
            provider_type,
            json.dumps(params, ensure_ascii=True, sort_keys=True, default=str),
        )
        with cls._shared_lock:
            stream = cls._shared_streams.get(key)
            if stream is None:
                stream = cls.get_provider(stream_config.provider_type, **params)
                cls._shared_streams[key] = stream
            return stream

    @classmethod
    async def aclose_shared_streams(cls) -> None:
        with cls._shared_lock:
            streams = list(cls._shared_streams.values())
            cls._shared_streams.clear()
        seen: set[int] = set()
        for stream in streams:
            if id(stream) in seen:
                continue
            seen.add(id(stream))
            try:
                await stream.aclose()
            except Exception:
                continue

    @classmethod
    def get_provider(
        cls,
        provider_type: str | None = "memory",
        **kwargs: Any,
    ) -> EngineResponseStream:
        raw = str(provider_type or "memory").strip()
        normalized = raw.lower() or "memory"
        definition = cls._definition_for(raw)
        if definition is None:
            raise RuntimeError(f"engine_response_stream_provider_unknown:{normalized}")
        provider_cls = cls._resolve_entry(definition.entry)
        provider = provider_cls(**kwargs)
        if not isinstance(provider, EngineResponseStream):
            raise RuntimeError(
                "engine_response_stream_provider_must_extend_engine_response_stream"
            )
        return provider

    @classmethod
    def is_cross_process_provider(cls, provider_type: str | None) -> bool:
        raw = str(provider_type or "memory").strip() or "memory"
        definition = cls._definition_for(raw)
        if definition is None:
            raise RuntimeError(f"engine_response_stream_provider_unknown:{raw}")
        if definition.cross_process is not None:
            return bool(definition.cross_process)
        provider_cls = cls._resolve_entry(definition.entry)
        return bool(getattr(provider_cls, "cross_process", False))

    @classmethod
    def _definition_for(cls, provider_type: str) -> _ProviderDefinition | None:
        raw = str(provider_type or "").strip()
        definition = cls._registry.get(raw.lower())
        if definition is None and ":" in raw:
            return _ProviderDefinition(raw)
        return definition

    @staticmethod
    def _resolve_entry(entry: ProviderEntry) -> type[EngineResponseStream]:
        if isinstance(entry, str):
            module_name, _, attr_name = entry.partition(":")
            module = import_module(module_name)
            return getattr(module, attr_name)
        if isinstance(entry, type):
            return entry
        resolved = entry()
        if not isinstance(resolved, type):
            raise TypeError(
                "engine response stream provider resolver must return a class"
            )
        return resolved


def resolve_engine_response_stream(
    stream: EngineResponseStream | None = None,
) -> EngineResponseStream:
    if isinstance(stream, EngineResponseStream):
        return stream
    if stream is not None:
        raise RuntimeError("engine_response_stream_provider_object_invalid")
    return EngineResponseStreamFactory.get_shared_stream(getattr(app_ctx(), "config", None))
