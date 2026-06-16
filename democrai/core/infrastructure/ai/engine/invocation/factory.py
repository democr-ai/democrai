from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable

from democrai.core.application.ai.engine.invocation import (
    EngineInvocationProvider,
    EngineOrchestratorProvider,
)


ProviderEntry = (
    type[EngineOrchestratorProvider]
    | str
    | Callable[[], type[EngineOrchestratorProvider]]
)


@dataclass(frozen=True)
class _ProviderDefinition:
    entry: ProviderEntry
    receivers: tuple[str, ...] = ()
    requires_shared_response_stream: bool | None = None


class EngineOrchestratorProviderFactory:
    _registry: dict[str, _ProviderDefinition] = {
        "grpc": _ProviderDefinition(
            (
                "democrai.core.infrastructure.ai.engine.invocation.transports.grpc:"
                "EngineOrchestratorClient"
            ),
            receivers=("grpc",),
            requires_shared_response_stream=False,
        ),
        "queue": _ProviderDefinition(
            (
                "democrai.core.infrastructure.ai.engine.invocation.transports.queue:"
                "EngineQueueTransport"
            ),
            receivers=("queue",),
            requires_shared_response_stream=True,
        ),
    }

    @classmethod
    def register(
        cls,
        name: str,
        provider_entry: ProviderEntry,
        *,
        receivers: tuple[str, ...] = (),
        requires_shared_response_stream: bool | None = None,
    ) -> None:
        normalized = str(name).strip().lower()
        cls._registry[normalized] = _ProviderDefinition(
            provider_entry,
            receivers=tuple(receivers),
            requires_shared_response_stream=requires_shared_response_stream,
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
        return issubclass(provider_cls, EngineOrchestratorProvider)

    @classmethod
    def get_provider(
        cls, provider_type: str = "grpc", **kwargs: Any
    ) -> EngineOrchestratorProvider:
        raw = str(provider_type or "grpc").strip() or "grpc"
        definition = cls._definition_for(raw)
        if definition is None:
            raise RuntimeError(f"engine_orchestrator_provider_unknown:{raw}")
        provider_cls = cls._resolve_entry(definition.entry)
        if not issubclass(provider_cls, EngineOrchestratorProvider):
            raise RuntimeError(
                "engine_orchestrator_provider_must_extend_engine_orchestrator_provider"
            )
        return provider_cls(**kwargs)

    @classmethod
    def receiver_names(cls, provider_type: str) -> tuple[str, ...]:
        raw = str(provider_type or "grpc").strip() or "grpc"
        definition = cls._definition_for(raw)
        if definition is None:
            raise RuntimeError(f"engine_orchestrator_provider_unknown:{raw}")
        if definition.receivers:
            return definition.receivers
        provider_cls = cls._resolve_entry(definition.entry)
        receivers = getattr(provider_cls, "receiver_names", ())
        if not isinstance(receivers, tuple):
            raise RuntimeError("engine_orchestrator_provider_receivers_must_be_tuple")
        return receivers

    @classmethod
    def requires_shared_response_stream(cls, provider_type: str) -> bool:
        raw = str(provider_type or "grpc").strip() or "grpc"
        definition = cls._definition_for(raw)
        if definition is None:
            raise RuntimeError(f"engine_orchestrator_provider_unknown:{raw}")
        if definition.requires_shared_response_stream is not None:
            return bool(definition.requires_shared_response_stream)
        provider_cls = cls._resolve_entry(definition.entry)
        return bool(getattr(provider_cls, "requires_shared_response_stream", False))

    @classmethod
    def _definition_for(cls, provider_type: str) -> _ProviderDefinition | None:
        raw = str(provider_type or "").strip()
        definition = cls._registry.get(raw.lower())
        if definition is None and ":" in raw:
            return _ProviderDefinition(raw)
        return definition

    @staticmethod
    def _resolve_entry(entry: ProviderEntry) -> type[EngineOrchestratorProvider]:
        if isinstance(entry, str):
            module_name, _, attr_name = entry.partition(":")
            module = import_module(module_name)
            return getattr(module, attr_name)
        if isinstance(entry, type):
            return entry
        resolved = entry()
        if not isinstance(resolved, type):
            raise TypeError("engine orchestrator provider resolver must return a class")
        return resolved


class EngineInvocationProviderFactory:
    def __init__(self, *, config: Any | None = None) -> None:
        from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
            EngineOrchestratorProviderResolver,
        )

        self._orchestrator = EngineOrchestratorProviderResolver(config=config)

    def provider_for_objective(
        self,
        *,
        objective: str,
        capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
    ) -> EngineInvocationProvider:
        return self._orchestrator.provider_for_objective(
            objective=objective,
            capabilities=capabilities or [],
            prefer_local=prefer_local,
            confirm_swap=confirm_swap,
        )

    def provider_for_model_registry_id(
        self,
        *,
        model_registry_id: int,
        confirm_swap: bool = False,
    ) -> EngineInvocationProvider:
        return self._orchestrator.provider_for_model_registry_id(
            model_registry_id=model_registry_id,
            confirm_swap=confirm_swap,
        )
