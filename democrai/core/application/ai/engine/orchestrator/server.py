from __future__ import annotations

import asyncio
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import grpc
from grpc_health.v1 import health
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from democrai.core.application.auth.internal_grpc import require_internal_service_auth
from democrai.core.application.ai.engine.orchestrator.config import (
    ENGINE_ORCHESTRATOR_AUTH_AUDIENCE,
    ENGINE_ORCHESTRATOR_AUTH_SCOPE,
    cleanup_orchestrator_socket,
    orchestrator_batch_queue_size,
    orchestrator_batch_wait_seconds,
    orchestrator_invocation_worker_count,
    orchestrator_job_output_queue_size,
    orchestrator_job_terminal_ttl_seconds,
    orchestrator_grpc_options,
    orchestrator_scheduler_graceful_shutdown_seconds,
    orchestrator_scheduler_max_queue_depth,
    orchestrator_scheduler_submit_timeout_seconds,
    orchestrator_scheduler_worker_count,
    orchestrator_runtime_transition_worker_count,
    orchestrator_target,
    orchestrator_tls_cert_file,
    orchestrator_tls_enabled,
    orchestrator_tls_key_file,
    orchestrator_transport,
)
from democrai.core.application.ai.engine.orchestrator.batching import (
    EngineBatchingCoordinator,
)
from democrai.core.application.ai.engine.orchestrator.proto import (
    engine_orchestrator_pb2,
    engine_orchestrator_pb2_grpc,
)
from democrai.core.application.ai.engine.orchestrator.resolver import (
    optional_bool,
)
from democrai.core.application.ai.engine.orchestrator.executor import EngineJobExecutor
from democrai.core.application.ai.engine.orchestrator.jobs import EngineJobRegistry
from democrai.core.application.ai.engine.orchestrator.scheduler import EngineScheduler
from democrai.core.application.ai.engine.orchestrator.scheduler import EngineSchedulerConfig
from democrai.core.application.ai.engine.runtime.requests import cancel_runtime_request
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.application.ai.pipeline_context import ai_pipeline_context
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.pipeline_context import create_ai_pipeline_context
from democrai.core.platform.utils.identity import to_int_or_zero
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import request_context_scope


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _context_cancelled(context: Any) -> bool:
    cancelled = getattr(context, "cancelled", None)
    if callable(cancelled):
        return bool(cancelled())
    done = getattr(context, "done", None)
    if callable(done):
        return bool(done())
    return False


def _context_deadline_expired(context: Any) -> bool:
    time_remaining = getattr(context, "time_remaining", None)
    if not callable(time_remaining):
        return False
    remaining = time_remaining()
    return remaining is not None and float(remaining) <= 0


def _exception_traceback(exc: Exception) -> str:
    return f"{type(exc).__name__}:{exc}\n{traceback.format_exc()}"


def _ensure_context_active(context: Any) -> None:
    if _context_cancelled(context):
        raise asyncio.CancelledError()
    if _context_deadline_expired(context):
        raise TimeoutError("engine_orchestrator_deadline_exceeded")


async def _await_with_context(awaitable: Any, context: Any) -> Any:
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            _ensure_context_active(context)
            done, _pending = await asyncio.wait({task}, timeout=0.25)
            if done:
                break
        _ensure_context_active(context)
        return await task
    except BaseException:
        if not task.done():
            task.cancel()
        raise


async def _await_job_result(job: Any, context: Any) -> Any:
    future = job.result_future
    while not future.done():
        if _context_cancelled(context):
            job.cancel("engine_orchestrator_client_cancelled")
            raise asyncio.CancelledError()
        if _context_deadline_expired(context):
            job.cancel("engine_orchestrator_deadline_exceeded")
            raise TimeoutError("engine_orchestrator_deadline_exceeded")
        await asyncio.sleep(0.05)
    _ensure_context_active(context)
    return await future


