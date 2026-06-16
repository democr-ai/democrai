from __future__ import annotations

from importlib import import_module
from typing import Any, Callable

from democrai.core.infrastructure.ai.engine.invocation.receivers.base import (
    EngineInvocationReceiver,
)


ReceiverEntry = (
    type[EngineInvocationReceiver]
    | str
    | Callable[[], type[EngineInvocationReceiver]]
)


class EngineInvocationReceiverFactory:
    _registry: dict[str, ReceiverEntry] = {
        "grpc": (
            "democrai.core.infrastructure.ai.engine.invocation.receivers.grpc:"
            "GrpcInvocationReceiver"
        ),
        "queue": (
            "democrai.core.infrastructure.ai.engine.invocation.receivers.queue:"
            "QueueInvocationReceiver"
        ),
    }

    @classmethod
    def register(cls, name: str, receiver_entry: ReceiverEntry) -> None:
        cls._registry[str(name).strip().lower()] = receiver_entry

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> EngineInvocationReceiver:
        normalized = str(name or "").strip().lower()
        entry = cls._registry.get(normalized)
        if entry is None:
            raise RuntimeError(f"engine_invocation_receiver_unknown:{normalized}")
        receiver_cls = cls._resolve_entry(entry)
        return receiver_cls(**kwargs)

    @staticmethod
    def _resolve_entry(entry: ReceiverEntry) -> type[EngineInvocationReceiver]:
        if isinstance(entry, str):
            module_name, _, attr_name = entry.partition(":")
            module = import_module(module_name)
            return getattr(module, attr_name)
        if isinstance(entry, type):
            return entry
        resolved = entry()
        if not isinstance(resolved, type):
            raise TypeError("engine invocation receiver resolver must return a class")
        return resolved
