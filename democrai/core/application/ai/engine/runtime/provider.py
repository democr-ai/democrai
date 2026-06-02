from __future__ import annotations

import asyncio
import inspect
import sys
from typing import Any

from democrai.core.application.ai.engine.base.llm import current_ai_call_context
from democrai.core.application.ai.engine.pipeline.execution import (
    generate_completion_pipeline,
)
from democrai.core.application.ai.engine.pipeline.execution import (
    generate_stream_pipeline,
)
from democrai.core.application.ai.engine.runtime.invocation import invoke_with_usage
from democrai.core.application.ai.engine.runtime.invocation import invoke_stream_with_usage
from democrai.core.application.ai.engine.runtime.requests import (
    register_runtime_request,
)
from democrai.core.application.ai.engine.runtime.requests import (
    unregister_runtime_request,
)
from democrai.core.application.ai.engine.schemas.completion import CompletionResponse
from democrai.core.application.ai.engine.schemas.audio import SpeechResponse
from democrai.core.application.ai.engine.schemas.audio import SpeechUsage
from democrai.core.application.ai.engine.schemas.runtime import EngineMethodResponse
from democrai.core.application.knowledge.ai_capture import ingest_ai_completion_call
from democrai.core.application.ai.pipeline_context import ai_pipeline_context
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.pipeline_context import create_ai_pipeline_context
from democrai.core.runtime.foundation.app import app_ctx


def _message_storage_paths(messages) -> tuple[str, ...]:
    paths: list[str] = []
    for message in list(messages or []):
        content = (
            message.get("content")
            if isinstance(message, dict)
            else getattr(message, "content", None)
        )
        if not isinstance(content, list):
            continue
        for part in content:
            storage_path = (
                part.get("storage_path")
                if isinstance(part, dict)
                else getattr(part, "storage_path", None)
            )
            rendered = str(storage_path or "").strip()
            if rendered:
                paths.append(rendered)
    return tuple(dict.fromkeys(paths))


def _knowledge_repository():
    service = getattr(app_ctx(), "knowledge_service", None)
    repository = getattr(service, "repository", None)
    if repository is not None:
        return repository
    from democrai.core.application.knowledge.repository import KnowledgeRepository
    from democrai.core.infrastructure.database import SessionLocal

    return KnowledgeRepository(SessionLocal)


def _pipeline_metadata(ingest_meta: dict[str, Any] | None) -> dict[str, Any]:
    metadata = {}
    ai_context = current_ai_call_context()
    context_metadata = ai_context.get("metadata")
    if isinstance(context_metadata, dict):
        metadata.update(context_metadata)
    if isinstance(ingest_meta, dict):
        metadata.update(ingest_meta)
    return metadata