async def _next_job_event(job: Any, context: Any) -> Any | None:
    wait_task = asyncio.create_task(job.next_event())
    try:
        while not wait_task.done():
            if _context_cancelled(context):
                job.cancel("engine_orchestrator_client_cancelled")
                wait_task.cancel()
                return None
            if _context_deadline_expired(context):
                job.cancel("engine_orchestrator_deadline_exceeded")
                wait_task.cancel()
                raise TimeoutError("engine_orchestrator_deadline_exceeded")
            await asyncio.wait({wait_task}, timeout=0.05)
        return await wait_task
    except BaseException:
        if not wait_task.done():
            wait_task.cancel()
        raise


def _drain_job_event(job: Any) -> Any | None:
    next_event_nowait = getattr(job, "next_event_nowait", None)
    if callable(next_event_nowait):
        return next_event_nowait()
    return None


def _job_event_chunk(job: Any, event: Any):
    kind = getattr(event, "kind", "")
    payload = getattr(event, "payload", {})
    if kind == "engine.chunk":
        return engine_orchestrator_pb2.EngineStreamChunk(
            request_id=getattr(job, "request_id", ""),
            kind="chunk",
            chunk_json=json.dumps(json_value(payload.get("value")), ensure_ascii=True),
        )
    if kind == "engine.pipeline_message":
        return engine_orchestrator_pb2.EngineStreamChunk(
            request_id=getattr(job, "request_id", ""),
            kind="message",
            chunk_json=json.dumps(
                json_value(payload.get("message") or {}),
                ensure_ascii=True,
            ),
        )
    return engine_orchestrator_pb2.EngineStreamChunk(
        request_id=getattr(job, "request_id", ""),
        kind="message",
        chunk_json=json.dumps(
            json_value(
                {
                    "type": kind,
                    "pipeline_id": getattr(job, "pipeline_id", ""),
                    "current_pipeline_id": getattr(job, "pipeline_id", ""),
                    "parent_pipeline_id": None,
                    "request_id": getattr(job, "request_id", ""),
                    "root_method": getattr(job, "method", ""),
                    "status": getattr(event, "status", None),
                    "payload": payload,
                }
            ),
            ensure_ascii=True,
        ),
    )


