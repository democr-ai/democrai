from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from democrai.core.application.ai.engine.orchestrator.client import (
    EngineOrchestratorClient,
)
from democrai.core.application.ai.engine.base.llm import current_ai_call_context
from democrai.core.application.ai.engine.runtime.requests import (
    register_runtime_request,
    unregister_runtime_request,
)
from democrai.core.application.ai.engine.schemas.completion import CompletionResponse
from democrai.core.platform.utils.identity import to_int_or_zero


def _consume_task_exception(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    try:
        task.exception()
    except Exception:
        return


class RemoteEngineProvider:
    def __init__(
        self,
        *,
        selector_type: str,
        model_registry_id: int | None = None,
        objective: str | None = None,
        capability: str | None = None,
        capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
        client: EngineOrchestratorClient | None = None,
    ) -> None:
        self.selector_type = selector_type
        self.model_registry_id = to_int_or_zero(model_registry_id) or None
        self.objective = objective
        self.capability = capability
        self.capabilities = list(capabilities or [])
        self.prefer_local = prefer_local
        self.confirm_swap = confirm_swap
        self._client = client or EngineOrchestratorClient()

    async def _invoke(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
    ) -> Any:
        return await self._client.invoke(
            selector_type=self.selector_type,
            model_registry_id=self.model_registry_id,
            objective=self.objective,
            capability=self.capability,
            capabilities=self.capabilities,
            prefer_local=self.prefer_local,
            confirm_swap=self.confirm_swap,
            method=method,
            payload=payload,
            request_id=request_id,
        )

    async def validate(self) -> dict[str, Any]:
        result = await self._invoke("__validate_provider__", {})
        if not isinstance(result, dict):
            raise RuntimeError("engine_orchestrator_validate_result_dict_required")
        return result

    async def warmup(self, *, wait: bool = True) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        if wait:
            started = time.perf_counter()
            result = await self._invoke(
                "__warmup_provider__",
                {},
                request_id=request_id,
            )
            if not isinstance(result, dict):
                raise RuntimeError("engine_orchestrator_warmup_result_dict_required")
            payload = result.copy()
            payload.setdefault("status", "ok")
            payload["request_id"] = request_id
            payload["warmup_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
            return payload

        async def _run() -> None:
            await self._invoke(
                "__warmup_provider__",
                {},
                request_id=request_id,
            )

        task = asyncio.create_task(
            _run(),
            name=f"remote-engine-warmup:{request_id}",
        )
        task.add_done_callback(_consume_task_exception)
        return {
            "status": "queued",
            "request_id": request_id,
            "selector_type": self.selector_type,
            "model_registry_id": self.model_registry_id,
            "objective": self.objective,
        }

    async def _invoke_stream(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        on_message: Any = None,
    ):
        async for item in self._client.invoke_stream(
            selector_type=self.selector_type,
            model_registry_id=self.model_registry_id,
            objective=self.objective,
            capability=self.capability,
            capabilities=self.capabilities,
            prefer_local=self.prefer_local,
            confirm_swap=self.confirm_swap,
            method=method,
            payload=payload,
            request_id=request_id,
            on_message=on_message,
        ):
            yield item

    async def _call_callback(self, callback: Any, *args: Any) -> None:
        if callback is None:
            return
        result = callback(*args)
        if asyncio.iscoroutine(result):
            await result

    @staticmethod
    def _ingest_meta(ingest_meta: dict[str, Any] | None) -> dict[str, Any]:
        metadata = {}
        context_metadata = current_ai_call_context().get("metadata")
        if isinstance(context_metadata, dict):
            metadata.update(context_metadata)
        if isinstance(ingest_meta, dict):
            metadata.update(ingest_meta)
        return metadata

    async def generate_completion(
        self,
        messages=None,
        options=None,
        *,
        on_response: Any = None,
        on_error: Any = None,
        on_message: Any = None,
        ingest: bool = False,
        ingest_meta: dict[str, Any] | None = None,
    ):
        if on_response is None and on_error is None and on_message is None:
            return await self._invoke(
                "generate_completion",
                {
                    "messages": messages,
                    "options": options,
                    "ingest": ingest,
                    "ingest_meta": self._ingest_meta(ingest_meta),
                },
            )

        request_id = uuid.uuid4().hex

        if on_response is None and on_error is None:
            response = None
            async for item in self._invoke_stream(
                "generate_completion",
                {
                    "messages": messages,
                    "options": options,
                    "_stream_pipeline_messages": True,
                    "ingest": ingest,
                    "ingest_meta": self._ingest_meta(ingest_meta),
                },
                request_id=request_id,
                on_message=on_message,
            ):
                response = item
            return response

        async def _run() -> None:
            try:
                response = None
                async for item in self._invoke_stream(
                    "generate_completion",
                    {
                        "messages": messages,
                        "options": options,
                        "_stream_pipeline_messages": on_message is not None,
                        "ingest": ingest,
                        "ingest_meta": self._ingest_meta(ingest_meta),
                    },
                    request_id=request_id,
                    on_message=on_message,
                ):
                    response = item
                await self._call_callback(on_response, response)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if on_error is not None:
                    await self._call_callback(on_error, exc)
                    return
                raise
            finally:
                unregister_runtime_request(request_id, task)

        task = asyncio.create_task(_run(), name=f"remote-engine-completion:{request_id}")
        register_runtime_request(
            request_id,
            task,
            cancel=lambda rid: self._client.cancel_sync(rid),
        )
        return CompletionResponse(id=request_id, request_id=request_id, status="running")

    async def embed_texts(self, texts):
        return await self._invoke("embed_texts", {"texts": texts})

    async def generate_stream(
        self,
        messages=None,
        options=None,
        *,
        request_id: str | None = None,
        on_message: Any = None,
        ingest: bool = False,
        ingest_meta: dict[str, Any] | None = None,
    ):
        resolved_request_id = request_id or uuid.uuid4().hex
        task = asyncio.current_task()
        if task is not None:
            register_runtime_request(
                resolved_request_id,
                task,
                cancel=lambda rid: self._client.cancel_sync(rid),
            )
        try:
            async for item in self._invoke_stream(
                "generate_stream",
                {
                    "messages": messages,
                    "options": options,
                    "_stream_pipeline_messages": on_message is not None,
                    "ingest": ingest,
                    "ingest_meta": self._ingest_meta(ingest_meta),
                },
                request_id=resolved_request_id,
                on_message=on_message,
            ):
                yield item
        finally:
            if task is not None:
                unregister_runtime_request(resolved_request_id, task)

    async def rerank(self, query, texts, options=None):
        return await self._invoke(
            "rerank",
            {"query": query, "texts": texts, "options": options},
        )

    async def classify(self, texts, options=None):
        return await self._invoke("classify", {"texts": texts, "options": options})

    async def extract_tokens(self, text):
        return await self._invoke("extract_tokens", {"text": text})

    async def extract_triples(
        self,
        *,
        kind,
        title=None,
        summary=None,
        content,
        options=None,
    ):
        return await self._invoke(
            "extract_triples",
            {
                "kind": kind,
                "title": title,
                "summary": summary,
                "content": content,
                "options": options,
            },
        )

    async def transcribe(self, audio_data, language=None):
        return await self._invoke(
            "transcribe",
            {"audio_data": audio_data, "language": language},
        )

    async def synthesize(self, text, options=None):
        return await self._invoke("synthesize", {"text": text, "options": options})

    async def synthesize_stream(self, text, options=None):
        async for item in self._invoke_stream(
            "synthesize_stream",
            {"text": text, "options": options},
        ):
            yield item

    async def detect(self, *args, **kwargs):
        payload = dict(kwargs)
        if args:
            payload["args"] = list(args)
        return await self._invoke("detect", payload)

    async def get_detections(self, *args, **kwargs):
        payload = dict(kwargs)
        if args:
            payload["args"] = list(args)
        return await self._invoke("get_detections", payload)
