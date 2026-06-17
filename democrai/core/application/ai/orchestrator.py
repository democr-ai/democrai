import asyncio
import copy
import json
from typing import Callable, List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.preferences import get_preference
from democrai.core.application.ai.engine.config_access import get_engine_runtime_config
from democrai.core.infrastructure.database.models import (
    EngineRegistry,
    ModelCapabilityPriority,
    ModelRegistry,
    ObjectiveMapping,
)
from democrai.core.application.ai.models.catalog import get_engine_model
from democrai.core.application.ai.models.hardware_compatibility import HardwareValidator
from democrai.core.application.ai.engine.provider_manager import genai_manager
from democrai.core.application.ai.engine.manifests import get_provider_definition
from democrai.core.application.ai.engine.runtime.manager import get_engine_runtime
from democrai.core.application.ai.engine.runtime.environment import (
    runtime_config_signature,
)
from democrai.core.application.ai.engine.orchestrator.config import (
    EngineOrchestratorConfig,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.platform.utils.system import get_resource_monitor
from democrai.core.application.ai.engine.base.llm import ai_call_context
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.models.selection_policy import (
    annotate_provider,
    effective_policy_mode,
    engine_fit_score,
    is_local_provider,
    provider_capabilities,
)
from democrai.core.application.ai.constants import (
    AI_CONTEXT_POLICY_DEFAULTS,
    AIContextPolicy,
)
from democrai.core.platform.utils.identity import to_int_or_zero


_RUNTIME_TRANSITION_SEMAPHORES: dict[tuple[int, int], asyncio.Semaphore] = {}

async def _emit_orchestrator_event(
    event_hook: Callable[[str, Dict[str, Any]], Any] | None,
    name: str,
    payload: Dict[str, Any],
) -> None:
    if event_hook is None:
        return
    result = event_hook(name, payload)
    if asyncio.iscoroutine(result):
        await result


async def _record_runtime_transition(
    *,
    step_name: str,
    input: Dict[str, Any],
    event_hook: Callable[[str, Dict[str, Any]], Any] | None,
    event_name: str,
    event_payload: Dict[str, Any],
    operation: Callable[[], Any],
) -> Any:
    async with _runtime_transition_semaphore():
        async with ai_pipeline_step(
            type="engine_runtime",
            name=step_name,
            input=input,
        ) as step:
            await _emit_orchestrator_event(event_hook, event_name, event_payload)
            result = operation()
            if asyncio.iscoroutine(result):
                result = await result
            step["output"] = {"ok": True}
            return result


def _runtime_transition_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    config = app_ctx().config
    worker_count = EngineOrchestratorConfig.load(
        config
    ).runtime_transition_worker_count
    key = (id(loop), worker_count)
    semaphore = _RUNTIME_TRANSITION_SEMAPHORES.get(key)
    if semaphore is None:
        semaphore = asyncio.Semaphore(worker_count)
        _RUNTIME_TRANSITION_SEMAPHORES[key] = semaphore
    return semaphore


async def _invocation_provider_result(
    *,
    selector_type: str,
    model_registry_id: int | None = None,
    objective: str | None = None,
    required_capabilities: Optional[List[str]] = None,
    prefer_local: Optional[bool] = None,
    confirm_swap: bool = False,
) -> Dict[str, Any]:
    from democrai.core.infrastructure.ai.engine.invocation.factory import (
        EngineInvocationProviderFactory,
    )

    factory = EngineInvocationProviderFactory()
    if selector_type == "model_registry_id":
        provider = factory.provider_for_model_registry_id(
            model_registry_id=int(model_registry_id or 0),
            confirm_swap=confirm_swap,
        )
    else:
        provider = factory.provider_for_objective(
            objective=objective or "",
            capabilities=required_capabilities or [],
            prefer_local=prefer_local,
            confirm_swap=confirm_swap,
        )
    try:
        validation = await provider.validate()
    except Exception as exc:
        return {"status": "error", "error": str(exc).split("\n", 1)[0]}
    if validation.get("status") != "ok":
        return validation
    return {"status": "ok", "provider": provider}


class ModelOrchestrator:
    """
    Orchestrates GenAI models based on objectives, system resources, and user preferences.
    """

    def __init__(self, session_factory: Callable[[], Session] | None = None):
        self._session_factory = session_factory or SessionLocal
        self.hardware = HardwareValidator()

    @staticmethod
    def _provider_method_batch_sizes(provider_id: str) -> dict[str, Any]:
        definition = get_provider_definition(provider_id) or {}
        value = definition.get("runtime_batch_sizes")
        return value if isinstance(value, dict) else {}

    def _prepare_runtime_provider(
        self,
        *,
        provider: Any,
        instance_id: str,
        provider_id: str,
        model_info: Any,
    ) -> Any:
        setattr(provider, "_democrai_instance_id", instance_id)
        setattr(
            provider,
            "_democrai_method_batch_sizes",
            self._provider_method_batch_sizes(provider_id),
        )
        if model_info is not None and model_info.engine is not None:
            try:
                engine_config = get_engine_runtime_config(
                    engine_row_id=model_info.engine.id
                )
                concurrency_enabled = engine_config.get("concurrency_enabled", False)
                concurrency_limit = engine_config.get("concurrency_limit", 1)
                setattr(provider, "_democrai_concurrency_enabled", concurrency_enabled)
                setattr(provider, "_democrai_concurrency_limit", concurrency_limit)

                app_ctx().logger.debug(
                    f"[ORCHESTRATOR] ORCHESTRATOR CALL conc: {concurrency_enabled} - limit: {concurrency_limit}; PROVIDER: {provider_id}\n",
                    name="ORCHESTRATOR",
                )
            except Exception as exc:
                setattr(provider, "_democrai_concurrency_enabled", False)
                setattr(provider, "_democrai_concurrency_limit", 1)
                app_ctx().logger.debug(
                    f"[ORCHESTRATOR] ORCHESTRATOR CALL ERROR ENGINE: {getattr(model_info.engine, 'id', '?')}; ERROR: {type(exc).__name__}\n",
                    name="ORCHESTRATOR",
                )
        else:
            setattr(provider, "_democrai_concurrency_enabled", False)
            setattr(provider, "_democrai_concurrency_limit", 1)

        self._annotate_provider(
            provider, model_info=model_info, engine_name=provider_id
        )
        return provider

    @staticmethod
    def runtime_config_payload(config: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in config.items()
            if not key.startswith("_")
            and key
            not in {"ram", "vram", "options_schema", "test_config", "test_results"}
        }

    @classmethod
    def runtime_config_signature(cls, config: dict[str, Any]) -> str:
        return runtime_config_signature(config)

    @classmethod
    def active_runtime_instance(
        cls,
        *,
        provider_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        active_instances = app_ctx().engine_runtime.active_instances
        engine_row_id = config.get("_engine_row_id")
        model_registry_id = config.get("_model_registry_id")
        signature = cls.runtime_config_signature(config)
        for item in active_instances():
            if item.get("status") != "running":
                continue
            if item.get("engine_id") != provider_id:
                continue
            if engine_row_id is not None and item.get("engine_row_id") != engine_row_id:
                continue
            if (
                model_registry_id is not None
                and item.get("model_registry_id") != model_registry_id
            ):
                continue
            if item.get("config_signature") == signature:
                return item
        return None

    async def _ensure_runtime_model_ready(
        self,
        *,
        provider_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        engine_row_id = config.get("_engine_row_id")
        if engine_row_id is None:
            return self.active_runtime_instance(provider_id=provider_id, config=config)
        model_registry_id = config.get("_model_registry_id")
        if model_registry_id is None or int(model_registry_id) <= 0:
            raise RuntimeError("engine_runtime_requires_model_registry_id")
        runtime_config = self.runtime_config_payload(config)
        try:
            await asyncio.to_thread(
                get_engine_runtime().ensure_running,
                engine_row_id=engine_row_id,
                engine_id=provider_id,
                config=runtime_config,
                model_registry_id=int(model_registry_id),
            )
        except Exception as exc:
            resolved = await self._retry_runtime_context_config(
                provider_id=provider_id,
                config=config,
                engine_row_id=engine_row_id,
                model_registry_id=int(model_registry_id),
                error=exc,
            )
            if not resolved:
                raise
        return self.active_runtime_instance(provider_id=provider_id, config=config)

    async def _retry_runtime_context_config(
        self,
        *,
        provider_id: str,
        config: dict[str, Any],
        engine_row_id: int,
        model_registry_id: Any,
        error: Exception,
    ) -> bool:
        candidates = self._runtime_context_retry_candidates(
            provider_id=provider_id,
            config=config,
            error=error,
        )
        if not candidates:
            return False
        last_error = error
        for candidate in candidates:
            runtime_config = self.runtime_config_payload(candidate)
            try:
                await asyncio.to_thread(
                    get_engine_runtime().ensure_running,
                    engine_row_id=engine_row_id,
                    engine_id=provider_id,
                    config=runtime_config,
                    model_registry_id=int(model_registry_id),
                )
            except Exception as exc:
                last_error = exc
                continue
            config.clear()
            config.update(candidate)
            self.apply_provider_runtime_aliases(provider_id, config)
            return True
        raise last_error

    @classmethod
    def _runtime_context_retry_candidates(
        cls,
        *,
        provider_id: str,
        config: dict[str, Any],
        error: Exception,
    ) -> list[dict[str, Any]]:
        """
        SET RUNTIME CONTEXT POLICY
        TO MOVE IN ENGINES

        @todo
        """
        provider = provider_id
        policy = config.get("context_policy") or ""
        if policy == AIContextPolicy.STRICT:
            return []
        context_length = cls._runtime_context_length(provider, config)
        if context_length is None or context_length <= 2048:
            return []
        candidates: list[dict[str, Any]] = []
        if policy in {AIContextPolicy.OFFLOAD, AIContextPolicy.OFFLOAD_THEN_REDUCE}:
            offloaded = copy.deepcopy(config)
            if provider == "llamacpp":
                llama_kwargs = offloaded.get("llama_kwargs") or {}
                if llama_kwargs.get("offload_kqv") is not False:
                    llama_kwargs["offload_kqv"] = False
                    offloaded["llama_kwargs"] = llama_kwargs
                    cls._set_runtime_context_length(provider, offloaded, context_length)
                    candidates.append(offloaded)
            elif provider == "vllm" and offloaded.get("kv_offloading_size") in (
                None,
                "",
            ):
                kv_offload_gb = cls._runtime_cpu_offload_gb(default=8)
                if kv_offload_gb > 0:
                    offloaded["kv_offloading_size"] = kv_offload_gb
                    offloaded.setdefault("kv_offloading_backend", "native")
                    offloaded.setdefault("kv_cache_dtype", "auto")
                    offloaded.setdefault("enforce_eager", True)
                    offloaded.setdefault(
                        "gpu_memory_utilization", offloaded.get("gpu_util", 0.9)
                    )
                    offloaded.setdefault(
                        "gpu_util", offloaded.get("gpu_memory_utilization")
                    )
                    cls._set_runtime_context_length(provider, offloaded, context_length)
                    candidates.append(offloaded)
            elif provider == "onnx":
                cls._set_runtime_context_length(provider, offloaded, context_length)
            if policy == AIContextPolicy.OFFLOAD:
                return candidates
        if policy in {
            AIContextPolicy.AUTO_REDUCE,
            AIContextPolicy.OFFLOAD_THEN_REDUCE,
        }:
            current = context_length
            while current > 2048:
                current = max(2048, current // 2)
                reduced = copy.deepcopy(config)
                cls._set_runtime_context_length(provider, reduced, current)
                if (
                    not candidates
                    or cls._runtime_context_length(provider, candidates[-1]) != current
                ):
                    candidates.append(reduced)
        return candidates

    @staticmethod
    def _runtime_cpu_offload_gb(*, default: int) -> int:
        resources = get_resource_monitor().get_resources()
        ram_free_mb = resources.get("ram_free_mb") or 0
        if ram_free_mb <= 0:
            return default
        reserved_mb = 8192
        available_mb = max(0, ram_free_mb - reserved_mb)
        return max(0, min(default, available_mb // 1024))

    @staticmethod
    def _annotate_provider(
        provider: Any, *, model_info: Any, engine_name: str | None = None
    ) -> Any:
        return annotate_provider(
            provider, model_info=model_info, engine_name=engine_name
        )

    @staticmethod
    def _model_display_name(model_info: Any) -> str:
        available_model = model_info.available_model
        label = available_model.label if available_model is not None else ""
        if label:
            return label
        extra_config = model_info.extra_config
        if isinstance(extra_config, dict):
            binding_label = extra_config.get("binding_label") or ""
            if binding_label:
                return binding_label
        return model_info.name

    def _models_for_objective_selection(
        self,
        objective: str,
        *,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: Optional[bool] = None,
    ) -> tuple[list[ModelRegistry], set[int]]:
        required = [objective] + [cap for cap in (required_capabilities or []) if cap]
        policy = self._load_selection_policy()
        with self._session_factory() as session:
            mapping = (
                session.query(ObjectiveMapping).filter_by(objective=objective).first()
            )
            all_models = (
                session.query(ModelRegistry)
                .options(
                    joinedload(ModelRegistry.engine),
                    joinedload(ModelRegistry.available_model),
                )
                .join(ModelRegistry.engine)
                .filter(ModelRegistry.status == "active")
                .filter(EngineRegistry.status == "active")
                .all()
            )
            mapped_model = mapping.model if mapping else None
            candidates = self._filter_candidate_models(
                all_models,
                required_capabilities=required,
            )
            if mapped_model is not None and mapped_model not in candidates:
                candidates.insert(0, mapped_model)
            if not candidates:
                return [], set()
            capability_priorities = self._load_capability_priorities(
                session,
                required_capabilities=required,
            )
            scored = sorted(
                candidates,
                key=lambda model: (
                    0 if model.id in capability_priorities else 1,
                    capability_priorities.get(model.id, 10**9),
                    -self._score_model_candidate(
                        model,
                        objective=objective,
                        required_capabilities=required,
                        policy=policy,
                        mapped_model=mapped_model,
                        prefer_local=prefer_local,
                    ),
                ),
            )
            priority_model_ids = set(capability_priorities)
            session.expunge_all()
            return scored, priority_model_ids
        return [], set()

    def get_models_for_objective(
        self,
        objective: str,
        *,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: Optional[bool] = None,
    ) -> list[ModelRegistry]:
        """
        Returns the ordered models associated with a specific objective.
        """
        models, _priority_model_ids = self._models_for_objective_selection(
            objective,
            required_capabilities=required_capabilities,
            prefer_local=prefer_local,
        )
        return models

    def get_model_for_objective(
        self,
        objective: str,
        *,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: Optional[bool] = None,
    ) -> Optional[ModelRegistry]:
        """
        Returns the model associated with a specific objective.
        """
        models = self.get_models_for_objective(
            objective,
            required_capabilities=required_capabilities,
            prefer_local=prefer_local,
        )
        return models[0] if models else None

    def get_quota_available_model_for_objective(
        self,
        objective: str,
        *,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: Optional[bool] = None,
        request_context: Optional[dict[str, Any]] = None,
    ) -> tuple[Optional[ModelRegistry], bool]:
        models, priority_model_ids = self._models_for_objective_selection(
            objective,
            required_capabilities=required_capabilities,
            prefer_local=prefer_local,
        )
        if not models:
            return None, False
        if not isinstance(request_context, dict) or not request_context:
            return models[0], False

        prioritized = [model for model in models if model.id in priority_model_ids]
        if not prioritized:
            return models[0], False
        candidates = prioritized

        from democrai.core.application.ai.engine.quotas import check_engine_quota

        user_id = to_int_or_zero(request_context.get("user")) or None
        quota_candidates_checked = False
        for model in candidates:
            engine = getattr(model, "engine", None)
            engine_row_id = to_int_or_zero(getattr(engine, "id", None))
            if engine_row_id <= 0:
                return model, False
            decision = check_engine_quota(
                engine_registry_id=engine_row_id,
                user_id=user_id,
                request_context=request_context,
            )
            if decision.allowed:
                return model, False
            if decision.reason != "engine_quota_exceeded":
                return model, False
            quota_candidates_checked = True
        return None, quota_candidates_checked

    async def get_provider_for_objective(
        self,
        objective: str,
        confirm_swap: bool = False,
        *,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: Optional[bool] = None,
        event_hook: Callable[[str, Dict[str, Any]], Any] | None = None,
    ) -> Dict[str, Any]:
        """
        High-level entry point to get a GenAI provider ready for an objective.
        Returns a dict with {'status': 'ok'|'need_confirmation'|'error', 'provider': ..., 'to_unload': []}
        """
        return await _invocation_provider_result(
            selector_type="objective",
            objective=objective,
            required_capabilities=required_capabilities,
            prefer_local=prefer_local,
            confirm_swap=confirm_swap,
        )

    async def _resolve_runtime_provider_for_objective(
        self,
        objective: str,
        confirm_swap: bool = False,
        *,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: Optional[bool] = None,
        request_context: Optional[dict[str, Any]] = None,
        event_hook: Callable[[str, Dict[str, Any]], Any] | None = None,
    ) -> Dict[str, Any]:
        model_info, quota_exhausted = self.get_quota_available_model_for_objective(
            objective,
            required_capabilities=required_capabilities,
            prefer_local=prefer_local,
            request_context=request_context,
        )
        if not model_info:
            if quota_exhausted:
                return {
                    "status": "error",
                    "error": f"engine_quota_exhausted_for_objective:{objective}",
                }
            return {
                "status": "error",
                "error": f"no_model_configured_for_objective:{objective}",
            }

        ram_needed, vram_needed = self.memory_requirements_mb(model_info)
        config = self.build_provider_config(model_info)
        config.setdefault("model", model_info.name)
        instance_id = genai_manager.provider_instance_id(
            model_info.engine.provider,
            config,
        )

        # 1. Check if model is already loaded with the same runtime config
        active_runtime = self.active_runtime_instance(
            provider_id=model_info.engine.provider,
            config=config,
        )
        if active_runtime is not None:
            provider = genai_manager.get_provider(model_info.engine.provider, config)
            provider = self._prepare_runtime_provider(
                provider=provider,
                instance_id=instance_id,
                provider_id=model_info.engine.provider,
                model_info=model_info,
            )
            return {
                "status": "ok",
                "provider": provider,
                "runtime_instance": active_runtime,
            }
        if genai_manager.has_loaded_instance(instance_id):
            genai_manager.unload_model(instance_id)

        # 2. Check Resources
        resources = get_resource_monitor().get_resources()

        if (
            resources["vram_free_mb"] < vram_needed
            or resources["ram_free_mb"] < ram_needed
        ):
            # Need to unload something
            to_unload = self._find_unload_candidates(vram_needed, ram_needed)

            if not confirm_swap:
                return {
                    "status": "need_confirmation",
                    "model_to_load": self._model_display_name(model_info),
                    "to_unload": to_unload,
                }

            unload_payload = {
                "model_to_load": self._model_display_name(model_info),
                "to_unload": to_unload,
            }
            await _record_runtime_transition(
                step_name="engine_runtime.unload",
                input=unload_payload,
                event_hook=event_hook,
                event_name="unloading",
                event_payload=unload_payload,
                operation=lambda: self._unload_candidates_async(to_unload),
            )

        # 3. Resolve model runtime
        load_payload = {
            "model_to_load": self._model_display_name(model_info),
            "model_registry_id": model_info.id,
            "engine": model_info.engine.provider,
        }
        runtime_instance = await _record_runtime_transition(
            step_name="engine_runtime.load",
            input=load_payload,
            event_hook=event_hook,
            event_name="loading",
            event_payload=load_payload,
            operation=lambda: self._ensure_runtime_model_ready(
                provider_id=model_info.engine.provider,
                config=config,
            ),
        )
        provider = genai_manager.get_provider(model_info.engine.provider, config)

        provider = self._prepare_runtime_provider(
            provider=provider,
            instance_id=instance_id,
            provider_id=model_info.engine.provider,
            model_info=model_info,
        )
        return {
            "status": "ok",
            "provider": provider,
            "runtime_instance": runtime_instance,
        }

    def get_model_by_registry_id(
        self, model_registry_id: int
    ) -> Optional[ModelRegistry]:
        if model_registry_id <= 0:
            return None
        with self._session_factory() as session:
            model = (
                session.query(ModelRegistry)
                .options(
                    joinedload(ModelRegistry.engine),
                    joinedload(ModelRegistry.available_model),
                )
                .join(ModelRegistry.engine)
                .filter(ModelRegistry.id == model_registry_id)
                .first()
            )
            if model is None:
                return None
            session.expunge_all()
            return model

    async def get_provider_by_model_registry_id(
        self,
        model_registry_id: int,
        confirm_swap: bool = False,
        *,
        event_hook: Callable[[str, Dict[str, Any]], Any] | None = None,
    ) -> Dict[str, Any]:
        model_info = self.get_model_by_registry_id(model_registry_id)
        if not model_info:
            return {
                "status": "error",
                "error": f"model_registry_row_not_found:{model_registry_id}",
            }
        return await _invocation_provider_result(
            selector_type="model_registry_id",
            model_registry_id=model_info.id,
            confirm_swap=confirm_swap,
        )

    async def _resolve_runtime_provider_by_model_registry_id(
        self,
        model_registry_id: int,
        confirm_swap: bool = False,
        *,
        event_hook: Callable[[str, Dict[str, Any]], Any] | None = None,
    ) -> Dict[str, Any]:
        model_info = self.get_model_by_registry_id(model_registry_id)
        if not model_info:
            return {
                "status": "error",
                "error": f"model_registry_row_not_found:{model_registry_id}",
            }
        engine = model_info.engine
        provider_id = engine.provider if engine is not None else ""
        if not provider_id:
            return {
                "status": "error",
                "error": f"model_registry_engine_not_found:{model_registry_id}",
            }
        if model_info.status != "active":
            return {
                "status": "error",
                "error": f"model_registry_row_not_active:{model_registry_id}",
            }
        if engine.status != "active":
            return {
                "status": "error",
                "error": f"engine_registry_row_not_active:{engine.id}",
            }

        ram_needed, vram_needed = self.memory_requirements_mb(model_info)
        config = self.build_provider_config(model_info)
        config.setdefault("model", model_info.name)
        instance_id = genai_manager.provider_instance_id(provider_id, config)
        active_runtime = self.active_runtime_instance(
            provider_id=provider_id,
            config=config,
        )
        if active_runtime is not None:
            provider = genai_manager.get_provider(provider_id, config)
            provider = self._prepare_runtime_provider(
                provider=provider,
                instance_id=instance_id,
                provider_id=provider_id,
                model_info=model_info,
            )
            return {
                "status": "ok",
                "provider": provider,
                "model": model_info,
                "runtime_instance": active_runtime,
            }
        if genai_manager.has_loaded_instance(instance_id):
            genai_manager.unload_model(instance_id)

        resources = get_resource_monitor().get_resources()
        if (
            resources["vram_free_mb"] < vram_needed
            or resources["ram_free_mb"] < ram_needed
        ):
            to_unload = self._find_unload_candidates(vram_needed, ram_needed)
            if not confirm_swap:
                return {
                    "status": "need_confirmation",
                    "model_to_load": self._model_display_name(model_info),
                    "to_unload": to_unload,
                }
            unload_payload = {
                "model_to_load": self._model_display_name(model_info),
                "to_unload": to_unload,
            }
            await _record_runtime_transition(
                step_name="engine_runtime.unload",
                input=unload_payload,
                event_hook=event_hook,
                event_name="unloading",
                event_payload=unload_payload,
                operation=lambda: self._unload_candidates_async(to_unload),
            )

        load_payload = {
            "model_to_load": self._model_display_name(model_info),
            "model_registry_id": model_info.id,
            "engine": provider_id,
        }
        runtime_instance = await _record_runtime_transition(
            step_name="engine_runtime.load",
            input=load_payload,
            event_hook=event_hook,
            event_name="loading",
            event_payload=load_payload,
            operation=lambda: self._ensure_runtime_model_ready(
                provider_id=provider_id,
                config=config,
            ),
        )
        provider = genai_manager.get_provider(provider_id, config)
        provider = self._prepare_runtime_provider(
            provider=provider,
            instance_id=instance_id,
            provider_id=provider_id,
            model_info=model_info,
        )
        return {
            "status": "ok",
            "provider": provider,
            "model": model_info,
            "runtime_instance": runtime_instance,
        }

    async def generate_completion_for_objective(
        self,
        *,
        objective: str,
        messages: Any,
        options: Any,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: Optional[bool] = None,
        request_kind: str = "orchestrator_completion",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        resolved = await self.get_provider_for_objective(
            objective,
            required_capabilities=required_capabilities,
            prefer_local=prefer_local,
        )
        status = resolved.get("status")
        provider = resolved.get("provider")
        if status != "ok" or provider is None:
            raise RuntimeError(
                f"orchestrator_provider_unavailable objective={objective} status={status or '-'}"
            )

        with ai_call_context(
            objective=objective,
            request_kind=request_kind or "orchestrator_completion",
            metadata=metadata or {},
        ):
            return await provider.generate_completion(
                messages=messages, options=options
            )

    @staticmethod
    def _safe_required_memory_mb(value: Any) -> int:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0
        return max(0, int(parsed))

    @classmethod
    def _memory_value_mb(
        cls, requirements: dict[str, Any], base_key: str, fallback: Any
    ) -> int:
        mb_key = f"{base_key}_mb"
        gb_key = f"{base_key}_gb"
        if requirements.get(mb_key) not in (None, ""):
            return cls._safe_required_memory_mb(requirements.get(mb_key))
        if requirements.get(gb_key) not in (None, ""):
            return cls._safe_required_memory_mb(
                float(requirements.get(gb_key) or 0) * 1024
            )
        return cls._safe_required_memory_mb(fallback)

    def _find_unload_candidates(self, vram_needed: int, ram_needed: int) -> List[Any]:
        """
        Identifies which active models should be unloaded to free up resources.
        Simple logic: unload everything until we have enough space.
        """
        candidates: list[Any] = []
        active_instances = app_ctx().engine_runtime.active_instances
        for item in active_instances():
            if item.get("status") != "running":
                continue
            engine_row_id = item.get("engine_row_id")
            if engine_row_id is None:
                continue
            model_registry_id = item.get("model_registry_id")
            if model_registry_id is None:
                continue
            candidates.append(
                {
                    "engine_row_id": engine_row_id,
                    "engine_id": item.get("engine_id"),
                    "model": item.get("model"),
                    "model_registry_id": model_registry_id,
                }
            )
        for inst_id in genai_manager.list_loaded_instance_ids():
            candidates.append(inst_id)
        return candidates

    def _unload_candidates(self, candidates: List[Any]) -> None:
        runtime = app_ctx().engine_runtime
        for candidate in candidates:
            if (
                isinstance(candidate, dict)
                and candidate.get("engine_row_id") is not None
            ):
                runtime.unload_model(
                    engine_row_id=candidate["engine_row_id"],
                    model_registry_id=candidate["model_registry_id"],
                )
                continue
            genai_manager.unload_model(candidate)

    async def _unload_candidates_async(self, candidates: List[Any]) -> None:
        await asyncio.to_thread(self._unload_candidates, candidates)

    def _load_selection_policy(self) -> Dict[str, Any]:
        raw_policy = get_preference("ai.selection.policy", "{}")
        try:
            policy = (
                json.loads(raw_policy)
                if isinstance(raw_policy, str)
                else (raw_policy or {})
            )
        except Exception:
            policy = {}
        if not isinstance(policy, dict):
            policy = {}
        return policy

    @staticmethod
    def _catalog_model_metadata(model: Any) -> dict[str, Any]:
        engine = model.engine
        engine_id = engine.provider if engine is not None else ""
        model_name = model.name
        if not engine_id or not model_name:
            return {}
        resolved = get_engine_model(engine_id, model_name)
        return resolved if isinstance(resolved, dict) else {}

    @classmethod
    def _provider_capabilities(cls, model: Any) -> set[str]:
        metadata = cls._catalog_model_metadata(model)
        capabilities = metadata.get("capabilities")
        if isinstance(capabilities, list):
            return {cap for cap in capabilities if cap}
        return provider_capabilities(model)

    @classmethod
    def memory_requirements_mb(cls, model: Any) -> tuple[int, int]:
        available_model = model.available_model
        requirements = {}
        if available_model is not None:
            available_requirements = available_model.requirements
            if isinstance(available_requirements, dict):
                requirements = available_requirements
        if not requirements:
            metadata = cls._catalog_model_metadata(model)
            requirements = (
                metadata.get("requirements")
                if isinstance(metadata.get("requirements"), dict)
                else {}
            )
        ram_required_mb = cls._memory_value_mb(
            requirements,
            "ram",
            model.ram_required_mb,
        )
        vram_required_mb = cls._memory_value_mb(
            requirements,
            "vram",
            model.vram_required_mb,
        )
        return ram_required_mb, vram_required_mb

    @staticmethod
    def _is_local_provider(provider: str) -> bool:
        return is_local_provider(provider)

    def _filter_candidate_models(
        self,
        models: List[ModelRegistry],
        *,
        required_capabilities: List[str],
    ) -> List[ModelRegistry]:
        required_set = {cap for cap in required_capabilities if cap}
        candidates: list[ModelRegistry] = []
        for model in models:
            capabilities = self._provider_capabilities(model)
            if required_set and not required_set.intersection(capabilities):
                continue
            candidates.append(model)
        return candidates

    def _score_model_candidate(
        self,
        model: ModelRegistry,
        *,
        objective: str,
        required_capabilities: List[str],
        policy: Dict[str, Any],
        mapped_model: Any,
        prefer_local: Optional[bool],
        resources: Any | None = None,
        warm_instances: Any | None = None,
    ) -> int:
        score = 0
        if mapped_model is model:
            score += 200
        capabilities = self._provider_capabilities(model)
        required_set = {cap for cap in required_capabilities if cap}
        score += 25 * len(required_set.intersection(capabilities))

        policy_mode = self._effective_policy_mode(
            policy, objective=objective, prefer_local=prefer_local
        )
        is_local = self._is_local_provider(model.engine.provider)
        if policy_mode == "local":
            score += 60 if is_local else -60
        elif policy_mode == "cloud":
            score += 60 if not is_local else -60
        elif policy_mode == "hybrid":
            score += 10 if is_local else 0

        score += self._engine_fit_score(model.engine.provider, required_set)
        score += 15 if model.is_downloaded else 0
        if model.status not in {
            "available",
            "ready",
            "downloaded",
            "active",
        }:
            score -= 40

        if resources is None:
            resources = self.hardware.get_system_resources()
        if is_local:
            metadata = self._catalog_model_metadata(model)
            requirements = (
                metadata.get("requirements")
                if isinstance(metadata.get("requirements"), dict)
                else {}
            )
            extra_config = model.extra_config or {}
            ram_required_mb, vram_required_mb = self.memory_requirements_mb(model)
            cpu_fallback_allowed = requirements.get(
                "cpu_fallback_allowed",
                extra_config.get("cpu_fallback_allowed", True),
            )
            partial_gpu_offload = requirements.get(
                "partial_gpu_offload",
                extra_config.get("partial_gpu_offload", False),
            )
            if ram_required_mb and resources.ram_gb * 1024 < ram_required_mb:
                score -= 80
            if vram_required_mb:
                if not resources.has_gpu:
                    score -= 20 if cpu_fallback_allowed else 120
                elif resources.vram_gb * 1024 < vram_required_mb:
                    score -= 10 if partial_gpu_offload else 80
        if warm_instances and (model.engine.id, model.id) in warm_instances:
            score += 50
        return score

    def score_selector_for_view(
        self,
        *,
        selector_type: str,
        model_registry_id: Optional[int] = None,
        objective: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: Optional[bool] = None,
        view: Any,
    ) -> Optional[int]:
        """Score how well a node (described by ``view``) can serve a selector.

        Used by placement: every orchestrator evaluates each
        active node — itself included, through its own published view — with
        the same scoring used for local model selection. Returns the best
        candidate score, or None when no active model matches the selector.
        ``view`` must expose ``ram_gb``/``vram_gb``/``has_gpu`` (free capacity)
        and ``warm_instances`` as (engine_row_id, model_registry_id) pairs.
        """
        policy = self._load_selection_policy()
        warm_instances = getattr(view, "warm_instances", None)
        with self._session_factory() as session:
            if selector_type == "model_registry_id":
                model = (
                    session.query(ModelRegistry)
                    .options(
                        joinedload(ModelRegistry.engine),
                        joinedload(ModelRegistry.available_model),
                    )
                    .join(ModelRegistry.engine)
                    .filter(ModelRegistry.id == int(model_registry_id or 0))
                    .filter(ModelRegistry.status == "active")
                    .filter(EngineRegistry.status == "active")
                    .first()
                )
                if model is None:
                    return None
                return self._score_model_candidate(
                    model,
                    objective=objective or "",
                    required_capabilities=[
                        cap for cap in (required_capabilities or []) if cap
                    ],
                    policy=policy,
                    mapped_model=None,
                    prefer_local=prefer_local,
                    resources=view,
                    warm_instances=warm_instances,
                )
            if selector_type not in {"objective", "capability"}:
                raise RuntimeError(
                    f"engine_orchestrator_selector_unknown:{selector_type}"
                )
            if not objective:
                raise RuntimeError("engine_orchestrator_objective_required")
            required = [objective] + [
                cap for cap in (required_capabilities or []) if cap
            ]
            mapping = (
                session.query(ObjectiveMapping).filter_by(objective=objective).first()
            )
            all_models = (
                session.query(ModelRegistry)
                .options(
                    joinedload(ModelRegistry.engine),
                    joinedload(ModelRegistry.available_model),
                )
                .join(ModelRegistry.engine)
                .filter(ModelRegistry.status == "active")
                .filter(EngineRegistry.status == "active")
                .all()
            )
            mapped_model = mapping.model if mapping else None
            candidates = self._filter_candidate_models(
                all_models,
                required_capabilities=required,
            )
            if mapped_model is not None and mapped_model not in candidates:
                candidates.insert(0, mapped_model)
            if not candidates:
                return None
            return max(
                self._score_model_candidate(
                    model,
                    objective=objective,
                    required_capabilities=required,
                    policy=policy,
                    mapped_model=mapped_model,
                    prefer_local=prefer_local,
                    resources=view,
                    warm_instances=warm_instances,
                )
                for model in candidates
            )

    def _effective_policy_mode(
        self,
        policy: Dict[str, Any],
        *,
        objective: str,
        prefer_local: Optional[bool],
    ) -> str:
        return effective_policy_mode(
            policy, objective=objective, prefer_local=prefer_local
        )

    def _engine_fit_score(self, provider: str, required_capabilities: set[str]) -> int:
        return engine_fit_score(
            provider,
            required_capabilities,
            hardware_validator=self.hardware,
        )

    def build_provider_config(self, model: ModelRegistry) -> Dict[str, Any]:
        engine_row_id = model.engine.id
        provider_id = model.engine.provider
        engine_config = get_engine_runtime_config(engine_row_id=engine_row_id)
        config: Dict[str, Any] = dict(engine_config)
        config["_engine_row_id"] = engine_row_id
        config["_model_registry_id"] = model.id
        extra_config = model.extra_config or {}
        runtime_model_ref = extra_config.get("runtime_model_ref") or model.name
        if runtime_model_ref:
            config["model"] = runtime_model_ref
        model_path = self._runtime_model_path(model)
        if model_path:
            config["model_path"] = model_path
        metadata = self._catalog_model_metadata(model)
        runtime = metadata.get("runtime") if isinstance(metadata, dict) else {}
        if not isinstance(runtime, dict):
            runtime = {}
        runtime_defaults = (
            runtime.get("defaults") if isinstance(runtime.get("defaults"), dict) else {}
        )
        runtime_default_values = (
            runtime_defaults.get("runtime")
            if isinstance(runtime_defaults.get("runtime"), dict)
            else (
                runtime_defaults
                if not isinstance(runtime_defaults.get("generation"), dict)
                else {}
            )
        )
        runtime_auxiliary_artifacts = (
            runtime.get("auxiliary_artifacts")
            if isinstance(runtime.get("auxiliary_artifacts"), dict)
            else {}
        )
        for key, value in runtime_default_values.items():
            if value is not None:
                config.setdefault(key, value)
        if runtime_auxiliary_artifacts:
            config.setdefault("auxiliary_artifacts", runtime_auxiliary_artifacts)
        structured_defaults = (
            extra_config.get("defaults")
            if isinstance(extra_config.get("defaults"), dict)
            else {}
        )
        model_runtime_defaults = (
            structured_defaults.get("runtime")
            if isinstance(structured_defaults.get("runtime"), dict)
            else {}
        )
        for key, value in model_runtime_defaults.items():
            if value is not None:
                config[key] = value
        available_model = model.available_model
        available_artifacts = (
            available_model.artifacts if available_model is not None else None
        )
        if isinstance(available_artifacts, list):
            config.setdefault("artifacts", available_artifacts)
        metadata_keys = {
            "available_model",
            "binding_label",
            "defaults",
            "requirements",
            "runtime_model_ref",
            "test_config",
            "test_results",
            "options_schema",
        }
        for key, value in extra_config.items():
            if key not in metadata_keys and value is not None:
                config.setdefault(key, value)
        self.apply_provider_runtime_aliases(provider_id, config)
        return config

    @staticmethod
    def apply_provider_runtime_aliases(
        provider_id: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        resolution = ModelOrchestrator.resolve_runtime_context_config(
            provider_id,
            config,
        )
        config["_context_resolution"] = {
            key: value for key, value in resolution.items() if key != "config"
        }
        return resolution["config"]

    @staticmethod
    def resolve_runtime_context_config(
        provider_id: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        provider = provider_id
        definition = get_provider_definition(provider) or {}
        policy = ModelOrchestrator._context_policy(provider, config, definition)
        config["context_policy"] = policy
        context_length = config.get("context_length")
        if context_length in (None, ""):
            for key in ("n_ctx", "max_model_len", "num_ctx"):
                value = config.get(key)
                if value not in (None, ""):
                    context_length = value
                    break

        if context_length not in (None, ""):
            if provider == "llamacpp":
                config["n_ctx"] = context_length
            elif provider == "vllm":
                config["max_model_len"] = context_length
            elif provider == "ollama":
                config["num_ctx"] = context_length
            else:
                config["context_length"] = context_length

        if provider in {"llamacpp", "vllm", "ollama"}:
            config.pop("context_length", None)
        if provider != "llamacpp":
            config.pop("n_ctx", None)
        if provider != "vllm":
            config.pop("max_model_len", None)
        if provider != "ollama":
            config.pop("num_ctx", None)
        return {
            "provider": provider,
            "policy": policy,
            "requested_context_length": context_length,
            "resolved_context_length": context_length,
            "offload": {"enabled": False},
            "config": config,
        }

    @staticmethod
    def _runtime_context_length(provider_id: str, config: Dict[str, Any]) -> int | None:
        provider = provider_id
        keys = {
            "llamacpp": ("n_ctx", "context_length"),
            "vllm": ("max_model_len", "context_length"),
            "ollama": ("num_ctx", "context_length"),
        }.get(provider, ("context_length",))
        for key in keys:
            value = config.get(key)
            if value in (None, ""):
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
        return None

    @staticmethod
    def _set_runtime_context_length(
        provider_id: str,
        config: Dict[str, Any],
        context_length: int,
    ) -> None:
        provider = provider_id
        value = context_length
        if provider == "llamacpp":
            config["n_ctx"] = value
            config.pop("context_length", None)
            return
        if provider == "vllm":
            config["max_model_len"] = value
            config.pop("context_length", None)
            return
        if provider == "ollama":
            config["num_ctx"] = value
            config.pop("context_length", None)
            return
        config["context_length"] = value

    @staticmethod
    def _context_policy(
        provider_id: str,
        config: Dict[str, Any],
        definition: Dict[str, Any],
    ) -> str:
        requested = config.get("context_policy") or ""
        valid = {
            AIContextPolicy.STRICT,
            AIContextPolicy.AUTO_REDUCE,
            AIContextPolicy.OFFLOAD,
            AIContextPolicy.OFFLOAD_THEN_REDUCE,
        }
        if requested in valid:
            return requested
        deployment = definition.get("deployment") or ""
        return AI_CONTEXT_POLICY_DEFAULTS.get(deployment, AIContextPolicy.STRICT)

    @staticmethod
    def _runtime_model_path(model: Any) -> str:
        available_model = model.available_model
        storage_ref = available_model.storage_ref if available_model is not None else ""
        if model.is_downloaded and storage_ref:
            return storage_ref
        return model.model_path

    def _load_capability_priorities(
        self,
        session: Session,
        *,
        required_capabilities: List[str],
    ) -> Dict[int, int]:
        normalized = sorted({cap for cap in required_capabilities if cap})
        if not normalized:
            return {}

        rows = (
            session.query(ModelCapabilityPriority)
            .filter(ModelCapabilityPriority.capability.in_(normalized))
            .all()
        )
        priorities: Dict[int, int] = {}
        for row in rows:
            model_id = row.model_id
            priority = row.priority
            if model_id <= 0 or priority <= 0:
                continue
            existing = priorities.get(model_id)
            if existing is None or priority < existing:
                priorities[model_id] = priority
        return priorities


# Singleton instance
model_orchestrator = ModelOrchestrator()