def _json_loads(value: str, default: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return default
    return json.loads(raw)


def _server_tls_credentials(config: Any | None):
    if orchestrator_transport(config) != "tcp" or not orchestrator_tls_enabled(config):
        return None
    cert_file = orchestrator_tls_cert_file(config)
    key_file = orchestrator_tls_key_file(config)
    if not cert_file or not key_file:
        raise RuntimeError("engine_orchestrator_tls_cert_and_key_required")
    private_key = Path(key_file).read_bytes()
    certificate_chain = Path(cert_file).read_bytes()
    return grpc.ssl_server_credentials(((private_key, certificate_chain),))


class EngineOrchestratorService(
    engine_orchestrator_pb2_grpc.EngineOrchestratorServicer
):
    def __init__(self) -> None:
        self._started_at = _utc_now()
        config = getattr(app_ctx(), "config", None)
        self._job_output_queue_size = orchestrator_job_output_queue_size(config)
        self._job_registry = EngineJobRegistry(
            terminal_ttl_seconds=orchestrator_job_terminal_ttl_seconds(config)
        )
        self._job_executor = EngineJobExecutor(
            batching=EngineBatchingCoordinator(
                wait_time=orchestrator_batch_wait_seconds(config),
                queue_size=orchestrator_batch_queue_size(config),
                invocation_worker_count=orchestrator_invocation_worker_count(config),
            )
        )
        self._runtime_transition_worker_count = (
            orchestrator_runtime_transition_worker_count(config)
        )
        self._scheduler = EngineScheduler(
            registry=self._job_registry,
            executor=self._job_executor.execute,
            config=EngineSchedulerConfig(
                max_queue_depth=orchestrator_scheduler_max_queue_depth(config),
                submit_timeout_seconds=orchestrator_scheduler_submit_timeout_seconds(config),
                worker_count=orchestrator_scheduler_worker_count(config),
                graceful_shutdown_seconds=orchestrator_scheduler_graceful_shutdown_seconds(config),
            ),
        )
        self._scheduler_started = False

    def _ensure_scheduler_started(self) -> None:
        if not self._scheduler_started:
            self._scheduler.start()
            self._scheduler_started = True

    async def stop(self) -> None:
        if self._scheduler_started:
            self._scheduler_started = False
            await self._scheduler.stop()
        await self._job_executor.shutdown()

    async def _authorize(self, context: Any) -> None:
        await require_internal_service_auth(
            context,
            audience=ENGINE_ORCHESTRATOR_AUTH_AUDIENCE,
            scopes=(ENGINE_ORCHESTRATOR_AUTH_SCOPE,),
        )

    async def Status(self, request, context):
        await self._authorize(context)
        runtime = getattr(app_ctx(), "engine_runtime", None)
        active_instances = []
        if runtime is not None and callable(getattr(runtime, "active_instances", None)):
            active_instances = list(runtime.active_instances() or [])
        active_jobs = self._job_registry.snapshots()
        return engine_orchestrator_pb2.EngineStatusResponse(
            ok=True,
            node_id=str(getattr(app_ctx(), "node_id", "") or ""),
            pid=int(os.getpid()),
            started_at=self._started_at,
            active_instances_json=json.dumps(active_instances, ensure_ascii=True),
            active_jobs_json=json.dumps(active_jobs, ensure_ascii=True),
        )

    async def Invoke(self, request, context):
        await self._authorize(context)
        request_id = request.request_id
        try:
            with request_context_scope(_json_loads(request.request_context_json, {})):
                result = await self._invoke_unary_job(request, context)
            return engine_orchestrator_pb2.EngineInvokeResponse(
                request_id=request_id,
                ok=True,
                result_json=json.dumps(json_value(result), ensure_ascii=True),
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(exc))
        except Exception as exc:
            return engine_orchestrator_pb2.EngineInvokeResponse(
                request_id=request_id,
                ok=False,
                error=str(exc),
                traceback=_exception_traceback(exc),
            )

    async def InvokeStream(self, request, context):
        await self._authorize(context)
        request_id = request.request_id
        try:
            with request_context_scope(_json_loads(request.request_context_json, {})):
                async for chunk in self._invoke_stream_job(request, context):
                    yield chunk
            yield engine_orchestrator_pb2.EngineStreamChunk(
                request_id=request_id,
                kind="end",
            )
        except asyncio.CancelledError:
            return
        except TimeoutError as exc:
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(exc))
        except Exception as exc:
            yield engine_orchestrator_pb2.EngineStreamChunk(
                request_id=request_id,
                kind="error",
                error=str(exc),
                traceback=_exception_traceback(exc),
            )

    async def Cancel(self, request, context):
        await self._authorize(context)
        request_id = request.request_id
        try:
            job_cancelled = self._job_registry.cancel(
                request_id,
                "engine_orchestrator_cancelled",
            )
            runtime_cancelled = cancel_runtime_request(request_id)
            return engine_orchestrator_pb2.EngineCancelResponse(
                request_id=request_id,
                ok=True,
                cancelled=bool(job_cancelled or runtime_cancelled),
            )
        except Exception as exc:
            return engine_orchestrator_pb2.EngineCancelResponse(
                request_id=request_id,
                ok=False,
                error=str(exc),
            )

    async def RefreshRegistries(self, request, context):
        await self._authorize(context)
        try:
            from democrai.core.application.ai.engine.manifests import (
                sync_engine_manifests_to_registry,
            )

            sync_engine_manifests_to_registry()
            return engine_orchestrator_pb2.RefreshRegistriesResponse(ok=True)
        except Exception as exc:
            return engine_orchestrator_pb2.RefreshRegistriesResponse(
                ok=False,
                error=str(exc),
            )

    async def SyncActiveEngines(self, request, context):
        await self._authorize(context)
        try:
            from democrai.core.application.ai.engine.runtime import get_engine_runtime

            await get_engine_runtime().sync_active_engines()
            return engine_orchestrator_pb2.SyncActiveEnginesResponse(ok=True)
        except Exception as exc:
            return engine_orchestrator_pb2.SyncActiveEnginesResponse(
                ok=False,
                error=str(exc),
            )

    async def UnloadModel(self, request, context):
        await self._authorize(context)
        try:
            from democrai.core.application.ai.engine.runtime import get_engine_runtime

            model_registry_id = to_int_or_zero(request.model_registry_id)
            if model_registry_id <= 0:
                raise RuntimeError("engine_runtime_model_registry_id_required")
            unloaded = get_engine_runtime().unload_model(
                engine_row_id=to_int_or_zero(request.engine_registry_id),
                model_registry_id=model_registry_id,
            )
            return engine_orchestrator_pb2.UnloadModelResponse(
                ok=True,
                unloaded=bool(unloaded),
            )
        except Exception as exc:
            return engine_orchestrator_pb2.UnloadModelResponse(
                ok=False,
                error=str(exc),
            )

    async def StopEngine(self, request, context):
        await self._authorize(context)
        try:
            from democrai.core.application.ai.engine.runtime import get_engine_runtime

            get_engine_runtime().stop_engine(
                to_int_or_zero(request.engine_registry_id)
            )
            return engine_orchestrator_pb2.StopEngineResponse(
                ok=True,
                stopped=True,
            )
        except Exception as exc:
            return engine_orchestrator_pb2.StopEngineResponse(
                ok=False,
                stopped=False,
                error=str(exc),
            )

    async def InvokeEngineAction(self, request, context):
        await self._authorize(context)
        request_id = request.request_id
        try:
            if request.method not in {"list_available_models"}:
                raise RuntimeError(f"engine_action_method_not_allowed:{request.method}")
            with request_context_scope(_json_loads(request.request_context_json, {})):
                from democrai.core.application.ai.engine.runtime.methods import (
                    invoke_engine_method,
                    run_engine_result,
                )
                from democrai.core.application.ai.engine.runtime.worker import (
                    EngineWorkerSubject,
                )

                subject = EngineWorkerSubject(
                    engine_id=request.engine_id,
                    config=python_value(_json_loads(request.config_json, {})),
                )
                try:
                    result = await _await_with_context(
                        asyncio.to_thread(
                            lambda: run_engine_result(
                                invoke_engine_method(
                                    subject,
                                    request.method,
                                    python_value(_json_loads(request.payload_json, {})),
                                )
                            )
                        ),
                        context,
                    )
                finally:
                    subject.close()
                return engine_orchestrator_pb2.EngineInvokeResponse(
                    request_id=request_id,
                    ok=True,
                    result_json=json.dumps(json_value(result), ensure_ascii=True),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return engine_orchestrator_pb2.EngineInvokeResponse(
                request_id=request_id,
                ok=False,
                error=str(exc),
                traceback=traceback.format_exc(),
            )

    async def InvokeEngineRuntime(self, request, context):
        await self._authorize(context)
        request_id = request.request_id
        try:
            with request_context_scope(_json_loads(request.request_context_json, {})):
                from democrai.core.application.ai.engine.runtime import get_engine_runtime

                model_registry_id = to_int_or_zero(request.model_registry_id)
                if model_registry_id <= 0:
                    raise RuntimeError("engine_runtime_model_registry_id_required")
                _ensure_context_active(context)
                result = await _await_with_context(
                    asyncio.to_thread(
                        get_engine_runtime().invoke,
                        engine_row_id=to_int_or_zero(request.engine_registry_id),
                        model_registry_id=model_registry_id,
                        engine_id=request.engine_id,
                        config=python_value(_json_loads(request.config_json, {})),
                        method=request.method,
                        payload=python_value(_json_loads(request.payload_json, {})),
                    ),
                    context,
                )
                _ensure_context_active(context)
                return engine_orchestrator_pb2.EngineInvokeResponse(
                    request_id=request_id,
                    ok=True,
                    result_json=json.dumps(json_value(result), ensure_ascii=True),
                )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, str(exc))
        except Exception as exc:
            return engine_orchestrator_pb2.EngineInvokeResponse(
                request_id=request_id,
                ok=False,
                error=str(exc),
                traceback=_exception_traceback(exc),
            )

    async def _invoke_unary_job(self, request, context) -> Any:
        self._ensure_scheduler_started()
        job = None
        pipeline_context = _create_orchestrator_pipeline_context(request)
        with ai_pipeline_context(pipeline_context):
            async with ai_pipeline_step(
                type="request",
                name="engine_orchestrator.invoke",
                input=_request_audit_input(request),
            ):
                job, created = self._job_from_request(
                    request,
                    pipeline_id=pipeline_context.pipeline_id,
                    response_mode="unary",
                )
                try:
                    if created:
                        await self._scheduler.submit(job)
                    return await _await_job_result(job, context)
                finally:
                    self._job_registry.mark_terminal(job)

    async def _invoke_stream_job(self, request, context):
        self._ensure_scheduler_started()
        job = None
        pipeline_context = _create_orchestrator_pipeline_context(request)
        with ai_pipeline_context(pipeline_context):
            async with ai_pipeline_step(
                type="request",
                name="engine_orchestrator.invoke_stream",
                input=_request_audit_input(request),
            ):
                job, created = self._job_from_request(
                    request,
                    pipeline_id=pipeline_context.pipeline_id,
                    response_mode="stream",
                )
                if not created:
                    raise RuntimeError("engine_orchestrator_stream_already_attached")
                await self._scheduler.submit(job)
                try:
                    while True:
                        if _context_cancelled(context):
                            job.cancel("engine_orchestrator_client_cancelled")
                            return
                        if _context_deadline_expired(context):
                            job.cancel("engine_orchestrator_deadline_exceeded")
                            raise TimeoutError("engine_orchestrator_deadline_exceeded")
                        if job.result_future.done():
                            break
                        event = await _next_job_event(job, context)
                        if event is None:
                            continue
                        chunk = _job_event_chunk(job, event)
                        if chunk is not None:
                            yield chunk
                    while True:
                        event = _drain_job_event(job)
                        if event is None:
                            break
                        chunk = _job_event_chunk(job, event)
                        if chunk is not None:
                            yield chunk
                    await job.result_future
                finally:
                    self._job_registry.mark_terminal(job)

    def _job_from_request(self, request, *, pipeline_id: str, response_mode: str):
        payload = python_value(_json_loads(request.payload_json, {}))
        if not isinstance(payload, dict):
            raise RuntimeError("engine_orchestrator_payload_dict_required")
        request_context = _json_loads(request.request_context_json, {})
        security_context = _json_loads(request.security_context_json, {})
        capabilities = _json_loads(request.capabilities_json, [])
        if not isinstance(capabilities, list):
            raise RuntimeError("engine_orchestrator_capabilities_list_required")
        job, created = self._job_registry.get_or_create_job(
            request_id=request.request_id,
            pipeline_id=pipeline_id,
            selector_type=request.selector_type,
            model_registry_id=to_int_or_zero(request.model_registry_id) or None,
            objective=request.objective or request.capability or None,
            capabilities=[
                item for item in capabilities if item
            ],
            prefer_local=optional_bool(request, "prefer_local"),
            confirm_swap=request.confirm_swap,
            method=request.method,
            response_mode=response_mode,
            payload=payload,
            request_context=request_context
            if isinstance(request_context, dict)
            else {},
            security_context=security_context
            if isinstance(security_context, dict)
            else {},
            max_queue_size=self._job_output_queue_size,
        )
        return job, created


