from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from democrai.core.application.ai.engine.base.audio import BaseSTTProvider, BaseTTSProvider
from democrai.core.application.ai.engine.base.cv import BaseCvProvider
from democrai.core.application.ai.engine.base.engine import BaseEngine
from democrai.core.application.ai.engine.base.kg import KGProvider
from democrai.core.application.ai.engine.base.llm import LLMProvider
from democrai.core.application.ai.engine.base.llm import current_ai_call_context
from democrai.core.application.ai.output_parsers import ParsedModelOutput
from democrai.core.application.ai.output_parsers import StreamParseState
from democrai.core.application.ai.output_parsers import get_output_parser
from democrai.core.application.ai.output_parsers import list_output_parsers
from democrai.core.application.ai.chat_templates import get_chat_template
from democrai.core.application.ai.chat_templates import list_chat_templates
from democrai.core.application.ai.engine.schemas.completion import (
    ClassificationOptions,
    ClassificationResult,
    CompletionOptions,
    CompletionResponse,
    CompletionUsage,
    ContentPart,
    ContentType,
    Function,
    Message,
    MessageRole,
    RerankOptions,
    RerankResult,
    StreamChunk,
    TokenExtractionResult,
    Tool,
    ToolCall,
)
from democrai.core.application.ai.engine.schemas.kg import (
    ExtractedKnowledgeGraph,
    KGEntity,
    KGExtractionOptions,
    KGRelation,
)
from democrai.core.application.ai.engine.schemas.runtime import (
    EngineMethodResponse,
    EngineStreamFinal,
    EngineUsage,
)
from democrai.core.application.ai.engine.manifests import (
    get_provider_definition,
    list_provider_definitions,
)
from democrai.core.runtime.dependencies.installer_env import is_engine_supported


def provider_requirements(provider_id: str) -> dict[str, Any]:
    """Return public requirements for an engine provider."""
    from democrai.core.application.ai.engine.requirements import (
        provider_requirements as core_provider_requirements,
    )

    return core_provider_requirements(provider_id=provider_id)


def config_has_required_values(
    provider_id: str,
    config: dict[str, Any] | None,
) -> bool:
    """Return whether provider config includes all required values."""
    from democrai.core.application.ai.engine.requirements import (
        config_has_required_values as core_config_has_required_values,
    )

    return core_config_has_required_values(provider_id, config)


