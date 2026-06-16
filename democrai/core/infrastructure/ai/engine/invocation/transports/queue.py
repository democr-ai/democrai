from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import timedelta
from typing import Any

from democrai.core.application.ai.engine.invocation import (
    EngineInvocationRequest,
    EngineInvocationTarget,
    EngineOrchestratorProvider,
    EngineOrchestratorStatus,
)
from democrai.core.infrastructure.ai.engine.invocation.config import (
    EngineInvocationRuntimeConfig,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.infrastructure.ai.engine.response.factory import (
    EngineResponseStreamFactory,
    resolve_engine_response_stream,
)
from democrai.core.infrastructure.ai.engine.response.config import (
    EngineResponseStreamConfig,
)
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream
from democrai.core.infrastructure.ai.engine.response.reader import (
    EngineResponseStreamReader,
)
from democrai.core.infrastructure.ai.engine.response.writer import (
    EngineResponseStreamWriter,
)
from democrai.core.infrastructure.ai.engine.invocation.client_helpers import (
    build_request_context_json,
    call_pipeline_callback,
)
from democrai.core.application.ai.engine.orchestrator.config import (
    EngineOrchestratorConfig,
)
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.platform.utils.identity import to_int_or_zero
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    EngineInvocationQueue,
    EngineNodeInstallRegistry,
    EngineNodeInstanceRegistry,
    RuntimeNodeRegistry,
)
from democrai.core.runtime.foundation.app import app_ctx


CONTROL_SELECTOR_TYPE = "control"
CONTROL_REFRESH_REGISTRIES = "__control_refresh_registries__"
CONTROL_SYNC_ACTIVE_ENGINES = "__control_sync_active_engines__"
CONTROL_UNLOAD_MODEL = "__control_unload_model__"
CONTROL_STOP_ENGINE = "__control_stop_engine__"
CONTROL_INVOKE_ENGINE_ACTION = "__control_invoke_engine_action__"
CONTROL_INVOKE_ENGINE_RUNTIME = "__control_invoke_engine_runtime__"
ACTIVE_JOBS_STATUS_LIMIT = 100
ACTIVE_JOBS_MAX_PAGE_LIMIT = 500


def _run_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(
        target=runner,
        name="EngineQueueTransportSyncControl",
        daemon=True,
    )
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