def _create_orchestrator_pipeline_context(request: Any):
    selector_type = request.selector_type
    model_registry_id = None
    if selector_type == "model_registry_id":
        model_registry_id = to_int_or_zero(request.model_registry_id) or None
    payload = python_value(_json_loads(request.payload_json, {}))
    metadata = {}
    if isinstance(payload, dict) and isinstance(payload.get("ingest_meta"), dict):
        metadata.update(payload["ingest_meta"])
    return create_ai_pipeline_context(
        root_method=request.method or "engine_orchestrator.invoke",
        request_id=request.request_id or None,
        model_registry_id=model_registry_id,
        metadata=metadata,
    )


def _apply_provider_metadata(context: Any, provider: Any) -> None:
    context.provider = getattr(provider, "engine_id", None)
    context.engine = context.provider
    engine_row_id = getattr(provider, "engine_row_id", None)
    if engine_row_id is not None:
        context.engine_row_id = engine_row_id
    model_registry_id = getattr(provider, "model_registry_id", None)
    if model_registry_id is not None:
        context.model_registry_id = model_registry_id
    config = getattr(provider, "config", None)
    if isinstance(config, dict):
        context.model_name = config.get("model") or config.get("model_path")


def _request_audit_input(request: Any) -> dict[str, Any]:
    payload = _json_loads(request.payload_json, {})
    payload_summary = (
        _payload_summary(payload)
        if isinstance(payload, dict)
        else {"type": type(payload).__name__}
    )
    selector_type = request.selector_type
    return {
        "selector_type": selector_type,
        "model_registry_id": (
            to_int_or_zero(request.model_registry_id)
            if selector_type == "model_registry_id"
            else None
        ),
        "objective": request.objective or None,
        "capability": request.capability or None,
        "capabilities": _json_loads(request.capabilities_json, []),
        "prefer_local": optional_bool(request, "prefer_local"),
        "confirm_swap": request.confirm_swap,
        "method": request.method or None,
        "payload": payload_summary,
    }


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "keys": sorted(str(key) for key in payload.keys()),
        "fields": {
            str(key): _value_summary(value)
            for key, value in payload.items()
            if str(key) != "_stream_pipeline_messages"
        },
    }