class EngineRuntimeProvider:
    """
    Adapter that exposes provider-like methods by delegating execution to EngineRuntime.
    """

    def __init__(
        self,
        *,
        engine_row_id: int,
        model_registry_id: int,
        engine_id: str,
        config: dict[str, Any],
    ):
        if model_registry_id <= 0:
            raise ValueError("engine_runtime_model_registry_id_required")
        self.engine_row_id = engine_row_id
        self.model_registry_id = model_registry_id
        self.engine_id = engine_id
        self.config = dict(config)

    @staticmethod
    async def _call_callback(callback: Any, *args: Any) -> None:
        if callback is None:
            return
        result = callback(*args)
        if inspect.isawaitable(result):
            await result

    def _invoke(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        resolved_payload = dict(payload) if payload is not None else {}
        ai_context = current_ai_call_context()
        if ai_context:
            resolved_payload["__ai_call_context"] = ai_context
        from democrai.core.application.ai.engine.runtime.manager import get_engine_runtime

        return get_engine_runtime().invoke(
            engine_row_id=self.engine_row_id,
            model_registry_id=self.model_registry_id,
            engine_id=self.engine_id,
            config=self.config,
            method=method,
            payload=resolved_payload,
        )

    async def _invoke_stream(self, method: str, payload: dict[str, Any] | None = None):
        resolved_payload = dict(payload) if payload is not None else {}
        ai_context = current_ai_call_context()
        if ai_context:
            resolved_payload["__ai_call_context"] = ai_context
        from democrai.core.application.ai.engine.runtime.manager import get_engine_runtime

        async for item in get_engine_runtime().invoke_stream(
            engine_row_id=self.engine_row_id,
            model_registry_id=self.model_registry_id,
            engine_id=self.engine_id,
            config=self.config,
            method=method,
            payload=resolved_payload,
        ):
            yield item

    async def _invoke_with_usage(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
        metadata_from_result: Any = None,
    ) -> Any:
        return await invoke_with_usage(
            self,
            method,
            payload,
            metadata=metadata,
            metadata_from_result=metadata_from_result,
        )

    async def _invoke_stream_with_usage(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
        metadata_from_result: Any = None,
    ):
        async for item in invoke_stream_with_usage(
            self,
            method,
            payload,
            metadata=metadata,
            metadata_from_result=metadata_from_result,
        ):
            yield item

    def _cancel_request(self, request_id: str) -> bool:
        from democrai.core.application.ai.engine.runtime.manager import get_engine_runtime

        return get_engine_runtime().cancel_request(
            engine_row_id=self.engine_row_id,
            request_id=request_id,
        )

    def _link_message_uploads_to_pipeline(
        self,
        *,
        context,
        messages,
        ingest_meta: dict[str, Any] | None,
    ) -> None:
        storage_paths = _message_storage_paths(messages)
        if not storage_paths:
            return
        repository = _knowledge_repository()
        pipeline_context = dict(ingest_meta or {})
        pipeline_context.update({
            "pipeline_id": context.pipeline_id,
            "current_pipeline_id": context.current_pipeline_id,
            "parent_pipeline_id": context.parent_pipeline_id,
            "request_id": context.request_id,
            "root_method": context.root_method,
            "provider": context.provider,
            "engine": context.engine,
            "engine_row_id": context.engine_row_id,
            "model_registry_id": context.model_registry_id,
            "model_name": context.model_name,
        })
        for storage_path in storage_paths:
            repository.link_chat_upload_context(
                storage_path=storage_path,
                pipeline_id=context.pipeline_id,
                context=pipeline_context,
            )

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
        context = create_ai_pipeline_context(
            root_method="generate_completion",
            provider=self.engine_id or None,
            engine=self.engine_id or None,
            engine_row_id=self.engine_row_id,
            model_registry_id=self.model_registry_id,
            model_name=str(
                self.config.get("model") or self.config.get("model_path") or ""
            ).strip()
            or None,
            metadata=_pipeline_metadata(ingest_meta),
            on_message=on_message,
        )
        self._link_message_uploads_to_pipeline(
            context=context,
            messages=messages,
            ingest_meta=ingest_meta,
        )
        if on_response is None and on_error is None:
            with ai_pipeline_context(context):
                async with ai_pipeline_step(type="request", name="generate_completion"):
                    response = await generate_completion_pipeline(
                        self,
                        messages=messages,
                        options=options,
                    )
                    response = response.model_copy(
                        update={
                            "request_id": context.request_id,
                            "pipeline_id": context.pipeline_id,
                            "current_pipeline_id": context.current_pipeline_id,
                            "parent_pipeline_id": context.parent_pipeline_id,
                            "status": response.status or "ok",
                        }
                    )
                    if ingest:
                        ingest_ai_completion_call(
                            context=context,
                            method="generate_completion",
                            messages=messages,
                            response=response,
                            ingest_meta=ingest_meta,
                        )
                    return response

        request_id = context.request_id

        async def _run() -> None:
            with ai_pipeline_context(context):
                try:
                    async with ai_pipeline_step(type="request", name="generate_completion"):
                        response = await generate_completion_pipeline(
                            self,
                            messages=messages,
                            options=options,
                        )
                    response = response.model_copy(
                        update={
                            "request_id": context.request_id,
                            "pipeline_id": context.pipeline_id,
                            "current_pipeline_id": context.current_pipeline_id,
                            "parent_pipeline_id": context.parent_pipeline_id,
                            "status": response.status or "ok",
                        }
                    )
                    if ingest:
                        ingest_ai_completion_call(
                            context=context,
                            method="generate_completion",
                            messages=messages,
                            response=response,
                            ingest_meta=ingest_meta,
                        )
                    await self._call_callback(on_response, response)
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    _log_engine_runtime_provider_error(
                        generator="completion:generate_completion",
                        error=exc,
                    )
                    if on_error is not None:
                        await self._call_callback(on_error, exc)
                    else:
                        raise
                finally:
                    unregister_runtime_request(request_id, task)

        task = asyncio.create_task(_run(), name=f"engine-generate-completion:{request_id}")
        register_runtime_request(request_id, task, cancel=self._cancel_request)
        return CompletionResponse(
            id=request_id,
            request_id=request_id,
            status="running",
            pipeline_id=context.pipeline_id,
            current_pipeline_id=context.current_pipeline_id,
            parent_pipeline_id=context.parent_pipeline_id,
        )

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
        context = create_ai_pipeline_context(
            root_method="generate_stream",
            request_id=request_id,
            provider=self.engine_id or None,
            engine=self.engine_id or None,
            engine_row_id=self.engine_row_id,
            model_registry_id=self.model_registry_id,
            model_name=str(self.config.get("model") or self.config.get("model_path") or "").strip()
            or None,
            metadata=_pipeline_metadata(ingest_meta),
            on_message=on_message,
        )
        self._link_message_uploads_to_pipeline(
            context=context,
            messages=messages,
            ingest_meta=ingest_meta,
        )
        task = asyncio.current_task()
        if task is not None:
            register_runtime_request(
                context.request_id,
                task,
                cancel=self._cancel_request,
            )
        with ai_pipeline_context(context):
            try:
                async with ai_pipeline_step(type="request", name="generate_stream"):
                    chunks: list[Any] = []
                    async for item in generate_stream_pipeline(
                        self,
                        messages=messages,
                        options=options,
                    ):
                        if getattr(item, "delta", None):
                            chunks.append(item)
                        yield item
                    if ingest:
                        ingest_ai_completion_call(
                            context=context,
                            method="generate_stream",
                            messages=messages,
                            stream_chunks=chunks,
                            ingest_meta=ingest_meta,
                        )
            except Exception as exc:
                _log_engine_runtime_provider_error(
                    generator="stream:generate_stream",
                    error=exc,
                )
                raise
            finally:
                if task is not None:
                    unregister_runtime_request(context.request_id, task)

    async def embed_texts(self, texts):
        return await self._invoke_with_usage(
            "embed_texts",
            {"texts": texts},
            metadata={
                "input_count": len(texts or []) if isinstance(texts, list) else None
            },
        )

    async def rerank(self, query, texts, options=None):
        return await self._invoke_with_usage(
            "rerank",
            {"query": query, "texts": texts, "options": options},
            metadata={
                "input_count": len(texts or []) if isinstance(texts, list) else None
            },
        )

    async def classify(self, texts, options=None):
        return await self._invoke_with_usage(
            "classify",
            {"texts": texts, "options": options},
            metadata={
                "input_count": len(texts or []) if isinstance(texts, list) else None
            },
        )

    async def extract_tokens(self, text):
        return await self._invoke_with_usage(
            "extract_tokens",
            {"text": text},
            metadata={"input_count": 1 if text else 0},
        )

    async def extract_triples(
        self,
        *,
        kind,
        title=None,
        summary=None,
        content,
        options=None,
    ):
        return await self._invoke_with_usage(
            "extract_triples",
            {
                "kind": kind,
                "title": title,
                "summary": summary,
                "content": content,
                "options": options,
            },
            metadata={"input_count": 1 if content else 0},
        )

    async def transcribe(self, audio_data, language=None):
        return await self._invoke_with_usage(
            "transcribe",
            {"audio_data": audio_data, "language": language},
        )

    async def synthesize(self, text, options=None):
        result = await self._invoke_with_usage(
            "synthesize",
            {"text": text, "options": options},
            metadata={"input_characters": len(str(text or ""))},
        )
        return _speech_response(result, text=text)

    async def synthesize_stream(self, text, options=None):
        async for item in self._invoke_stream_with_usage(
            "synthesize_stream",
            {"text": text, "options": options},
            metadata={"input_characters": len(str(text or ""))},
            metadata_from_result=lambda result: {
                "chunks": len(result) if isinstance(result, list) else None
            },
        ):
            yield item

    async def detect(self, *args, **kwargs):
        payload = dict(kwargs)
        if args:
            payload["args"] = list(args)
        return await self._invoke_with_usage("detect", payload)

    async def get_detections(self, *args, **kwargs):
        payload = dict(kwargs)
        if args:
            payload["args"] = list(args)
        return await self._invoke_with_usage("get_detections", payload)


def _speech_response(result: Any, *, text: Any) -> Any:
    if isinstance(result, EngineMethodResponse):
        resolved = _speech_response(result.result, text=text)
        return EngineMethodResponse(
            result=resolved,
            usage=result.usage,
            duration_ms=result.duration_ms,
            tokens_per_second=result.tokens_per_second,
            metadata=result.metadata,
        )
    if isinstance(result, SpeechResponse):
        usage = result.usage or SpeechUsage()
        return result.model_copy(
            update={
                "usage": usage.model_copy(
                    update={
                        "input_characters": usage.input_characters
                        or len(str(text or "")),
                        "audio_bytes": usage.audio_bytes or len(result.data or b""),
                    }
                ),
                "tokens_per_second": result.tokens_per_second or 0.0,
            }
        )
    if not isinstance(result, dict):
        return result
    data = result.get("data")
    if not isinstance(data, bytes | bytearray):
        return result
    usage = result.get("usage")
    if isinstance(usage, SpeechUsage):
        resolved_usage = usage
    elif isinstance(usage, dict):
        resolved_usage = SpeechUsage(**usage)
    else:
        resolved_usage = SpeechUsage()
    return SpeechResponse(
        data=bytes(data),
        content_type=str(result.get("content_type") or "audio/mpeg"),
        duration=result.get("duration"),
        usage=resolved_usage.model_copy(
            update={
                "input_characters": resolved_usage.input_characters
                or len(str(text or "")),
                "audio_bytes": resolved_usage.audio_bytes or len(data),
            }
        ),
        tokens_per_second=float(result.get("tokens_per_second") or 0.0),
    )


def _log_engine_runtime_provider_error(
    *,
    generator: str,
    error: BaseException,
) -> None:
    try:
        logger = app_ctx().logger
        if logger is None:
            return
        logger.error(
            "[AI Pipeline] engine runtime provider failed "
            f"generator={generator} error_type={type(error).__name__} error={error}",
            exc_info=sys.exc_info()
            if sys.exc_info()[1] is error
            else (type(error), error, error.__traceback__),
        )
    except Exception:
        pass
