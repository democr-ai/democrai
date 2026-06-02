from __future__ import annotations

import json
from typing import Any

import grpc

from democrai.core.application.auth.internal_grpc import internal_service_auth_metadata
from democrai.core.application.runtime_prompt.grpc.config import (
    RUNTIME_PROMPT_AUTH_AUDIENCE,
    RUNTIME_PROMPT_AUTH_SCOPE,
    runtime_prompt_grpc_options,
    runtime_prompt_target,
    runtime_prompt_timeout_seconds,
)
from democrai.core.application.runtime_prompt.grpc.proto import (
    runtime_prompt_pb2,
    runtime_prompt_pb2_grpc,
)
from democrai.core.application.runtime_prompt.models import RuntimePromptDecision
from democrai.core.runtime.foundation.app import app_ctx


class RuntimePromptClient:
    def __init__(
        self,
        *,
        target: str | None = None,
        timeout: float | None = None,
    ) -> None:
        config = app_ctx().config
        self._target = str(target or runtime_prompt_target(config)).strip()
        self._timeout = (
            float(timeout)
            if timeout is not None
            else runtime_prompt_timeout_seconds(config)
        )
        self._options = runtime_prompt_grpc_options(config)
        self._channel = None

    def _stub(self):
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(
                self._target,
                options=self._options,
        )
        return runtime_prompt_pb2_grpc.RuntimePromptStub(self._channel)

    def _auth_metadata(self) -> tuple[tuple[str, str], ...]:
        return internal_service_auth_metadata(
            audience=RUNTIME_PROMPT_AUTH_AUDIENCE,
            scopes=(RUNTIME_PROMPT_AUTH_SCOPE,),
        )

    async def close(self) -> None:
        channel = self._channel
        self._channel = None
        if channel is not None:
            await channel.close()

    async def ask(
        self,
        *,
        question: str,
        actions: list[dict[str, Any]],
        required_role: str | None = None,
        required_access_level: int | None = None,
        required_permissions: list[str] | tuple[str, ...] | None = None,
        form_model: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
        form_values: dict[str, Any] | None = None,
        request_context: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        timeout_seconds: float = 300.0,
    ) -> RuntimePromptDecision:
        request = runtime_prompt_pb2.RuntimePromptRequest(
            request_id=str(request_context.get("request_id") or ""),
            question=str(question or ""),
            actions_json=json.dumps(list(actions or []), ensure_ascii=True),
            required_role=str(required_role or ""),
            required_access_level=int(required_access_level or 0),
            required_permissions_json=json.dumps(
                list(required_permissions or []),
                ensure_ascii=True,
            ),
            request_context_json=json.dumps(dict(request_context or {}), ensure_ascii=True),
            metadata_json=json.dumps(dict(metadata or {}), ensure_ascii=True),
            timeout_seconds=float(timeout_seconds or 300.0),
            form_model_json=json.dumps(list(form_model or []), ensure_ascii=True),
            form_values_json=json.dumps(dict(form_values or {}), ensure_ascii=True),
        )
        try:
            response = await self._stub().AskRuntimePrompt(
                request,
                timeout=self._timeout,
                metadata=self._auth_metadata(),
            )
        except grpc.aio.AioRpcError as exc:
            raise RuntimeError(f"{exc.code().name}:{exc.details()}") from exc
        metadata_payload = {}
        raw_metadata = str(response.metadata_json or "").strip()
        if raw_metadata:
            metadata_payload = json.loads(raw_metadata)
        data_payload = {}
        raw_data = str(response.data_json or "").strip()
        if raw_data:
            data_payload = json.loads(raw_data)
        return RuntimePromptDecision(
            ok=bool(response.ok),
            prompt_id=str(response.prompt_id or ""),
            action=str(response.action or "").strip() or None,
            data=data_payload if isinstance(data_payload, dict) else {},
            error=str(response.error or "").strip() or None,
            metadata=metadata_payload if isinstance(metadata_payload, dict) else {},
        )