class Engines:
    """Expose engine and model-management helpers to modules."""

    def __init__(self, sdk=None) -> None:
        self.sdk = sdk

    async def constants(self) -> dict[str, Any]:
        """Return the shared AI engine/model contract constants."""
        from democrai.core.application.ai.constants import (
            AIDeployment,
            AI_MODEL_CAPABILITIES,
            AI_MODEL_CONFIGURATION_FORM_SCHEMA,
            AI_MODEL_FEATURE_SCHEMAS,
            AI_MODEL_RUNTIME_FORMATTING_SCHEMA,
            AI_MODEL_RUNTIME_CONFIG_SCHEMAS,
            AIModelFormat,
            AIModelSource,
            AIRegistryStatus,
            AI_CONTEXT_POLICIES,
            AI_CONTEXT_POLICY_DEFAULTS,
            AIRuntimeMethod,
        )

        def values(cls: type) -> list[str]:
            return [
                str(value)
                for key, value in vars(cls).items()
                if key.isupper() and isinstance(value, str)
            ]

        return {
            "model_capabilities": list(AI_MODEL_CAPABILITIES),
            "model_configuration_form_schema": AI_MODEL_CONFIGURATION_FORM_SCHEMA,
            "model_feature_schemas": AI_MODEL_FEATURE_SCHEMAS,
            "model_runtime_formatting_schema": AI_MODEL_RUNTIME_FORMATTING_SCHEMA,
            "model_runtime_config_schemas": AI_MODEL_RUNTIME_CONFIG_SCHEMAS,
            "context_policies": list(AI_CONTEXT_POLICIES),
            "context_policy_defaults": AI_CONTEXT_POLICY_DEFAULTS,
            "chat_templates": list_chat_templates(),
            "output_parsers": list_output_parsers(),
            "runtime_methods": values(AIRuntimeMethod),
            "model_formats": values(AIModelFormat),
            "model_sources": values(AIModelSource),
            "deployment": values(AIDeployment),
            "statuses": values(AIRegistryStatus),
        }

    async def get_provider_definition(self, *, provider_id: str) -> dict[str, Any] | None:
        """Return a provider definition by provider id."""
        from democrai.core.application.ai.engine.manifests import get_provider_definition

        return get_provider_definition(provider_id)

    async def list_provider_definitions(
        self,
        *,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        """List provider definitions, optionally filtered by kind."""
        from democrai.core.application.ai.engine.manifests import list_provider_definitions

        return list_provider_definitions(kind=kind)

    async def is_supported(self, *, engine_id: str) -> bool:
        """Return whether an engine is supported in the current runtime."""
        from democrai.core.runtime.dependencies.installer_env import is_engine_supported

        return is_engine_supported(engine_id)

    async def provider_requirements(self, *, provider_id: str) -> dict[str, Any]:
        """Return public requirements for an engine provider."""
        return provider_requirements(provider_id=provider_id)

    async def activation_requirements(
        self,
        *,
        engine_registry_id: int,
    ) -> dict[str, Any]:
        """Return requirements for activating an engine registry row."""
        from democrai.core.application.ai.engine.requirements import (
            activation_requirements,
        )

        return await activation_requirements(engine_registry_id=engine_registry_id)

    async def activate_instance(
        self,
        *,
        engine_registry_id: int,
    ) -> dict[str, Any]:
        """Activate an engine registry row."""
        from democrai.core.application.ai.engine.activation import (
            activate_engine_instance,
        )

        return await activate_engine_instance(engine_registry_id=engine_registry_id)

    async def deactivate_instance(
        self,
        *,
        engine_registry_id: int,
    ) -> dict[str, Any]:
        """Deactivate an engine registry row."""
        from democrai.core.application.ai.engine.activation import (
            deactivate_engine_instance,
        )

        return await deactivate_engine_instance(engine_registry_id=engine_registry_id)

    async def request_install(
        self,
        *,
        engine_id: str,
        force: bool = False,
        requested_by: Optional[dict[str, Any]] = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Publish an install request for an engine."""
        from democrai.core.application.ai.engine.install_events import publish_engine_install_requested

        return await publish_engine_install_requested(
            engine_id=engine_id,
            force=force,
            requested_by=requested_by,
            task_id=task_id,
        )

    async def begin_install(
        self,
        *,
        engine_registry_id: int,
        force: bool = False,
        requested_by: Optional[dict[str, Any]] = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Publish an install request for an engine registry row."""
        from democrai.core.application.ai.engine.install_events import begin_engine_install

        return await begin_engine_install(
            engine_registry_id=engine_registry_id,
            force=force,
            requested_by=requested_by,
            task_id=task_id,
        )

    async def install_status(self, *, engine_registry_id: int) -> dict[str, Any]:
        """Return aggregated install status for an engine registry row."""
        from democrai.core.application.ai.engine.install_events import engine_install_status

        return engine_install_status(engine_registry_id=engine_registry_id)

    async def sync_runtime(self) -> None:
        """Synchronize engine lifecycle state with the runtime engine manager."""
        def _sync() -> None:
            from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
                EngineOrchestratorProviderResolver,
            )

            EngineOrchestratorProviderResolver().provider().sync_active_engines()

        await asyncio.to_thread(_sync)

    async def list_loaded_models(
        self,
        *,
        engine_registry_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        """List engine runtime instances currently loaded in memory."""
        from democrai.core.application.ai.orchestrator import model_orchestrator
        from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
            EngineOrchestratorProviderResolver,
        )

        def _status():
            return EngineOrchestratorProviderResolver().provider().status()

        status = await asyncio.to_thread(_status)
        rows = json.loads(status.active_instances_json or "[]")
        rows = [
            self._annotate_loaded_model(dict(row), model_orchestrator=model_orchestrator)
            for row in rows
        ]
        if engine_registry_id is None:
            return rows
        resolved_id = int(engine_registry_id)
        return [
            row
            for row in rows
            if int(row.get("engine_row_id") or 0) == resolved_id
        ]

    async def list_active_jobs(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List active engine orchestrator jobs."""
        from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
            EngineOrchestratorProviderResolver,
        )

        def _list_active_jobs():
            return EngineOrchestratorProviderResolver().provider().list_active_jobs(
                offset=offset,
                limit=limit,
            )

        return await asyncio.to_thread(_list_active_jobs)

    @staticmethod
    def _annotate_loaded_model(row: dict[str, Any], *, model_orchestrator: Any) -> dict[str, Any]:
        model_registry_id = row.get("model_registry_id")
        if model_registry_id in (None, ""):
            return row
        model = model_orchestrator.get_model_by_registry_id(model_registry_id)
        if model is None:
            return row
        available_model = getattr(model, "available_model", None)
        row["model_registry_id"] = model.id
        row["model_registry_name"] = str(getattr(model, "name", "") or "")
        row["model_display_name"] = str(
            getattr(available_model, "label", "")
            or getattr(available_model, "name", "")
            or getattr(model, "name", "")
            or ""
        )
        return row

    async def unload_loaded_model(
        self,
        *,
        engine_registry_id: int | str,
        model_registry_id: int | str,
    ) -> dict[str, Any]:
        """Unload one loaded model runtime instance from memory."""
        from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
            EngineOrchestratorProviderResolver,
        )

        def _unload_model():
            return EngineOrchestratorProviderResolver().provider().unload_model(
                engine_registry_id=engine_registry_id,
                model_registry_id=model_registry_id,
            )

        unloaded = await asyncio.to_thread(_unload_model)
        return {"status": "ok", "unloaded": bool(unloaded)}

    async def stop_engine(self, *, engine_registry_id: int | str) -> dict[str, Any]:
        """Stop all loaded models for one engine runtime instance."""
        from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
            EngineOrchestratorProviderResolver,
        )

        def _stop_engine():
            return EngineOrchestratorProviderResolver().provider().stop_engine(
                engine_registry_id=engine_registry_id
            )

        stopped = await asyncio.to_thread(_stop_engine)
        return {"status": "ok", "stopped": bool(stopped)}

    async def check_runtime_config(
        self,
        *,
        engine_id: str,
        config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Validate runtime config for an engine."""
        from democrai.core.application.ai.engine.runtime import check_engine_runtime_config

        return check_engine_runtime_config(
            engine_id=engine_id,
            config=config,
        )

    async def evaluate_model_resources(
        self,
        *,
        model_registry_id: int | str,
        context_length: int,
        runtime_overrides: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Estimate resources for a registered model against the active runtime."""
        from democrai.core.application.ai.engine.model_resources import (
            evaluate_model_registry_resources,
        )

        return evaluate_model_registry_resources(
            model_registry_id,
            context_length=context_length,
            runtime_overrides=runtime_overrides,
        )

    async def check_ready(
        self,
        *,
        engine_id: str,
    ) -> dict[str, Any]:
        """Return whether an engine runtime is installed and importable."""
        from democrai.core.application.ai.engine.runtime import check_engine_ready_runtime

        return check_engine_ready_runtime(engine_id=engine_id)

    async def model_source_modes(self, *, engine_id: str) -> list[str]:
        """Return supported model source modes for an engine."""
        from democrai.core.application.ai.models.catalog import engine_model_source_modes

        return engine_model_source_modes(engine_id)

    async def get_model_management(self, *, engine_id: str) -> dict[str, Any]:
        """Return model-management metadata for an engine."""
        from democrai.core.application.ai.models.catalog import get_engine_model_management

        return get_engine_model_management(engine_id)

    async def get_model_schema(
        self,
        *,
        engine_id: str,
        source_mode: str,
    ) -> dict[str, Any]:
        """Return the model schema for an engine/source-mode pair."""
        from democrai.core.application.ai.models.catalog import get_engine_model_schema

        return get_engine_model_schema(engine_id, source_mode=source_mode)

    async def list_models(self, *, engine_id: str) -> list[dict[str, Any]]:
        """List registered models for an engine instance."""
        from democrai.core.application.ai.models.instance_models import (
            list_registered_models_for_engine,
        )

        return list_registered_models_for_engine(engine_id)

    async def list_available_models(self, *, engine_id: str) -> list[dict[str, Any]]:
        """List models available to an engine instance."""
        from democrai.core.application.ai.models.instance_models import (
            list_available_models_for_engine,
        )

        return await list_available_models_for_engine(engine_id)

    async def list_catalog_models(self, *, engine_id: str) -> list[dict[str, Any]]:
        """List static catalog models declared by an engine provider."""
        from democrai.core.application.ai.models.catalog import list_engine_models

        return list_engine_models(engine_id)

    async def resolve_model(
        self,
        *,
        engine_id: str,
        model_id: str | None = None,
        source_mode: str = "catalog",
        definition: dict[str, Any] | None = None,
        artifact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve a model definition for an engine and source mode."""
        from democrai.core.application.ai.models.catalog import resolve_engine_model

        return resolve_engine_model(
            engine_id,
            model_id=model_id,
            source_mode=source_mode,
            definition=definition,
            artifact=artifact,
        )

    async def download_model(
        self,
        *,
        catalog_id: str,
        confirmed_resource_warning: bool = False,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Download a catalog model into shared storage and register it as available."""
        from democrai.core.application.ai.models.catalog_download import (
            ModelStorageOps,
            download_model,
        )

        if self.sdk is None:
            raise RuntimeError("sdk_context_required")
        return await download_model(
            catalog_id,
            storage=ModelStorageOps(
                add_model=self.sdk.media.add_model,
                add_model_from_source=self.sdk.media.add_model_from_source,
                view=self.sdk.media.view,
                delete=self.sdk.media.delete,
            ),
            confirmed_resource_warning=confirmed_resource_warning,
            task_id=task_id,
        )

    async def import_model_from_source(
        self,
        *,
        source: dict[str, Any],
        model: dict[str, Any],
    ) -> dict[str, Any]:
        """Import a model artifact already uploaded into media storage."""
        from democrai.core.application.ai.models.catalog_download import (
            ModelStorageOps,
            import_model_from_source,
        )

        if self.sdk is None:
            raise RuntimeError("sdk_context_required")
        return import_model_from_source(
            source=source,
            model=model,
            storage=ModelStorageOps(
                add_model=self.sdk.media.add_model,
                add_model_from_source=self.sdk.media.add_model_from_source,
                view=self.sdk.media.view,
                delete=self.sdk.media.delete,
            ),
        )

    async def download_model_from_source(
        self,
        *,
        source: dict[str, Any],
        model: dict[str, Any],
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Download a remote model source into shared storage and register it."""
        from democrai.core.application.ai.models.catalog_download import (
            ModelStorageOps,
            download_model_from_source,
        )

        if self.sdk is None:
            raise RuntimeError("sdk_context_required")
        return await download_model_from_source(
            source=source,
            model=model,
            storage=ModelStorageOps(
                add_model=self.sdk.media.add_model,
                add_model_from_source=self.sdk.media.add_model_from_source,
                view=self.sdk.media.view,
                delete=self.sdk.media.delete,
            ),
            task_id=task_id,
        )

    async def delete_available_model(
        self,
        *,
        available_model_id: int | str,
    ) -> dict[str, Any]:
        """Delete an available model, its bindings, and its stored artifacts."""
        from democrai.core.application.ai.models.catalog_download import (
            ModelStorageOps,
            delete_available_model,
        )

        if self.sdk is None:
            raise RuntimeError("sdk_context_required")
        return delete_available_model(
            int(available_model_id),
            storage=ModelStorageOps(
                add_model=self.sdk.media.add_model,
                add_model_from_source=self.sdk.media.add_model_from_source,
                view=self.sdk.media.view,
                delete=self.sdk.media.delete,
            ),
        )
