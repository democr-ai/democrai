from __future__ import annotations

from typing import Callable

from democrai.core.infrastructure.network.contracts import StreamProvider
from democrai.core.infrastructure.network.factory._registry import _RegistryFactory
from democrai.core.infrastructure.network.providers.stream.memory import (
    MemoryStreamProvider,
)


class StreamProviderFactory:
    _factory = _RegistryFactory[StreamProvider]("memory", MemoryStreamProvider)

    @classmethod
    def register(
        cls,
        name: str,
        provider_cls: type[StreamProvider] | str | Callable[[], type[StreamProvider]],
    ) -> None:
        cls._factory.register(name, provider_cls)

    @classmethod
    def get_provider(
        cls, provider_type: str | None = "memory", **kwargs
    ) -> StreamProvider:
        explicit = bool(str(provider_type or "").strip())
        return cls._factory.create(provider_type, strict=explicit, **kwargs)


StreamProviderFactory.register(
    "redis",
    "democrai.core.infrastructure.network.providers.stream.redis:RedisStreamProvider",
)
