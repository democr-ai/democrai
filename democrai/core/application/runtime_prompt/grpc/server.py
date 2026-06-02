from __future__ import annotations

import asyncio
import json
from typing import Any

import grpc
from grpc_health.v1 import health
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from democrai.core.application.auth.internal_grpc import require_internal_service_auth
from democrai.core.application.runtime_prompt.grpc.config import (
    RUNTIME_PROMPT_AUTH_AUDIENCE,
    RUNTIME_PROMPT_AUTH_SCOPE,
    cleanup_runtime_prompt_socket,
    runtime_prompt_grpc_options,
    runtime_prompt_target,
)
from democrai.core.application.runtime_prompt.grpc.proto import (
    runtime_prompt_pb2,
    runtime_prompt_pb2_grpc,
)
from democrai.core.application.runtime_prompt.service import (
    get_runtime_prompt_service,
)
from democrai.core.runtime.foundation.app import app_ctx


def _json_loads(value: str, default: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return default
    return json.loads(raw)


class RuntimePromptGrpcService(runtime_prompt_pb2_grpc.RuntimePromptServicer):
    async def _authorize(self, context: Any) -> None:
        await require_internal_service_auth(
            context,
            audience=RUNTIME_PROMPT_AUTH_AUDIENCE,
            scopes=(RUNTIME_PROMPT_AUTH_SCOPE,),
        )

    async def AskRuntimePrompt(self, request, context):
        await self._authorize(context)
        try:
            required_access_level = (
                int(request.required_access_level)
                if int(request.required_access_level or 0) > 0
                else None
            )
            decision = await get_runtime_prompt_service().ask(
                question=str(request.question or ""),
                actions=_json_loads(request.actions_json, []),
                required_role=str(request.required_role or "").strip() or None,
                required_access_level=required_access_level,
                required_permissions=_json_loads(
                    request.required_permissions_json,
                    [],
                ),
                form_model=_json_loads(request.form_model_json, []),
                form_values=_json_loads(request.form_values_json, {}),
                request_context=_json_loads(request.request_context_json, {}),
                metadata=_json_loads(request.metadata_json, {}),
                timeout_seconds=float(request.timeout_seconds or 300.0),
            )
            return runtime_prompt_pb2.RuntimePromptResponse(
                ok=bool(decision.ok),
                prompt_id=str(decision.prompt_id or ""),
                action=str(decision.action or ""),
                error=str(decision.error or ""),
                metadata_json=json.dumps(
                    dict(decision.metadata or {}),
                    ensure_ascii=True,
                ),
                data_json=json.dumps(dict(decision.data or {}), ensure_ascii=True),
            )
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))


async def serve_until_stopped(*, stop_event: asyncio.Event | None = None) -> None:
    config = app_ctx().config
    cleanup_runtime_prompt_socket(config)
    server = grpc.aio.server(options=runtime_prompt_grpc_options(config))
    health_servicer = health.aio.HealthServicer()
    runtime_prompt_pb2_grpc.add_RuntimePromptServicer_to_server(
        RuntimePromptGrpcService(),
        server,
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    service_name = runtime_prompt_pb2.DESCRIPTOR.services_by_name[
        "RuntimePrompt"
    ].full_name
    target = runtime_prompt_target(config)
    bound_port = server.add_insecure_port(target)
    if bound_port == 0:
        raise RuntimeError(f"runtime_prompt_bind_failed:{target}")
    await server.start()
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)
    app_ctx().runtime_prompt_grpc_server = server
    logger = getattr(app_ctx(), "logger", None)
    if logger is not None:
        logger.info(f"[RuntimePrompt] gRPC server started target={target}")
    try:
        if stop_event is None:
            await server.wait_for_termination()
        else:
            await stop_event.wait()
    finally:
        await health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
        await health_servicer.set(
            service_name,
            health_pb2.HealthCheckResponse.NOT_SERVING,
        )
        await server.stop(grace=2)


async def stop_runtime_prompt_grpc_server() -> None:
    config = getattr(app_ctx(), "config", None)
    server = getattr(app_ctx(), "runtime_prompt_grpc_server", None)
    if server is not None:
        app_ctx().runtime_prompt_grpc_server = None
        app_ctx().runtime_prompt_grpc_future = None
        await server.stop(grace=2)
    cleanup_runtime_prompt_socket(config)
