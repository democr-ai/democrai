from __future__ import annotations

import asyncio
import json
import os
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import grpc
from grpc_health.v1 import health
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from democrai.core.application.auth.internal_grpc import require_internal_service_auth
from democrai.core.application.knowledge.models import KnowledgeRetrieveRequest
from democrai.core.application.knowledge.query.config import (
    KNOWLEDGE_QUERY_AUTH_AUDIENCE,
    KNOWLEDGE_QUERY_AUTH_SCOPE,
    cleanup_knowledge_query_socket,
    knowledge_query_grpc_options,
    knowledge_query_tls_cert_file,
    knowledge_query_tls_enabled,
    knowledge_query_tls_key_file,
    knowledge_query_transport,
    knowledge_query_target,
)
from democrai.core.application.knowledge.query.proto import (
    knowledge_query_pb2,
    knowledge_query_pb2_grpc,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import request_context_scope


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _json_loads(value: str, default: Any) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return default
    return json.loads(raw)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


def _configured() -> bool:
    from democrai.core.application.knowledge.configuration import (
        get_knowledge_runtime_config,
    )

    return bool(get_knowledge_runtime_config().get("enabled"))


def _match_payload(match: Any) -> dict[str, Any]:
    if hasattr(match, "__dataclass_fields__"):
        return asdict(match)
    return dict(match or {})


class KnowledgeQueryGrpcService(knowledge_query_pb2_grpc.KnowledgeQueryServicer):
    def __init__(self) -> None:
        self._started_at = _utc_now()

    async def _authorize(self, context: Any) -> None:
        await require_internal_service_auth(
            context,
            audience=KNOWLEDGE_QUERY_AUTH_AUDIENCE,
            scopes=(KNOWLEDGE_QUERY_AUTH_SCOPE,),
        )

    async def Status(self, request, context):
        await self._authorize(context)
        return knowledge_query_pb2.KnowledgeQueryStatusResponse(
            ok=True,
            node_id=app_ctx().node_id or "",
            pid=os.getpid(),
            started_at=self._started_at,
            configured=_configured(),
        )

    async def Retrieve(self, request, context):
        await self._authorize(context)
        try:
            if not _configured():
                return knowledge_query_pb2.KnowledgeRetrieveResponse(
                    ok=False,
                    error="knowledge_disabled",
                )
            service = getattr(app_ctx(), "knowledge_service", None)
            if service is None:
                return knowledge_query_pb2.KnowledgeRetrieveResponse(
                    ok=False,
                    error="knowledge_query_service_unavailable",
                )
            query_vector = _json_loads(request.query_vector_json, [])
            if not isinstance(query_vector, list) or not query_vector:
                query_vector = None
            metadata_filters = _json_loads(request.metadata_filters_json, {})
            if not isinstance(metadata_filters, dict):
                metadata_filters = {}
            request_context = _json_loads(request.request_context_json, {})
            if not isinstance(request_context, dict):
                request_context = {}
            user_id = request_context.get("user")
            if user_id is None:
                return knowledge_query_pb2.KnowledgeRetrieveResponse(
                    ok=False,
                    error="knowledge_query_missing_user_id",
                )
            with request_context_scope(request_context):
                result = await service.retrieve(
                    KnowledgeRetrieveRequest(
                        user_id=user_id,
                        organization_id=request_context.get("organization_id"),
                        access_level=request_context.get("access_level") or 3,
                        query_text=request.query_text,
                        query_vector=query_vector,
                        top_k=request.top_k or 8,
                        lexical_limit=request.lexical_limit or 8,
                        graph_neighbors_limit=request.graph_neighbors_limit or 4,
                        metadata_filters=metadata_filters,
                    )
                )
            return knowledge_query_pb2.KnowledgeRetrieveResponse(
                ok=True,
                result_json=_json_dumps(
                    {"matches": [_match_payload(match) for match in result.matches]}
                ),
            )
        except Exception as exc:
            return knowledge_query_pb2.KnowledgeRetrieveResponse(
                ok=False,
                error=str(exc),
                traceback=traceback.format_exc(),
            )


def _server_tls_credentials(config: Any | None):
    if knowledge_query_transport(config) != "tcp" or not knowledge_query_tls_enabled(config):
        return None
    cert_file = knowledge_query_tls_cert_file(config)
    key_file = knowledge_query_tls_key_file(config)
    if not cert_file or not key_file:
        raise RuntimeError("knowledge_query_tls_cert_and_key_required")
    with open(cert_file, "rb") as cert_handle, open(key_file, "rb") as key_handle:
        return grpc.ssl_server_credentials(
            [(key_handle.read(), cert_handle.read())]
        )


async def serve_until_stopped(*, stop_event: asyncio.Event | None = None) -> None:
    config = app_ctx().config
    cleanup_knowledge_query_socket(config)
    server = grpc.aio.server(options=knowledge_query_grpc_options(config))
    health_servicer = health.aio.HealthServicer()
    service = KnowledgeQueryGrpcService()
    knowledge_query_pb2_grpc.add_KnowledgeQueryServicer_to_server(service, server)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    service_name = knowledge_query_pb2.DESCRIPTOR.services_by_name[
        "KnowledgeQuery"
    ].full_name
    target = knowledge_query_target(config)
    credentials = _server_tls_credentials(config)
    bound_port = (
        server.add_secure_port(target, credentials)
        if credentials is not None
        else server.add_insecure_port(target)
    )
    if bound_port == 0:
        raise RuntimeError(f"knowledge_query_bind_failed:{target}")
    await server.start()
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)
    logger = getattr(app_ctx(), "logger", None)
    if logger is not None:
        logger.info(f"[KnowledgeQuery] gRPC server started target={target}")
    try:
        if stop_event is None:
            await server.wait_for_termination()
        else:
            await stop_event.wait()
    finally:
        await health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
        await health_servicer.set(service_name, health_pb2.HealthCheckResponse.NOT_SERVING)
        await server.stop(grace=2)
