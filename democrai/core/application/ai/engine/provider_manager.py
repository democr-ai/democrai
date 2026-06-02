from typing import Any, Dict, MutableMapping, Type

from democrai.core.application.ai.engine.runtime import EngineRuntimeProvider
from democrai.core.application.ai.engine.runtime.environment import runtime_config_signature
from democrai.core.application.ai.engine.base.audio import BaseSTTProvider, BaseTTSProvider
from democrai.core.application.ai.engine.base.cv import BaseCvProvider
from democrai.core.application.ai.engine.base.kg import KGProvider
from democrai.core.application.ai.engine.base.llm import LLMProvider
from democrai.core.application.ai.engine.manifests import get_engine_manifest
from democrai.core.runtime.foundation.app import app_ctx


class GenAIManager:
    """
    Manager to register and instantiate GenAI providers (LLM, STT, TTS, CV).

    Engines are discovered once and registered by capability;
    runtime wrapping is applied at provider resolution time.
    """

    _KIND_ALIASES = {
        "detection": "cv",
    }

    _KIND_ERROR_PREFIX = {
        "llm": "LLM",
        "stt": "STT",
        "tts": "TTS",
        "cv": "CV",
        "kg": "KG",
    }

    def __init__(self):
        self._llm_providers: Dict[str, Type[LLMProvider]] = {}
        self._stt_providers: Dict[str, Type[BaseSTTProvider]] = {}
        self._tts_providers: Dict[str, Type[BaseTTSProvider]] = {}
        self._cv_providers: Dict[str, Type[BaseCvProvider]] = {}
        self._kg_providers: Dict[str, Type[KGProvider]] = {}

        self._providers_by_kind: dict[str, MutableMapping[str, Type[Any]]] = {
            "llm": self._llm_providers,
            "stt": self._stt_providers,
            "tts": self._tts_providers,
            "cv": self._cv_providers,
            "kg": self._kg_providers,
        }

        self._instances: Dict[str, Any] = {}
        self._active_models: Dict[str, str] = {}  # instance_id -> model_name
        self._instance_config_signatures: Dict[str, str] = {}

    @staticmethod
    def _config_signature(config: dict[str, Any]) -> str:
        return runtime_config_signature(config)

    def unload_model(self, instance_id: str):
        """Unsets an instance and attempts to free memory."""
        if instance_id in self._instances:
            model_name = self._active_models.get(instance_id, "unknown")
            app_ctx().logger.info(
                f"[GenAI] Unloading model: {model_name} ({instance_id})"
            )

            instance = self._instances[instance_id]
            if hasattr(instance, "cleanup"):
                instance.cleanup()

            del self._instances[instance_id]
            if instance_id in self._active_models:
                del self._active_models[instance_id]
            if instance_id in self._instance_config_signatures:
                del self._instance_config_signatures[instance_id]

            import gc

            gc.collect()

    def has_loaded_instance(self, instance_id: str) -> bool:
        return instance_id in self._instances

    def get_loaded_instance(self, instance_id: str) -> Any | None:
        return self._instances.get(instance_id)

    def list_loaded_instance_ids(self) -> list[str]:
        return list(self._instances.keys())

    def provider_instance_id(self, name: str, config: dict[str, Any]) -> str:
        manifest = get_engine_manifest(name) or {}
        provider_definition = (
            dict(manifest.get("provider"))
            if isinstance(manifest.get("provider"), dict)
            else {}
        )
        provider_kind = self._normalize_kind(provider_definition.get("kind"))
        return self._instance_key(kind=provider_kind, name=name, config=config)

    def loaded_instance_matches_config(self, name: str, config: dict[str, Any]) -> bool:
        instance_id = self.provider_instance_id(name, config)
        if instance_id not in self._instances:
            return False
        return self._instance_config_signatures.get(instance_id) == self._config_signature(
            config
        )

    def shutdown(self):
        """Unload all active models."""
        instance_ids = list(self._instances.keys())
        for iid in instance_ids:
            self.unload_model(iid)
        self._instances.clear()
        self._active_models.clear()
        self._instance_config_signatures.clear()

    def register_llm_provider(self, name: str, provider_cls: Type[LLMProvider]):
        self._llm_providers[name] = provider_cls

    def register_stt_provider(self, name: str, provider_cls: Type[BaseSTTProvider]):
        self._stt_providers[name] = provider_cls

    def register_tts_provider(self, name: str, provider_cls: Type[BaseTTSProvider]):
        self._tts_providers[name] = provider_cls

    def register_cv_provider(self, name: str, provider_cls: Type[BaseCvProvider]):
        self._cv_providers[name] = provider_cls

    def register_kg_provider(self, name: str, provider_cls: Type[KGProvider]):
        self._kg_providers[name] = provider_cls

    def _normalize_kind(self, kind: str | None) -> str:
        normalized = kind or "llm"
        normalized = self._KIND_ALIASES.get(normalized, normalized)
        return normalized if normalized in self._providers_by_kind else "llm"

    def _registry_for_kind(self, kind: str) -> MutableMapping[str, Type[Any]]:
        return self._providers_by_kind[self._normalize_kind(kind)]

    def _instance_key(self, *, kind: str, name: str, config: dict[str, Any]) -> str:
        return f"{kind}_{name}_{config.get('model', 'default')}"

    def _error_prefix(self, kind: str) -> str:
        return self._KIND_ERROR_PREFIX.get(kind, "Provider")

    def _build_runtime_proxy(self, name: str, config: dict[str, Any]) -> Any | None:
        runtime = getattr(app_ctx(), "engine_runtime", None)
        if runtime is None:
            raise RuntimeError("engine_runtime_not_initialized")
        engine_row_id = config.get("_engine_row_id")
        if engine_row_id is None:
            raise RuntimeError("engine_runtime_requires_engine_row_id")
        model_registry_id = config.get("_model_registry_id")
        if model_registry_id is None or int(model_registry_id) <= 0:
            raise RuntimeError("engine_runtime_requires_model_registry_id")
        runtime_payload = {
            key: value
            for key, value in config.items()
            if not key.startswith("_")
            and key not in {"ram", "vram", "options_schema", "test_config", "test_results"}
        }
        return EngineRuntimeProvider(
            engine_row_id=engine_row_id,
            model_registry_id=int(model_registry_id),
            engine_id=name,
            config=runtime_payload,
        )

    def _get_provider_by_kind(self, *, kind: str, name: str, config: dict[str, Any]) -> Any:
        runtime_proxy = self._build_runtime_proxy(name, config)
        if runtime_proxy is not None:
            return runtime_proxy
        raise RuntimeError("engine_runtime_provider_unavailable")

    def get_provider(self, name: str, config: dict) -> LLMProvider:
        """Returns an instance of a provider, dispatching by provider kind."""
        manifest = get_engine_manifest(name) or {}
        provider_definition = (
            dict(manifest.get("provider"))
            if isinstance(manifest.get("provider"), dict)
            else {}
        )
        provider_kind = self._normalize_kind(provider_definition.get("kind"))
        return self._get_provider_by_kind(kind=provider_kind, name=name, config=config)

    def get_cv_provider(self, name: str, config: dict) -> BaseCvProvider:
        return self._get_provider_by_kind(kind="cv", name=name, config=config)

    def get_stt_provider(self, name: str, config: dict) -> BaseSTTProvider:
        return self._get_provider_by_kind(kind="stt", name=name, config=config)

    def get_tts_provider(self, name: str, config: dict) -> BaseTTSProvider:
        return self._get_provider_by_kind(kind="tts", name=name, config=config)

    def get_kg_provider(self, name: str, config: dict) -> KGProvider:
        return self._get_provider_by_kind(kind="kg", name=name, config=config)


# Singleton instance
genai_manager = GenAIManager()
