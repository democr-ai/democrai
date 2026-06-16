from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.invocation import (
    EngineInvocationProvider,
    EngineOrchestratorProvider,
)
from democrai.core.infrastructure.ai.engine.invocation.factory import (
    EngineOrchestratorProviderFactory,
)
from democrai.core.runtime.foundation.app import app_ctx


class EngineOrchestratorProviderResolver:
    CONFIG_KEY = "ai.engine_orchestrator.provider.type"
    LEGACY_CONFIG_KEY = "ai.engine_orchestrator.invocation.provider"
    _queue_config_validated_for: int | None = None

    def __init__(self, *, config: Any | None = None) -> None:
        self._config = config

    @classmethod
    def provider_name_from_config(cls, config: Any | None = None) -> str:
        getter = getattr(config, "get", None)
        legacy = getter(cls.LEGACY_CONFIG_KEY, None) if callable(getter) else None
        if legacy is not None:
            raise RuntimeError(
                "engine_orchestrator_legacy_provider_config:"
                f"remove {cls.LEGACY_CONFIG_KEY}; use {cls.CONFIG_KEY}"
            )
        raw = getter(cls.CONFIG_KEY, "grpc") if callable(getter) else "grpc"
        name = str(raw or "grpc").strip()
        if ":" not in name:
            name = name.lower()
        if not EngineOrchestratorProviderFactory.has_provider(name):
            raise RuntimeError(f"engine_orchestrator_provider_unknown:{name}")
        return name

    @classmethod
    def provider_params_from_config(cls, config: Any | None = None) -> dict[str, Any]:
        getter = getattr(config, "get", None)
        raw = getter("ai.engine_orchestrator.provider.params", {}) if callable(getter) else {}
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise RuntimeError("engine_orchestrator_provider_params_must_be_mapping")
        return dict(raw)

    @classmethod
    def receiver_names_from_config(cls, config: Any | None = None) -> tuple[str, ...]:
        name = cls.provider_name_from_config(config)
        return EngineOrchestratorProviderFactory.receiver_names(name)

    @classmethod
    def requires_shared_response_stream_from_config(
        cls, config: Any | None = None
    ) -> bool:
        name = cls.provider_name_from_config(config)
        return EngineOrchestratorProviderFactory.requires_shared_response_stream(name)

    def provider_for_objective(
        self,
        *,
        objective: str,
        capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
    ) -> EngineInvocationProvider:
        return self._provider(
            selector_type="objective",
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
        return self._provider(
            selector_type="model_registry_id",
            model_registry_id=model_registry_id,
            confirm_swap=confirm_swap,
        )

    def provider(self) -> EngineOrchestratorProvider:
        config = self._resolved_config()
        provider_name = self.provider_name_from_config(config)
        provider_params = self.provider_params_from_config(config)
        return EngineOrchestratorProviderFactory.get_provider(
            provider_name, **provider_params
        )

    def _provider(
        self,
        *,
        selector_type: str,
        model_registry_id: int | None = None,
        objective: str | None = None,
        capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
    ) -> EngineInvocationProvider:
        from democrai.core.infrastructure.ai.engine.invocation.providers.orchestrated import (
            OrchestratedEngineProvider,
        )

        return OrchestratedEngineProvider(
            selector_type=selector_type,
            model_registry_id=model_registry_id,
            objective=objective,
            capabilities=capabilities or [],
            prefer_local=prefer_local,
            confirm_swap=confirm_swap,
            orchestrator_provider=self.provider(),
        )

    def _resolved_config(self) -> Any:
        return self._config or app_ctx().config
