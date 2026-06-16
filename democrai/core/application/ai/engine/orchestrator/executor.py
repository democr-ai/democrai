from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from democrai.core.application.ai.engine.orchestrator.batching import (
    EngineBatchingCoordinator,
)
from democrai.core.application.ai.engine.orchestrator.jobs import EngineJob
from democrai.core.application.ai.engine.orchestrator.resolver import resolve_provider
from democrai.core.application.ai.engine.orchestrator.resolver import validate_provider
from democrai.core.application.ai.pipeline_context import current_ai_pipeline_context
from democrai.core.platform.utils.identity import to_int_or_zero


@dataclass
class EngineJobResolverRequest:
    request_id: str
    selector_type: str
    model_registry_id: int
    objective: str
    capability: str
    capabilities_json: str
    prefer_local: bool | None
    confirm_swap: bool
    method: str
    payload_json: str
    request_context_json: str
    security_context_json: str
    # False when the executing node cannot reach the user's session for the
    # resource-swap prompt (claim on a non-origin node).
    allow_swap_prompt: bool = True

    def HasField(self, field_name: str) -> bool:
        if field_name == "prefer_local":
            return self.prefer_local is not None
        raise ValueError(field_name)


class EngineJobExecutor:
    def __init__(
        self,
        *,
        batching: EngineBatchingCoordinator | None = None,
    ) -> None:
        self._batching = batching or EngineBatchingCoordinator()

    async def execute(self, job: EngineJob) -> Any:
        if job.response_mode == "stream":
            await self.execute_stream(job)
            return None
        return await self.execute_unary(job)

    async def shutdown(self) -> None:
        await self._batching.shutdown()

    async def execute_unary(self, job: EngineJob) -> Any:
        request = resolver_request_from_job(job)
        if job.method == "__validate_provider__":
            await job.publish_async(
                "engine_orchestrator.provider_validate",
                {"confirm_swap": request.confirm_swap},
            )
            return await validate_provider(request)
        if job.method == "__warmup_provider__":
            await job.publish_async(
                "engine_orchestrator.provider_warmup",
                {"confirm_swap": request.confirm_swap},
            )
            provider = await resolve_provider(
                request,
                event_hook=lambda name, payload: _apply_resolver_event(job, name, payload),
                allow_prompt=getattr(job, "allow_swap_prompt", True),
            )
            _apply_provider_metadata(provider)
            await job.publish_async(
                "engine_orchestrator.provider_resolved",
                {"confirm_swap": request.confirm_swap},
            )
            return {
                "status": "ok",
                "request_id": job.request_id,
                "model_registry_id": getattr(provider, "model_registry_id", None),
                "engine_row_id": getattr(provider, "engine_row_id", None),
                "engine": getattr(provider, "engine_id", None),
            }
        provider = await resolve_provider(
            request,
            event_hook=lambda name, payload: _apply_resolver_event(job, name, payload),
            allow_prompt=getattr(job, "allow_swap_prompt", True),
        )
        _apply_provider_metadata(provider)
        await job.publish_async(
            "engine_orchestrator.provider_resolved",
            {"confirm_swap": request.confirm_swap},
        )
        return await self._batching.invoke_unary(
            job=job,
            provider=provider,
            method=job.method,
            payload=provider_payload(job),
        )

    async def execute_stream(self, job: EngineJob) -> None:
        request = resolver_request_from_job(job)
        provider = await resolve_provider(
            request,
            event_hook=lambda name, payload: _apply_resolver_event(job, name, payload),
            allow_prompt=getattr(job, "allow_swap_prompt", True),
        )
        _apply_provider_metadata(provider)
        await job.publish_async(
            "engine_orchestrator.provider_resolved",
            {"confirm_swap": request.confirm_swap},
        )
        await self._batching.invoke_stream(
            job=job,
            provider=provider,
            method=job.method,
            payload=provider_payload(job),
        )


def provider_payload(job: EngineJob) -> dict[str, Any]:
    payload = dict(job.payload)
    payload = _materialize_storage_refs(payload, method=job.method)
    stream_pipeline_messages = bool(payload.pop("_stream_pipeline_messages", False))
    if stream_pipeline_messages:
        payload["on_message"] = lambda message: job.publish_async(
            "engine.pipeline_message",
            {"message": message},
        )
    return payload


# Engine-side keyword that receives the loaded bytes, per method. Every
# method that accepts a media file goes through the same single transit key
# (media_storage_path); new methods extend this table.
_MEDIA_REF_TARGET_BY_METHOD = {
    "transcribe": "audio_data",
}


def _materialize_storage_refs(
    payload: dict[str, Any], *, method: str
) -> dict[str, Any]:
    """Resolve a media_storage_path reference into bytes on the executing node.

    Binary inputs travel as paths on the shared media storage instead of
    inline bytes (the durable queue persists payloads on the DB); engines
    keep receiving bytes on their method-specific keyword.
    """
    storage_path = payload.pop("media_storage_path", None)
    if not storage_path:
        return payload
    target_key = _MEDIA_REF_TARGET_BY_METHOD.get(method)
    if target_key is None:
        raise RuntimeError(
            f"engine_orchestrator_media_ref_unsupported_method:{method}"
        )
    if payload.get(target_key) is not None:
        raise RuntimeError(f"engine_orchestrator_media_ref_payload_conflict:{method}")
    from democrai.core.runtime.foundation.app import app_ctx

    media = getattr(app_ctx(), "media", None)
    if media is None:
        raise RuntimeError("engine_orchestrator_media_provider_unavailable")
    payload[target_key] = bytes(media.load(str(storage_path)))
    return payload


async def _apply_resolver_event(
    job: EngineJob,
    name: str,
    payload: dict[str, Any],
) -> None:
    if name in {"waiting_hitl", "unloading", "loading"}:
        await job.set_status_async(name, payload=payload)
        return
    await job.publish_async(f"engine_orchestrator.{name}", payload)


def _apply_provider_metadata(provider: Any) -> None:
    context = current_ai_pipeline_context()
    if context is None:
        return
    provider_id = getattr(provider, "engine_id", "")
    if provider_id:
        context.provider = provider_id
        context.engine = provider_id
    engine_row_id = getattr(provider, "engine_row_id", None)
    if engine_row_id is not None:
        context.engine_row_id = engine_row_id
    model_registry_id = getattr(provider, "model_registry_id", None)
    if model_registry_id is not None:
        context.model_registry_id = model_registry_id
    config = getattr(provider, "config", None)
    if isinstance(config, dict):
        model_name = config.get("model") or config.get("model_path")
        if model_name:
            context.model_name = model_name


def resolver_request_from_job(job: EngineJob) -> EngineJobResolverRequest:
    objective = job.objective or ""
    return EngineJobResolverRequest(
        request_id=job.request_id,
        selector_type=job.selector_type,
        model_registry_id=to_int_or_zero(job.model_registry_id),
        objective=objective,
        capability=objective,
        capabilities_json=json.dumps(list(job.capabilities), ensure_ascii=True),
        prefer_local=job.prefer_local,
        confirm_swap=job.confirm_swap,
        allow_swap_prompt=bool(getattr(job, "allow_swap_prompt", True)),
        method=job.method,
        payload_json=json.dumps(job.payload, ensure_ascii=True, default=str),
        request_context_json=json.dumps(job.request_context, ensure_ascii=True),
        security_context_json=json.dumps(
            job.security_context,
            ensure_ascii=True,
        ),
    )