def _value_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    if isinstance(value, bytes | bytearray):
        return {"type": "bytes", "length": len(value)}
    if isinstance(value, list):
        return {"type": "list", "length": len(value)}
    if isinstance(value, dict):
        return {"type": "dict", "keys": sorted(str(key) for key in value.keys())}
    return {"type": type(value).__name__}


async def serve_until_stopped(*, stop_event: asyncio.Event | None = None) -> None:
    config = app_ctx().config
    cleanup_orchestrator_socket(config)
    server = grpc.aio.server(options=orchestrator_grpc_options(config))
    health_servicer = health.aio.HealthServicer()
    service = EngineOrchestratorService()
    engine_orchestrator_pb2_grpc.add_EngineOrchestratorServicer_to_server(
        service,
        server,
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    service_name = engine_orchestrator_pb2.DESCRIPTOR.services_by_name[
        "EngineOrchestrator"
    ].full_name
    target = orchestrator_target(config)
    credentials = _server_tls_credentials(config)
    bound_port = (
        server.add_secure_port(target, credentials)
        if credentials is not None
        else server.add_insecure_port(target)
    )
    if bound_port == 0:
        raise RuntimeError(f"engine_orchestrator_bind_failed:{target}")
    await server.start()
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)
    logger = getattr(app_ctx(), "logger", None)
    if logger is not None:
        logger.info(f"[EngineOrchestrator] gRPC server started target={target}")
    try:
        if stop_event is None:
            await server.wait_for_termination()
        else:
            await stop_event.wait()
    finally:
        await health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
        await health_servicer.set(service_name, health_pb2.HealthCheckResponse.NOT_SERVING)
        await service.stop()
        await server.stop(grace=2)
