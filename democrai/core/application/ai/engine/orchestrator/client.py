from __future__ import annotations

import json
import inspect
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import grpc
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from democrai.core.application.auth.internal_grpc import internal_service_auth_metadata
from democrai.core.application.ai.engine.orchestrator.config import (
    ENGINE_ORCHESTRATOR_AUTH_AUDIENCE,
    ENGINE_ORCHESTRATOR_AUTH_SCOPE,
    orchestrator_grpc_options,
    orchestrator_invoke_timeout_seconds,
    orchestrator_target,
    orchestrator_tls_ca_file,
    orchestrator_tls_enabled,
    orchestrator_transport,
)
from democrai.core.application.ai.engine.orchestrator.proto import (
    engine_orchestrator_pb2,
    engine_orchestrator_pb2_grpc,
)
from democrai.core.application.ai.pipeline_context import AiPipelineMessage
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.platform.utils.identity import to_int_or_zero
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload


@dataclass(frozen=True)
class EngineOrchestratorStatus:
    ok: bool
    node_id: str
    pid: int
    started_at: str
    active_instances_json: str
    active_jobs_json: str


class EngineOrchestratorClient:
    def __init__(self, *, target: str | None = None, timeout: float = 10.0) -> None:
        config = app_ctx().config
        self._target = target or orchestrator_target(config)
        self._timeout = timeout
        self._invoke_timeout = orchestrator_invoke_timeout_seconds(config)
        self._options = orchestrator_grpc_options(config)
        self._tls_credentials = _client_tls_credentials(config)
        self._aio_channel = None

    def _request(
        self,
        *,
        selector_type: str,
        method: str,
        payload: dict[str, Any] | None = None,
        model_registry_id: int | None = None,
        objective: str | None = None,
        capability: str | None = None,
        capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
        request_id: str | None = None,
        security_context: dict[str, Any] | None = None,
        origin: str,
    ):
        resolved_request_id = request_id or uuid.uuid4().hex
        values = {
            "request_id": resolved_request_id,
            "selector_type": selector_type,
            "model_registry_id": to_int_or_zero(model_registry_id),
            "objective": objective or "",
            "capability": capability or "",
            "capabilities_json": json.dumps(capabilities or [], ensure_ascii=True),
            "confirm_swap": confirm_swap,
            "method": method,
            "payload_json": json.dumps(json_value(payload or {}), ensure_ascii=True),
            "request_context_json": self._request_context_json(
                origin=origin,
                request_id=resolved_request_id,
            ),
            "security_context_json": json.dumps(
                security_context or {},
                ensure_ascii=True,
            ),
        }
        if prefer_local is not None:
            values["prefer_local"] = prefer_local
        return engine_orchestrator_pb2.EngineInvokeRequest(**values)

    def _request_context_json(self, *, origin: str, request_id: str) -> str:
        request_context = current_request_context_payload(origin)
        if not request_context:
            request_context = {
                "request_id": request_id or uuid.uuid4().hex,
                "channel": "background",
                "module_name": "core",
                "action_name": origin,
            }
        return json.dumps(request_context, ensure_ascii=True)

    def _aio_stub(self):
        if self._aio_channel is None:
            if self._tls_credentials is not None:
                self._aio_channel = grpc.aio.secure_channel(
                    self._target,
                    self._tls_credentials,
                    options=self._options,
                )
            else:
                self._aio_channel = grpc.aio.insecure_channel(
                    self._target,
                    options=self._options,
                )
        return engine_orchestrator_pb2_grpc.EngineOrchestratorStub(self._aio_channel)

    def _sync_channel(self):
        if self._tls_credentials is not None:
            return grpc.secure_channel(
                self._target,
                self._tls_credentials,
                options=self._options,
            )
        return grpc.insecure_channel(self._target, options=self._options)

    def _auth_metadata(self) -> tuple[tuple[str, str], ...]:
        return internal_service_auth_metadata(
            audience=ENGINE_ORCHESTRATOR_AUTH_AUDIENCE,
            scopes=(ENGINE_ORCHESTRATOR_AUTH_SCOPE,),
        )

    async def close(self) -> None:
        channel = self._aio_channel
        self._aio_channel = None
        if channel is not None:
            await channel.close()

    @staticmethod
    async def _call_callback(callback: Any, value: Any) -> None:
        if callback is None:
            return
        if isinstance(value, dict):
            value = AiPipelineMessage(**value)
        result = callback(value)
        if inspect.isawaitable(result):
            await result

    def status(self, *, timeout: float | None = None) -> EngineOrchestratorStatus:
        with self._sync_channel() as channel:
            stub = engine_orchestrator_pb2_grpc.EngineOrchestratorStub(channel)
            response = stub.Status(
                engine_orchestrator_pb2.EngineStatusRequest(),
                timeout=float(timeout if timeout is not None else self._timeout),
                metadata=self._auth_metadata(),
            )
        return EngineOrchestratorStatus(
            ok=response.ok,
            node_id=response.node_id,
            pid=response.pid,
            started_at=response.started_at,
            active_instances_json=response.active_instances_json,
            active_jobs_json=response.active_jobs_json or "[]",
        )

    def health_check(self, *, timeout: float | None = None) -> bool:
        with self._sync_channel() as channel:
            stub = health_pb2_grpc.HealthStub(channel)
            response = stub.Check(
                health_pb2.HealthCheckRequest(
                    service=engine_orchestrator_pb2.DESCRIPTOR.services_by_name[
                        "EngineOrchestrator"
                    ].full_name,
                ),
                timeout=float(timeout if timeout is not None else self._timeout),
            )
        return response.status == health_pb2.HealthCheckResponse.SERVING

    def wait_ready(self, *, timeout: float) -> EngineOrchestratorStatus:
        deadline = time.monotonic() + max(1.0, float(timeout or 1.0))
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                health_timeout = min(2.0, max(0.1, deadline - time.monotonic()))
                if not self.health_check(timeout=health_timeout):
                    time.sleep(0.1)
                    continue
                status = self.status(
                    timeout=min(2.0, max(0.1, deadline - time.monotonic()))
                )
                if status.ok:
                    return status
            except grpc.RpcError as exc:
                last_error = exc
                try:
                    status = self.status(
                        timeout=min(2.0, max(0.1, deadline - time.monotonic()))
                    )
                    if status.ok:
                        return status
                except grpc.RpcError as status_exc:
                    last_error = status_exc
            time.sleep(0.1)
        if last_error is not None:
            raise RuntimeError(f"engine_orchestrator_not_ready:{last_error}") from last_error
        raise RuntimeError("engine_orchestrator_not_ready")

    async def invoke(
        self,
        *,
        selector_type: str,
        method: str,
        payload: dict[str, Any] | None = None,
        model_registry_id: int | None = None,
        objective: str | None = None,
        capability: str | None = None,
        capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
        request_id: str | None = None,
        security_context: dict[str, Any] | None = None,
    ) -> Any:
        try:
            stub = self._aio_stub()
            response = await stub.Invoke(
                self._request(
                    selector_type=selector_type,
                    method=method,
                    payload=payload,
                    model_registry_id=model_registry_id,
                    objective=objective,
                    capability=capability,
                    capabilities=capabilities,
                    prefer_local=prefer_local,
                    confirm_swap=confirm_swap,
                    request_id=request_id,
                    security_context=security_context,
                    origin="engine_orchestrator_client.invoke",
                ),
                timeout=self._invoke_timeout,
                metadata=self._auth_metadata(),
            )
        except grpc.aio.AioRpcError as exc:
            raise RuntimeError(f"{exc.code().name}:{exc.details()}") from exc
        if not response.ok:
            error = response.error or "engine_orchestrator_invoke_failed"
            details = response.traceback
            raise RuntimeError(error + (f"\n{details}" if details else ""))
        return python_value(json.loads(response.result_json or "null"))

    async def invoke_stream(
        self,
        *,
        selector_type: str,
        method: str,
        payload: dict[str, Any] | None = None,
        model_registry_id: int | None = None,
        objective: str | None = None,
        capability: str | None = None,
        capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
        request_id: str | None = None,
        security_context: dict[str, Any] | None = None,
        on_message: Any = None,
    ):
        try:
            stub = self._aio_stub()
            responses = stub.InvokeStream(
                self._request(
                    selector_type=selector_type,
                    method=method,
                    payload=payload,
                    model_registry_id=model_registry_id,
                    objective=objective,
                    capability=capability,
                    capabilities=capabilities,
                    prefer_local=prefer_local,
                    confirm_swap=confirm_swap,
                    request_id=request_id,
                    security_context=security_context,
                    origin="engine_orchestrator_client.invoke_stream",
                ),
                timeout=self._invoke_timeout,
                metadata=self._auth_metadata(),
            )
            async for response in responses:
                kind = response.kind
                if kind == "chunk":
                    yield python_value(json.loads(response.chunk_json or "null"))
                    continue
                if kind == "message":
                    await self._call_callback(
                        on_message,
                        python_value(json.loads(response.chunk_json or "null")),
                    )
                    continue
                if kind == "end":
                    return
                if kind == "error":
                    error = response.error or "engine_orchestrator_stream_failed"
                    details = response.traceback
                    raise RuntimeError(error + (f"\n{details}" if details else ""))
                raise RuntimeError(f"engine_orchestrator_stream_chunk_unknown:{kind}")
        except grpc.aio.AioRpcError as exc:
            raise RuntimeError(f"{exc.code().name}:{exc.details()}") from exc

    async def cancel(self, request_id: str) -> bool:
        try:
            response = await self._aio_stub().Cancel(
                engine_orchestrator_pb2.EngineCancelRequest(
                    request_id=request_id,
                ),
                timeout=self._timeout,
                metadata=self._auth_metadata(),
            )
        except grpc.aio.AioRpcError as exc:
            raise RuntimeError(f"{exc.code().name}:{exc.details()}") from exc
        if not response.ok:
            raise RuntimeError(response.error or "engine_orchestrator_cancel_failed")
        return response.cancelled

    def cancel_sync(self, request_id: str) -> bool:
        with self._sync_channel() as channel:
            stub = engine_orchestrator_pb2_grpc.EngineOrchestratorStub(channel)
            response = stub.Cancel(
                engine_orchestrator_pb2.EngineCancelRequest(
                    request_id=request_id,
                ),
                timeout=self._timeout,
                metadata=self._auth_metadata(),
            )
        if not response.ok:
            raise RuntimeError(response.error or "engine_orchestrator_cancel_failed")
        return response.cancelled

    def refresh_registries(self, *, reason: str = "") -> bool:
        with self._sync_channel() as channel:
            stub = engine_orchestrator_pb2_grpc.EngineOrchestratorStub(channel)
            response = stub.RefreshRegistries(
                engine_orchestrator_pb2.RefreshRegistriesRequest(
                    reason=reason,
                ),
                timeout=self._timeout,
                metadata=self._auth_metadata(),
            )
        if not response.ok:
            raise RuntimeError(response.error or "engine_orchestrator_refresh_failed")
        return True

    def sync_active_engines(self) -> bool:
        with self._sync_channel() as channel:
            stub = engine_orchestrator_pb2_grpc.EngineOrchestratorStub(channel)
            response = stub.SyncActiveEngines(
                engine_orchestrator_pb2.SyncActiveEnginesRequest(),
                timeout=self._timeout,
                metadata=self._auth_metadata(),
            )
        if not response.ok:
            raise RuntimeError(response.error or "engine_orchestrator_sync_failed")
        return True

    def unload_model(
        self,
        *,
        engine_registry_id: int | str,
        model_registry_id: int | str,
    ) -> bool:
        with self._sync_channel() as channel:
            stub = engine_orchestrator_pb2_grpc.EngineOrchestratorStub(channel)
            response = stub.UnloadModel(
                engine_orchestrator_pb2.UnloadModelRequest(
                    engine_registry_id=int(engine_registry_id),
                    model_registry_id=int(model_registry_id),
                ),
                timeout=self._timeout,
                metadata=self._auth_metadata(),
            )
        if not response.ok:
            raise RuntimeError(response.error or "engine_orchestrator_unload_failed")
        return response.unloaded

    def stop_engine(self, *, engine_registry_id: int | str) -> bool:
        with self._sync_channel() as channel:
            stub = engine_orchestrator_pb2_grpc.EngineOrchestratorStub(channel)
            response = stub.StopEngine(
                engine_orchestrator_pb2.StopEngineRequest(
                    engine_registry_id=int(engine_registry_id),
                ),
                timeout=self._timeout,
                metadata=self._auth_metadata(),
            )
        if not response.ok:
            raise RuntimeError(response.error or "engine_orchestrator_stop_engine_failed")
        return response.stopped

    def invoke_engine_action(
        self,
        *,
        engine_registry_id: int | str,
        engine_id: str,
        config: dict[str, Any] | None,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        request_id = uuid.uuid4().hex
        with self._sync_channel() as channel:
            stub = engine_orchestrator_pb2_grpc.EngineOrchestratorStub(channel)
            response = stub.InvokeEngineAction(
                engine_orchestrator_pb2.EngineActionRequest(
                    request_id=request_id,
                    engine_registry_id=int(engine_registry_id),
                    engine_id=engine_id,
                    config_json=json.dumps(
                        json_value(config or {}),
                        ensure_ascii=True,
                    ),
                    method=method,
                    payload_json=json.dumps(
                        json_value(payload or {}),
                        ensure_ascii=True,
                    ),
                    request_context_json=self._request_context_json(
                        origin="engine_orchestrator_client.invoke_engine_action",
                        request_id=request_id,
                    ),
                ),
                timeout=self._invoke_timeout,
                metadata=self._auth_metadata(),
            )
        if not response.ok:
            error = response.error or "engine_orchestrator_action_invoke_failed"
            details = response.traceback
            raise RuntimeError(error + (f"\n{details}" if details else ""))
        return python_value(json.loads(response.result_json or "null"))

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
        request_id = uuid.uuid4().hex
        with self._sync_channel() as channel:
            stub = engine_orchestrator_pb2_grpc.EngineOrchestratorStub(channel)
            response = stub.InvokeEngineRuntime(
                engine_orchestrator_pb2.EngineRuntimeInvokeRequest(
                    request_id=request_id,
                    engine_registry_id=int(engine_registry_id),
                    engine_id=engine_id,
                    model_registry_id=int(model_registry_id),
                    config_json=json.dumps(
                        json_value(config or {}),
                        ensure_ascii=True,
                    ),
                    method=method,
                    payload_json=json.dumps(
                        json_value(payload or {}),
                        ensure_ascii=True,
                    ),
                    request_context_json=self._request_context_json(
                        origin="engine_orchestrator_client.invoke_engine_runtime",
                        request_id=request_id,
                    ),
                ),
                timeout=self._invoke_timeout,
                metadata=self._auth_metadata(),
            )
        if not response.ok:
            error = response.error or "engine_orchestrator_runtime_invoke_failed"
            details = response.traceback
            raise RuntimeError(error + (f"\n{details}" if details else ""))
        return python_value(json.loads(response.result_json or "null"))


def _client_tls_credentials(config: Any | None):
    if orchestrator_transport(config) != "tcp" or not orchestrator_tls_enabled(config):
        return None
    ca_file = orchestrator_tls_ca_file(config)
    root_certificates = Path(ca_file).read_bytes() if ca_file else None
    return grpc.ssl_channel_credentials(root_certificates=root_certificates)
