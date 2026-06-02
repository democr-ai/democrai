from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import grpc
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from democrai.core.application.auth.internal_grpc import internal_service_auth_metadata
from democrai.core.application.knowledge.models import KnowledgeRetrieveMatch
from democrai.core.application.knowledge.models import KnowledgeRetrieveRequest
from democrai.core.application.knowledge.models import KnowledgeRetrieveResult
from democrai.core.application.knowledge.query.config import (
    KNOWLEDGE_QUERY_AUTH_AUDIENCE,
    KNOWLEDGE_QUERY_AUTH_SCOPE,
    knowledge_query_grpc_options,
    knowledge_query_tls_ca_file,
    knowledge_query_tls_enabled,
    knowledge_query_transport,
    knowledge_query_target,
    knowledge_query_timeout_seconds,
)
from democrai.core.application.knowledge.query.proto import (
    knowledge_query_pb2,
    knowledge_query_pb2_grpc,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload


@dataclass(frozen=True)
class KnowledgeQueryStatus:
    ok: bool
    node_id: str
    pid: int
    started_at: str
    configured: bool


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


def _request_context_json(*, origin: str, request_id: str) -> str:
    request_context = current_request_context_payload(origin)
    if not request_context:
        request_context = {
            "request_id": request_id or uuid.uuid4().hex,
            "channel": "background",
            "module_name": "core",
            "action_name": origin,
        }
    return _json_dump(request_context)


def _retrieve_result(payload: dict[str, Any]) -> KnowledgeRetrieveResult:
    return KnowledgeRetrieveResult(
        matches=tuple(
            KnowledgeRetrieveMatch(
                item_id=str(item.get("item_id") or ""),
                source_id=str(item.get("source_id") or ""),
                kind=str(item.get("kind") or ""),
                title=item.get("title"),
                content=str(item.get("content") or ""),
                summary=item.get("summary"),
                score=float(item.get("score") or 0.0),
                metadata=dict(item.get("metadata") or {}),
                graph_neighbors=tuple(item.get("graph_neighbors") or ()),
            )
            for item in list(payload.get("matches") or [])
        )
    )


class KnowledgeQueryClient:
    def __init__(self, *, target: str | None = None, timeout: float | None = None) -> None:
        config = app_ctx().config
        self._target = target if target is not None else knowledge_query_target(config)
        self._timeout = (
            timeout
            if timeout is not None
            else knowledge_query_timeout_seconds(config)
        )
        self._options = knowledge_query_grpc_options(config)
        self._tls_credentials = _client_tls_credentials(config)
        self._channel = None

    def _stub(self):
        if self._channel is None:
            if self._tls_credentials is not None:
                self._channel = grpc.aio.secure_channel(
                    self._target,
                    self._tls_credentials,
                    options=self._options,
                )
            else:
                self._channel = grpc.aio.insecure_channel(
                    self._target,
                    options=self._options,
                )
        return knowledge_query_pb2_grpc.KnowledgeQueryStub(self._channel)

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
            audience=KNOWLEDGE_QUERY_AUTH_AUDIENCE,
            scopes=(KNOWLEDGE_QUERY_AUTH_SCOPE,),
        )

    async def close(self) -> None:
        channel = self._channel
        self._channel = None
        if channel is not None:
            await channel.close()

    def status(self, *, timeout: float | None = None) -> KnowledgeQueryStatus:
        with self._sync_channel() as channel:
            stub = knowledge_query_pb2_grpc.KnowledgeQueryStub(channel)
            response = stub.Status(
                knowledge_query_pb2.KnowledgeQueryStatusRequest(),
                timeout=timeout if timeout is not None else self._timeout or 10.0,
                metadata=self._auth_metadata(),
            )
        return KnowledgeQueryStatus(
            ok=response.ok,
            node_id=response.node_id,
            pid=response.pid,
            started_at=response.started_at,
            configured=response.configured,
        )

    def health_check(self, *, timeout: float | None = None) -> bool:
        with self._sync_channel() as channel:
            stub = health_pb2_grpc.HealthStub(channel)
            response = stub.Check(
                health_pb2.HealthCheckRequest(
                    service=knowledge_query_pb2.DESCRIPTOR.services_by_name[
                        "KnowledgeQuery"
                    ].full_name,
                ),
                timeout=timeout if timeout is not None else self._timeout or 10.0,
            )
        return response.status == health_pb2.HealthCheckResponse.SERVING

    def wait_ready(self, *, timeout: float) -> KnowledgeQueryStatus:
        deadline = time.monotonic() + max(1.0, timeout)
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
            time.sleep(0.1)
        if last_error is not None:
            raise RuntimeError(f"knowledge_query_not_ready:{last_error}") from last_error
        raise RuntimeError("knowledge_query_not_ready")

    async def retrieve(
        self,
        request: KnowledgeRetrieveRequest,
        *,
        request_id: str | None = None,
    ) -> KnowledgeRetrieveResult:
        resolved_request_id = request_id or uuid.uuid4().hex
        response = await self._stub().Retrieve(
            knowledge_query_pb2.KnowledgeRetrieveRequest(
                request_id=resolved_request_id,
                query_text=request.query_text,
                query_vector_json=_json_dump(request.query_vector or []),
                top_k=request.top_k,
                lexical_limit=request.lexical_limit,
                graph_neighbors_limit=request.graph_neighbors_limit,
                metadata_filters_json=_json_dump(request.metadata_filters or {}),
                request_context_json=_request_context_json(
                    origin="knowledge_query_client.retrieve",
                    request_id=resolved_request_id,
                ),
            ),
            timeout=self._timeout,
            metadata=self._auth_metadata(),
        )
        if not response.ok:
            error = response.error or "knowledge_query_retrieve_failed"
            details = response.traceback.strip()
            raise RuntimeError(error + (f"\n{details}" if details else ""))
        return _retrieve_result(json.loads(response.result_json or "{}"))


def _client_tls_credentials(config: Any | None):
    if knowledge_query_transport(config) != "tcp" or not knowledge_query_tls_enabled(config):
        return None
    ca_file = knowledge_query_tls_ca_file(config)
    root_certificates = Path(ca_file).read_bytes() if ca_file else None
    return grpc.ssl_channel_credentials(root_certificates=root_certificates)