class EngineQueueTransport(EngineOrchestratorProvider):
    """Queue-backed invocation transport."""

    requires_media_storage_refs = True
    requires_shared_response_stream = True
    receiver_names = ("queue",)

    def __init__(
        self,
        *,
        store: EngineInvocationQueueStore | None = None,
        response_stream: EngineResponseStream | Any | None = None,
    ) -> None:
        config = app_ctx().config
        response_config = EngineResponseStreamConfig.load(config)
        if (
            response_stream is None
            and not EngineResponseStreamFactory.is_cross_process_provider(
                response_config.provider_type
            )
        ):
            raise RuntimeError(
                "engine_queue_response_stream_cross_process_provider_required"
            )
        self._store = store or EngineInvocationQueueStore()
        self._response_stream = resolve_engine_response_stream(response_stream)
        orchestrator_config = EngineOrchestratorConfig.load(config)
        self._invoke_timeout = orchestrator_config.invoke_timeout_seconds
        self._control_timeout = (
            orchestrator_config.invoke_timeout_seconds
            or orchestrator_config.startup_timeout_seconds
        )
        self._keepalive_seconds = (
            EngineInvocationRuntimeConfig.load(config).queue_keepalive_seconds
        )
        self._runtime_config = EngineInvocationRuntimeConfig.load(config)
        self._node_id = str(getattr(app_ctx(), "node_id", "") or SERVER_NAME)
        self._ready_after = utc_now_naive()

    @staticmethod
    def _validate_locally(
        *,
        selector_type: str,
        model_registry_id: int | None,
        objective: str | None,
        capability: str | None,
        capabilities: list[str] | None,
        prefer_local: bool | None,
        confirm_swap: bool,
        request_id: str,
    ) -> dict[str, Any]:
        from democrai.core.application.ai.engine.orchestrator.executor import (
            EngineJobResolverRequest,
        )
        from democrai.core.application.ai.engine.orchestrator.resolver import (
            validate_selector,
        )

        request = EngineJobResolverRequest(
            request_id=request_id,
            selector_type=selector_type,
            model_registry_id=to_int_or_zero(model_registry_id),
            objective=objective or capability or "",
            capability=capability or objective or "",
            capabilities_json=json.dumps(capabilities or [], ensure_ascii=True),
            prefer_local=prefer_local,
            confirm_swap=confirm_swap,
            method="__validate_provider__",
            payload_json="{}",
            request_context_json="{}",
            security_context_json="{}",
        )
        return validate_selector(request)

    async def _enqueue(
        self,
        *,
        selector_type: str,
        method: str,
        payload: dict[str, Any] | None,
        model_registry_id: int | None,
        objective: str | None,
        capability: str | None,
        capabilities: list[str] | None,
        prefer_local: bool | None,
        confirm_swap: bool,
        request_id: str,
        security_context: dict[str, Any] | None,
        response_mode: str,
        origin: str,
        total_timeout_seconds: float | None = None,
    ) -> EngineResponseStreamReader:
        stream_key = self._store_stream_key(request_id)
        enqueued = False
        reader = EngineResponseStreamReader(
            self._response_stream,
            stream_key,
            request_id=request_id,
            store=self._store,
            keepalive_timeout_seconds=self._keepalive_seconds * 3,
            total_timeout_seconds=total_timeout_seconds,
        )
        try:
            payload_json = json.dumps(json_value(payload or {}), ensure_ascii=True)
            request_context_json = build_request_context_json(
                origin=origin, request_id=request_id
            )
            security_context_json = json.dumps(
                security_context or {}, ensure_ascii=True
            )
            resolved_objective = objective or capability or None
            await asyncio.to_thread(
                self._store.enqueue,
                request_id=request_id,
                selector_type=selector_type,
                model_registry_id=to_int_or_zero(model_registry_id) or None,
                objective=resolved_objective,
                capabilities=[item for item in (capabilities or []) if item],
                prefer_local=prefer_local,
                confirm_swap=confirm_swap,
                method=method,
                response_mode=response_mode,
                payload_json=payload_json,
                request_context_json=request_context_json,
                security_context_json=security_context_json,
                origin_node_id=self._node_id,
            )
            enqueued = True
            writer = EngineResponseStreamWriter(
                self._response_stream,
                stream_key,
                node_id=self._node_id,
            )
            await writer.queued()
        except Exception:
            if enqueued:
                await asyncio.to_thread(self._store.request_cancel, request_id)
            await reader._cleanup()
            raise
        return reader

    @staticmethod
    def _store_stream_key(request_id: str) -> str:
        from democrai.core.infrastructure.ai.engine.invocation.queue.config import (
            engine_response_stream_key,
        )

        return engine_response_stream_key(request_id)

    @staticmethod
    def _entry_error(entry: Any) -> RuntimeError:
        data = entry.data if isinstance(entry.data, dict) else {}
        error = str(data.get("error") or "engine_orchestrator_invoke_failed")
        details = str(data.get("traceback") or "")
        return RuntimeError(error + (f"\n{details}" if details else ""))

    async def invoke(
        self,
        target: EngineInvocationTarget,
        request: EngineInvocationRequest,
    ) -> Any:
        resolved_request_id = request.request_id or uuid.uuid4().hex
        if request.method == "__validate_provider__":
            return self._validate_locally(
                selector_type=target.selector_type,
                model_registry_id=target.model_registry_id,
                objective=target.objective,
                capability=target.capability,
                capabilities=list(target.capabilities),
                prefer_local=target.prefer_local,
                confirm_swap=target.confirm_swap,
                request_id=resolved_request_id,
            )
        reader = await self._enqueue(
            selector_type=target.selector_type,
            method=request.method,
            payload=request.payload,
            model_registry_id=target.model_registry_id,
            objective=target.objective,
            capability=target.capability,
            capabilities=list(target.capabilities),
            prefer_local=target.prefer_local,
            confirm_swap=target.confirm_swap,
            request_id=resolved_request_id,
            security_context=request.security_context,
            response_mode="unary",
            origin="engine_queue_client.invoke",
            total_timeout_seconds=self._invoke_timeout,
        )
        result: Any = None
        async for entry in reader.entries():
            if entry.kind == "result":
                result = python_value(entry.data)
                continue
            if entry.kind == "end":
                return result
            if entry.kind == "error":
                raise self._entry_error(entry)
        raise RuntimeError("engine_orchestrator_response_stream_closed")

    async def invoke_stream(
        self,
        target: EngineInvocationTarget,
        request: EngineInvocationRequest,
        *,
        on_message: Any = None,
    ):
        resolved_request_id = request.request_id or uuid.uuid4().hex
        reader = await self._enqueue(
            selector_type=target.selector_type,
            method=request.method,
            payload=request.payload,
            model_registry_id=target.model_registry_id,
            objective=target.objective,
            capability=target.capability,
            capabilities=list(target.capabilities),
            prefer_local=target.prefer_local,
            confirm_swap=target.confirm_swap,
            request_id=resolved_request_id,
            security_context=request.security_context,
            response_mode="stream",
            origin="engine_queue_client.invoke_stream",
            total_timeout_seconds=self._invoke_timeout,
        )
        async for entry in reader.entries():
            if entry.kind == "chunk":
                yield python_value(entry.data)
                continue
            if entry.kind == "message":
                await call_pipeline_callback(on_message, python_value(entry.data))
                continue
            if entry.kind in {"accepted", "retry"}:
                continue
            if entry.kind == "result":
                continue
            if entry.kind == "end":
                return
            if entry.kind == "error":
                raise self._entry_error(entry)
            raise RuntimeError(
                f"engine_orchestrator_stream_chunk_unknown:{entry.kind}"
            )

    async def cancel(self, request_id: str) -> bool:
        outcome = await asyncio.to_thread(self._store.request_cancel, request_id)
        return outcome in {"cancelled", "requested"}

    def cancel_sync(self, request_id: str) -> bool:
        outcome = self._store.request_cancel(request_id)
        return outcome in {"cancelled", "requested"}

    # ----- control -------------------------------------------------------

    def status(self, *, timeout: float | None = None) -> EngineOrchestratorStatus:
        del timeout
        node_ids = self._active_node_ids()
        with SessionLocal() as session:
            instances = []
            if node_ids:
                instances = [
                    {
                        "node_id": row.node_id,
                        "engine_row_id": row.engine_row_id,
                        "engine_id": row.engine_id,
                        "model_registry_id": row.model_registry_id,
                        "model": row.model,
                        "config_signature": row.config_signature,
                        "pid": row.pid,
                        "status": row.status,
                    }
                    for row in (
                        session.query(EngineNodeInstanceRegistry)
                        .filter(EngineNodeInstanceRegistry.node_id.in_(node_ids))
                        .filter(EngineNodeInstanceRegistry.status == "running")
                        .all()
                    )
                ]
        jobs = self._active_jobs_page(
            offset=0,
            limit=ACTIVE_JOBS_STATUS_LIMIT,
        )
        return EngineOrchestratorStatus(
            ok=bool(node_ids),
            node_id="engine-queue" if node_ids else self._node_id,
            pid=0,
            started_at="",
            active_instances_json=json.dumps(instances, ensure_ascii=True),
            active_jobs_json=json.dumps(jobs, ensure_ascii=True),
        )

    def list_active_jobs(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._active_jobs_page(offset=offset, limit=limit)

    @staticmethod
    def _active_jobs_page(*, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        resolved_offset = max(0, int(offset or 0))
        resolved_limit = min(
            ACTIVE_JOBS_MAX_PAGE_LIMIT,
            max(1, int(limit or ACTIVE_JOBS_STATUS_LIMIT)),
        )
        with SessionLocal() as session:
            return [
                {
                    "request_id": row.id,
                    "status": row.status,
                    "method": row.method,
                    "origin_node_id": row.origin_node_id,
                    "claimed_by_node_id": row.claimed_by_node_id,
                    "lease_owner": row.lease_owner,
                    "attempts": int(row.attempts or 0),
                    "created_at": row.created_at.isoformat()
                    if row.created_at is not None
                    else "",
                }
                for row in (
                    session.query(EngineInvocationQueue)
                    .filter(
                        EngineInvocationQueue.status.in_(
                            ("pending", "failed", "processing")
                        )
                    )
                    .order_by(EngineInvocationQueue.created_at.asc())
                    .offset(resolved_offset)
                    .limit(resolved_limit)
                    .all()
                )
            ]

    def health_check(self, *, timeout: float | None = None) -> bool:
        return self.status(timeout=timeout).ok

    def wait_ready(self, *, timeout: float) -> EngineOrchestratorStatus:
        deadline = time.monotonic() + max(1.0, float(timeout or 1.0))
        last_status: EngineOrchestratorStatus | None = None
        while time.monotonic() < deadline:
            last_status = self.status(timeout=min(1.0, deadline - time.monotonic()))
            if last_status.ok and self._local_node_ready():
                return last_status
            time.sleep(0.1)
        raise RuntimeError("engine_orchestrator_not_ready")

    def refresh_registries(self, *, reason: str = "") -> bool:
        results = _run_sync(
            self._invoke_control_many(
                CONTROL_REFRESH_REGISTRIES,
                {"reason": reason},
                target_node_ids=self._active_node_ids(),
            )
        )
        return all(bool(item) for item in results) if results else True

    def sync_active_engines(self) -> bool:
        results = _run_sync(
            self._invoke_control_many(
                CONTROL_SYNC_ACTIVE_ENGINES,
                {},
                target_node_ids=self._active_node_ids(),
            )
        )
        return all(bool(item) for item in results) if results else True

    def unload_model(
        self,
        *,
        engine_registry_id: int | str,
        model_registry_id: int | str,
    ) -> bool:
        target_node_ids = self._nodes_with_instance(
            engine_registry_id=to_int_or_zero(engine_registry_id),
            model_registry_id=to_int_or_zero(model_registry_id),
        )
        if not target_node_ids:
            return False
        results = _run_sync(
            self._invoke_control_many(
                CONTROL_UNLOAD_MODEL,
                {
                    "engine_registry_id": to_int_or_zero(engine_registry_id),
                    "model_registry_id": to_int_or_zero(model_registry_id),
                },
                target_node_ids=target_node_ids,
            )
        )
        return any(bool(item) for item in results)

    def stop_engine(self, *, engine_registry_id: int | str) -> bool:
        target_node_ids = self._nodes_with_instance(
            engine_registry_id=to_int_or_zero(engine_registry_id),
        )
        if not target_node_ids:
            return False
        results = _run_sync(
            self._invoke_control_many(
                CONTROL_STOP_ENGINE,
                {"engine_registry_id": to_int_or_zero(engine_registry_id)},
                target_node_ids=target_node_ids,
            )
        )
        return any(bool(item) for item in results)

    def invoke_engine_action(
        self,
        *,
        engine_registry_id: int | str,
        engine_id: str,
        config: dict[str, Any] | None,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        target_node_id = self._node_for_engine_install(engine_id)
        if target_node_id is None:
            raise RuntimeError(
                f"engine_orchestrator_no_active_node_for_engine:{engine_id}"
            )
        return _run_sync(
            self._invoke_control_one(
                CONTROL_INVOKE_ENGINE_ACTION,
                {
                    "engine_registry_id": to_int_or_zero(engine_registry_id),
                    "engine_id": engine_id,
                    "config": config or {},
                    "method": method,
                    "payload": payload or {},
                },
                target_node_id=target_node_id,
            )
        )

    def invoke_engine_runtime(
        self,
        *,
        engine_registry_id: int | str,
        engine_id: str,
        config: dict[str, Any] | None,
        method: str,
        model_registry_id: int | str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        target_node_id = self._node_for_engine_install(engine_id)
        if target_node_id is None:
            raise RuntimeError(
                f"engine_orchestrator_no_active_node_for_engine:{engine_id}"
            )
        return _run_sync(
            self._invoke_control_one(
                CONTROL_INVOKE_ENGINE_RUNTIME,
                {
                    "engine_registry_id": to_int_or_zero(engine_registry_id),
                    "engine_id": engine_id,
                    "config": config or {},
                    "method": method,
                    "model_registry_id": to_int_or_zero(model_registry_id),
                    "payload": payload or {},
                },
                target_node_id=target_node_id,
            )
        )

    async def _invoke_control_many(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        target_node_ids: list[str],
    ) -> list[Any]:
        targets = target_node_ids or [""]
        results = await asyncio.gather(
            *(
                self._invoke_control_one(
                    method,
                    payload,
                    target_node_id=target_node_id,
                )
                for target_node_id in targets
            ),
            return_exceptions=True,
        )
        errors = [item for item in results if isinstance(item, Exception)]
        if errors:
            if len(errors) == 1:
                raise errors[0]
            raise ExceptionGroup("engine_orchestrator_control_fanout_failed", errors)
        return list(results)

    async def _invoke_control_one(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        target_node_id: str | None = None,
    ) -> Any:
        resolved_request_id = uuid.uuid4().hex
        control_payload = dict(payload)
        if target_node_id:
            control_payload["_target_node_id"] = target_node_id
        reader = await self._enqueue(
            selector_type=CONTROL_SELECTOR_TYPE,
            method=method,
            payload=control_payload,
            model_registry_id=None,
            objective="control",
            capability=None,
            capabilities=[],
            prefer_local=None,
            confirm_swap=False,
            request_id=resolved_request_id,
            security_context={},
            response_mode="unary",
            origin=f"engine_queue_client.{method}",
            total_timeout_seconds=self._control_timeout,
        )
        result: Any = None
        async for entry in reader.entries():
            if entry.kind == "result":
                result = python_value(entry.data)
                continue
            if entry.kind == "end":
                return result
            if entry.kind == "error":
                raise self._entry_error(entry)
        raise RuntimeError("engine_orchestrator_response_stream_closed")

    def _active_node_ids(self) -> list[str]:
        threshold = self._runtime_config.node_state_active_threshold_seconds
        cutoff = utc_now_naive() - timedelta(seconds=max(1.0, float(threshold)))
        with SessionLocal() as session:
            rows = (
                session.query(RuntimeNodeRegistry.node_id)
                .filter(RuntimeNodeRegistry.status == "active")
                .filter(RuntimeNodeRegistry.orchestrator_last_seen_at.isnot(None))
                .filter(RuntimeNodeRegistry.orchestrator_last_seen_at >= cutoff)
                .order_by(RuntimeNodeRegistry.node_id.asc())
                .all()
        )
        node_ids = [str(row[0]) for row in rows]
        return node_ids

    def _local_node_ready(self) -> bool:
        with SessionLocal() as session:
            row = (
                session.query(
                    RuntimeNodeRegistry.status,
                    RuntimeNodeRegistry.orchestrator_last_seen_at,
                )
                .filter(RuntimeNodeRegistry.node_id == self._node_id)
                .first()
            )
        if row is None:
            return False
        status, last_seen_at = row
        if status != "active" or last_seen_at is None:
            return False
        return last_seen_at >= self._ready_after

    def _nodes_with_instance(
        self,
        *,
        engine_registry_id: int,
        model_registry_id: int | None = None,
    ) -> list[str]:
        if engine_registry_id <= 0:
            return []
        with SessionLocal() as session:
            query = (
                session.query(EngineNodeInstanceRegistry.node_id)
                .filter(EngineNodeInstanceRegistry.engine_row_id == engine_registry_id)
                .filter(EngineNodeInstanceRegistry.status == "running")
            )
            if model_registry_id:
                query = query.filter(
                    EngineNodeInstanceRegistry.model_registry_id
                    == model_registry_id
                )
            active_node_ids = self._active_node_ids()
            if not active_node_ids:
                return []
            query = query.filter(
                EngineNodeInstanceRegistry.node_id.in_(active_node_ids)
            )
            rows = query.order_by(EngineNodeInstanceRegistry.node_id.asc()).all()
        return [str(row[0]) for row in rows]

    def _node_for_engine_install(self, engine_id: str) -> str | None:
        active_node_ids = self._active_node_ids()
        with SessionLocal() as session:
            rows = (
                session.query(EngineNodeInstallRegistry.node_id)
                .filter(EngineNodeInstallRegistry.engine_id == engine_id)
                .filter(EngineNodeInstallRegistry.status == "installed")
                .order_by(EngineNodeInstallRegistry.node_id.asc())
                .all()
            )
        if not rows:
            return None
        for row in rows:
            node_id = str(row[0])
            if node_id in active_node_ids:
                return node_id
        return None
