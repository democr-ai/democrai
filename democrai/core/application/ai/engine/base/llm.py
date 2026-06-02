from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar
import json
import sys
import time
from typing import Any, AsyncGenerator, Iterator, List, Optional

from democrai.core.application.ai.engine.schemas.completion import (
    ClassificationOptions,
    ClassificationResult,
    CompletionOptions,
    CompletionResponse,
    Message,
    RerankOptions,
    RerankResult,
    StreamChunk,
    TokenExtractionResult,
)
from democrai.core.application.ai.output_parsers import ParsedModelOutput
from democrai.core.application.ai.output_parsers import get_output_parser
from democrai.core.application.ai.pipeline_context import emit_ai_pipeline_event
from democrai.core.application.ai.security.prompt.messages import (
    normalize_prompt_messages,
)
from democrai.core.runtime.foundation.app import app_ctx


_ai_call_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "democrai_ai_call_context",
    default=None,
)


@contextmanager
def ai_call_context(**values: Any) -> Iterator[None]:
    """Attach observability metadata to provider calls in the current flow."""
    current = dict(_ai_call_context.get() or {})
    metadata = dict(current.get("metadata") or {})
    incoming_metadata = values.pop("metadata", None)
    if isinstance(incoming_metadata, dict):
        metadata.update(incoming_metadata)
    current.update({key: value for key, value in values.items() if value is not None})
    if metadata:
        current["metadata"] = metadata
    token = _ai_call_context.set(current)
    try:
        yield
    finally:
        _ai_call_context.reset(token)


def current_ai_call_context() -> dict[str, Any]:
    return dict(_ai_call_context.get() or {})


def _completion_messages(value: Any) -> list[Message]:
    if not isinstance(value, list):
        raise TypeError("completion_messages_list_expected")
    return normalize_prompt_messages(value)


def _completion_options(value: Any) -> CompletionOptions:
    if isinstance(value, CompletionOptions):
        return value
    if isinstance(value, dict):
        return CompletionOptions(**value)
    raise TypeError("completion_options_expected")


def _usage_float(value: Any, key: str) -> float | None:
    raw = getattr(value, key, None)
    return float(raw) if isinstance(raw, (int, float)) else None


def _usage_tuple(
    response: Any,
) -> tuple[int | None, int | None, int | None, float | None]:
    if not isinstance(response, CompletionResponse):
        return None, None, None, None
    usage = response.usage
    tokens_per_second = _usage_float(response, "tokens_per_second")
    if usage is None:
        return None, None, None, tokens_per_second
    return (
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
        tokens_per_second,
    )


def _chunk_usage(
    chunk: StreamChunk,
) -> tuple[int | None, int | None, int | None, float | None]:
    tokens_per_second = _usage_float(chunk, "tokens_per_second")
    return (
        chunk.prompt_tokens,
        chunk.completion_tokens,
        chunk.total_tokens,
        tokens_per_second,
    )


def _completion_tokens_per_second(
    response: Any,
    *,
    duration_ms: float,
) -> float | None:
    if not isinstance(response, CompletionResponse):
        return None
    if response.tokens_per_second is not None:
        return response.tokens_per_second
    usage = response.usage
    completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
    if not completion_tokens or duration_ms <= 0:
        return None
    return _tokens_per_second(
        completion_tokens=completion_tokens,
        duration_ms=duration_ms,
    )


def _tokens_per_second(
    *,
    completion_tokens: int | float | None,
    duration_ms: float,
) -> float | None:
    if not completion_tokens or duration_ms <= 0:
        return None
    return round(float(completion_tokens) / (duration_ms / 1000.0), 2)


def _engine_config(provider: Any) -> dict[str, Any]:
    config = getattr(provider, "config", None)
    return config if isinstance(config, dict) else {}


def _output_parser_name(provider: Any) -> str | None:
    config = _engine_config(provider)
    output_parser = config.get("output_parser")
    reasoning_parser = str(config.get("reasoning_parser") or "").strip()
    if reasoning_parser and output_parser in (None, "", "generic", "hermes"):
        return reasoning_parser
    return str(output_parser).strip() if output_parser is not None else None


def _is_dev_runtime() -> bool:
    return app_ctx().dev


def _tool_calls_debug(value: Any) -> list[dict[str, Any]]:
    calls = list(value or [])
    result: list[dict[str, Any]] = []
    for call in calls:
        result.append(
            {
                "id": getattr(call, "id", None),
                "function_name": getattr(call, "function_name", None),
                "arguments": getattr(call, "arguments", None),
            }
        )
    return result


def _raw_debug(provider: Any, event: str, payload: dict[str, Any]) -> None:
    if not _is_dev_runtime():
        return
    record = {
        "event": event,
        **payload,
    }


def _request_params_debug(
    messages: list[Message],
    options: CompletionOptions,
) -> dict[str, Any]:
    return {
        "messages": [message.model_dump(mode="python") for message in messages],
        "options": options.model_dump(mode="python"),
    }


def _diagnostic_raw_enabled(options: CompletionOptions) -> bool:
    extra = options.extra if isinstance(options.extra, dict) else {}
    if extra.get("diagnostic_raw"):
        return True
    return _diagnostic_raw_config_enabled()


def _diagnostic_raw_config_enabled() -> bool:
    try:
        config = getattr(app_ctx(), "config", None)
        if config is None:
            return False
        return bool(config.get("ai.pipeline.diagnostic_raw", False))
    except Exception:
        return False


async def _emit_diagnostic_raw(
    *,
    event: str,
    payload: dict[str, Any],
    options: CompletionOptions,
) -> None:
    from democrai.core.runtime.foundation.app import app_ctx

    app_ctx().logger.debug(f"[LLM] DEBUG DATA {event}\n", name="_LLM")
    # if not _diagnostic_raw_enabled(options):
    # return
    # await emit_ai_pipeline_event(
    # type="llm.diagnostic_raw",
    # name=event,
    # payload=payload,
    # )


def _completion_debug_payload(response: CompletionResponse) -> dict[str, Any]:
    return {
        "content": response.content,
        "reasoning": response.reasoning,
        "tool_calls": _tool_calls_debug(response.tool_calls),
        "finish_reason": response.finish_reason,
        "status": response.status,
    }


def _diagnostic_completion_payload(
    *,
    parser_name: str | None,
    raw_response: CompletionResponse,
    parsed_response: CompletionResponse,
) -> dict[str, Any]:
    return {
        "parser": parser_name,
        "raw": _completion_debug_payload(raw_response),
        "parsed": _completion_debug_payload(parsed_response),
        "parser_changed": parsed_response != raw_response,
    }


def _diagnostic_raw_preview(text: str | None, *, limit: int = 240) -> str:
    resolved = (text or "").strip().replace("\n", "\\n")
    if len(resolved) <= limit:
        return resolved
    return resolved[:limit] + f"…(+{len(resolved) - limit} char)"


def _log_completion_parse_outcome(
    provider: Any,
    *,
    generator: str,
    parser_name: str | None,
    raw_response: CompletionResponse,
    parsed_response: CompletionResponse,
    verbose: bool,
) -> None:
    """Una riga leggibile su cosa il modello ha prodotto vs cosa e' sopravvissuto
    al parser.

    Di default tace: stampa solo l'**anomalia** — il parsed e' vuoto (niente
    content e niente tool call) pur avendo il modello generato del grezzo. Tag
    ``EMPTY_PARSE`` greppabile, livello error, cosi' lo trovi in mezzo al rumore.
    Con ``verbose`` (config ``ai.pipeline.diagnostic_raw``) stampa ogni chiamata
    col tag ``raw diagnostic``."""
    try:
        raw_content = raw_response.content or ""
        parsed_content = (parsed_response.content or "").strip()
        parsed_tools = parsed_response.tool_calls or []
        empty = (
            not parsed_content
            and not parsed_tools
            and bool(
                raw_content.strip() or raw_response.reasoning or raw_response.tool_calls
            )
        )
        if not empty and not verbose:
            return
        logger = getattr(app_ctx(), "logger", None)
        if logger is None:
            return
        tag = "EMPTY_PARSE" if empty else "raw diagnostic"
        message = (
            f"[AI Pipeline] {tag} "
            f"generator={generator} parser={parser_name or 'generic'} "
            f"parser_changed={parsed_response != raw_response} "
            f"raw_content_len={len(raw_content)} parsed_content_len={len(parsed_content)} "
            f"raw_tool_calls={len(raw_response.tool_calls or [])} "
            f"parsed_tool_calls={len(parsed_tools)} "
            f"reasoning_len={len(parsed_response.reasoning or raw_response.reasoning or '')} "
            f"finish_reason={raw_response.finish_reason} "
            f'raw_preview="{_diagnostic_raw_preview(raw_content)}"'
        )
        (logger.error if empty else logger.warning)(message)
    except Exception:
        pass


def _apply_completion_parser(
    provider: Any,
    response: CompletionResponse,
) -> CompletionResponse:
    parser = get_output_parser(_output_parser_name(provider))
    parsed = parser.parse(response.content or "")
    if (
        parsed.content == response.content
        and not parsed.reasoning
        and not parsed.tool_calls
    ):
        return response
    return response.model_copy(
        update={
            "content": parsed.content,
            "reasoning": response.reasoning or parsed.reasoning,
            "tool_calls": response.tool_calls or parsed.tool_calls or None,
        }
    )


def _parsed_stream_chunks(
    chunk_id: str,
    parsed: ParsedModelOutput,
) -> list[StreamChunk]:
    chunks = [
        StreamChunk(
            id=chunk_id,
            tool_call_delta=tool_call,
            finish_reason=None,
        )
        for tool_call in parsed.tool_calls
    ]
    if parsed.reasoning:
        chunks.append(
            StreamChunk(
                id=chunk_id,
                reasoning=parsed.reasoning,
                finish_reason=None,
            )
        )
    if parsed.content:
        chunks.append(
            StreamChunk(
                id=chunk_id,
                delta=parsed.content,
                finish_reason=None,
            )
        )
    return chunks


def _log_llm_provider_error(
    provider: Any,
    *,
    generator: str,
    error: BaseException,
) -> None:
    try:
        logger = getattr(app_ctx(), "logger", None)
        if logger is None:
            return
        provider_name = (
            getattr(provider, "_democrai_provider_name", None)
            or provider.__class__.__name__
        )
        logger.error(
            "[AI Pipeline] llm provider failed "
            f"generator={generator} provider={provider_name} "
            f"error_type={type(error).__name__} error={error}",
            exc_info=sys.exc_info()
            if sys.exc_info()[1] is error
            else (type(error), error, error.__traceback__),
        )
    except Exception:
        pass


def _log_max_output_tokens(
    provider: Any,
    *,
    generator: str,
    finish_reason: str | None,
    completion_tokens: int | None,
    max_tokens: int | None,
) -> bool:
    if max_tokens is None:
        return False
    reason = (finish_reason or "").strip().lower()
    reached_limit = reason in {
        "length",
        "max_tokens",
        "max_token",
        "token_limit",
        "output_token_limit",
        "output_tokens",
    }
    if not reached_limit and (
        completion_tokens is None or completion_tokens < max_tokens
    ):
        return False
    provider_name = (
        getattr(provider, "_democrai_provider_name", None)
        or provider.__class__.__name__
    )
    app_ctx().logger.error(
        f"[LLM] output reached max tokens {provider_name} tok: {max_tokens} comp_tokens: {completion_tokens} reason: {reason}\n",
        name="_LLM",
    )
    return True


class LLMProvider(ABC):
    """LLM capability contract, separate from engine lifecycle."""

    async def generate_completion(
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        resolved_messages = _completion_messages(messages)
        resolved_options = _completion_options(options)
        started_at = time.perf_counter()
        error: Exception | None = None
        response: Any = None
        try:
            await _emit_diagnostic_raw(
                event="generate_completion.request",
                payload={
                    "params": _request_params_debug(
                        resolved_messages, resolved_options
                    ),
                    "parser": _output_parser_name(self),
                },
                options=resolved_options,
            )
            response = await self._generate_completion(
                resolved_messages,
                resolved_options,
            )
            raw_response = response

            await _emit_diagnostic_raw(
                event="generate_completion.raw_output",
                payload=_completion_debug_payload(response),
                options=resolved_options,
            )
            response = _apply_completion_parser(self, response)
            await _emit_diagnostic_raw(
                event="generate_completion.parsed_output",
                payload={
                    **_completion_debug_payload(response),
                    "parser": _output_parser_name(self),
                    "parser_changed": response != raw_response,
                },
                options=resolved_options,
            )

            if _diagnostic_raw_enabled(resolved_options):
                response = response.model_copy(
                    update={
                        "diagnostic_raw": _diagnostic_completion_payload(
                            parser_name=_output_parser_name(self),
                            raw_response=raw_response,
                            parsed_response=response,
                        )
                    }
                )
            tokens_per_second = _completion_tokens_per_second(
                response,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
            )
            if tokens_per_second is not None and response.tokens_per_second is None:
                response = response.model_copy(
                    update={"tokens_per_second": tokens_per_second}
                )
            _, completion_tokens, _, _ = _usage_tuple(response)

            return response
        except Exception as exc:
            raise
        finally:
            (
                prompt_tokens,
                completion_tokens,
                total_tokens,
                tokens_per_second,
            ) = _usage_tuple(response)
            self._record_ai_model_usage(
                request_kind="completion",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                tokens_per_second=tokens_per_second,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
                success=error is None,
                error=str(error) if error is not None else None,
            )

    async def generate_stream(
        self,
        messages: List[Message],
        options: CompletionOptions,
        *,
        request_id: str | None = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        resolved_messages = _completion_messages(messages)
        resolved_options = _completion_options(options)
        started_at = time.perf_counter()
        chunk_count = 0
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        total_tokens: int | None = None
        tokens_per_second: float | None = None
        last_chunk_id = "stream"
        success = False
        error: Exception | None = None
        output_limit_logged = False
        try:
            await _emit_diagnostic_raw(
                event="generate_stream.request",
                payload={
                    "params": _request_params_debug(
                        resolved_messages, resolved_options
                    ),
                    "parser": _output_parser_name(self),
                },
                options=resolved_options,
            )
            parser = get_output_parser(_output_parser_name(self))
            parser_state = parser.new_stream_state()
            async for chunk in self._generate_stream(
                resolved_messages, resolved_options
            ):
                chunk_count += 1
                last_chunk_id = chunk.id or last_chunk_id
                raw_chunk_payload = {
                    "id": chunk.id,
                    "delta": chunk.delta,
                    "reasoning": chunk.reasoning,
                    "tool_call_delta": _tool_calls_debug(
                        [chunk.tool_call_delta] if chunk.tool_call_delta else []
                    ),
                    "finish_reason": chunk.finish_reason,
                }

                await _emit_diagnostic_raw(
                    event="generate_stream.raw_chunk",
                    payload=raw_chunk_payload,
                    options=resolved_options,
                )
                prompt, completion, total, tps = _chunk_usage(chunk)
                if prompt is not None:
                    prompt_tokens = prompt
                if completion is not None:
                    completion_tokens = completion
                if total is not None:
                    total_tokens = total
                if tps is not None:
                    tokens_per_second = tps
                if chunk.delta:
                    for parsed in parser.feed(parser_state, chunk.delta):
                        parsed_payload = {
                            "id": chunk.id,
                            "content": parsed.content,
                            "reasoning": parsed.reasoning,
                            "tool_calls": _tool_calls_debug(parsed.tool_calls),
                            "parser": _output_parser_name(self),
                        }
                        # await _emit_diagnostic_raw(
                        # event="generate_stream.parsed_chunk",
                        # payload=parsed_payload,
                        # options=resolved_options,
                        # )
                        for parsed_chunk in _parsed_stream_chunks(chunk.id, parsed):
                            diagnostic_raw = (
                                {
                                    "parser": _output_parser_name(self),
                                    "raw": raw_chunk_payload,
                                    "parsed": parsed_payload,
                                }
                                if _diagnostic_raw_enabled(resolved_options)
                                else None
                            )
                            yield parsed_chunk.model_copy(
                                update={
                                    "prompt_tokens": chunk.prompt_tokens,
                                    "completion_tokens": chunk.completion_tokens,
                                    "total_tokens": chunk.total_tokens,
                                    "tokens_per_second": chunk.tokens_per_second,
                                    "diagnostic_raw": diagnostic_raw,
                                }
                            )
                has_usage = any(
                    value is not None
                    for value in (
                        chunk.prompt_tokens,
                        chunk.completion_tokens,
                        chunk.total_tokens,
                        chunk.tokens_per_second,
                    )
                )
                if (
                    chunk.reasoning
                    or chunk.tool_call_delta
                    or chunk.finish_reason
                    or (has_usage and not chunk.delta)
                ):
                    if not output_limit_logged:
                        output_limit_logged = _log_max_output_tokens(
                            self,
                            generator="stream:generate_stream",
                            finish_reason=chunk.finish_reason,
                            completion_tokens=completion_tokens,
                            max_tokens=resolved_options.max_tokens,
                        )
                    update = {"delta": None}
                    if _diagnostic_raw_enabled(resolved_options):
                        update["diagnostic_raw"] = {
                            "parser": _output_parser_name(self),
                            "raw": raw_chunk_payload,
                            "parsed": None,
                        }
                    yield chunk.model_copy(update=update)
            for parsed in parser.finish(parser_state):
                parsed_payload = {
                    "id": last_chunk_id,
                    "content": parsed.content,
                    "reasoning": parsed.reasoning,
                    "tool_calls": _tool_calls_debug(parsed.tool_calls),
                    "parser": _output_parser_name(self),
                }
                await _emit_diagnostic_raw(
                    event="generate_stream.parsed_finish",
                    payload=parsed_payload,
                    options=resolved_options,
                )
                for parsed_chunk in _parsed_stream_chunks(last_chunk_id, parsed):
                    diagnostic_raw = (
                        {
                            "parser": _output_parser_name(self),
                            "raw": None,
                            "parsed": parsed_payload,
                        }
                        if _diagnostic_raw_enabled(resolved_options)
                        else None
                    )
                    yield parsed_chunk.model_copy(
                        update={"diagnostic_raw": diagnostic_raw}
                    )
            if tokens_per_second is None and completion_tokens and started_at:
                duration_ms = (time.perf_counter() - started_at) * 1000.0
                tokens_per_second = _tokens_per_second(
                    completion_tokens=completion_tokens,
                    duration_ms=duration_ms,
                )
                if tokens_per_second is not None:
                    yield StreamChunk(
                        id=last_chunk_id,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        tokens_per_second=tokens_per_second,
                    )
            success = True
        except Exception as exc:
            raise
        finally:
            self._record_ai_model_usage(
                request_kind="stream",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                tokens_per_second=tokens_per_second,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
                success=success,
                error=str(error) if error is not None else None,
                metadata={"chunks": chunk_count},
            )

    @abstractmethod
    async def _generate_completion(
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        pass

    @abstractmethod
    async def _generate_stream(
        self, messages: List[Message], options: CompletionOptions
    ) -> AsyncGenerator[StreamChunk, None]:
        pass

    def _record_ai_model_usage(
        self,
        *,
        request_kind: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        duration_ms: float,
        success: bool,
        error: str | None,
        tokens_per_second: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        context = dict(_ai_call_context.get() or {})
        merged_metadata = dict(context.get("metadata") or {})
        if metadata:
            merged_metadata.update(metadata)
        try:
            from democrai.core.application.observability.service import (
                observability_service,
            )

            observability_service.record_ai_model_usage(
                objective=context.get("objective"),
                provider=getattr(self, "_democrai_provider_name", None)
                or self.__class__.__name__,
                engine=getattr(self, "_democrai_engine_name", None)
                or getattr(self, "engine_id", None)
                or self.__class__.__name__,
                model_name=getattr(
                    self,
                    "_democrai_model_name",
                    getattr(self, "model_name", None),
                ),
                deployment_mode=getattr(self, "_democrai_deployment_mode", None),
                request_kind=str(context.get("request_kind") or request_kind),
                agent_id=context.get("agent_id"),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
                tokens_per_second=tokens_per_second,
                success=success,
                error=error,
                metadata=merged_metadata or None,
            )
        except Exception as exc:
            app_ctx().logger.error(
                f"[AI Pipeline] llm telemetry failed in observability:ai_model_usage, ERROR {type(exc).__name__}\n",
                exc_info=False,
            )

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        started_at = time.perf_counter()
        error: Exception | None = None
        try:
            return await self._embed_texts(texts)
        except Exception as exc:
            raise
        finally:
            self._record_ai_model_usage(
                request_kind="embedding",
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
                success=error is None,
                error=str(error) if error is not None else None,
                metadata={"input_count": len(texts)},
            )

    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError(
            f"Provider {self.__class__.__name__} does not support embeddings."
        )

    async def rerank(
        self,
        query: str,
        texts: List[str],
        options: RerankOptions | dict[str, Any] | None = None,
    ) -> List[RerankResult]:
        resolved_options = (
            options
            if isinstance(options, RerankOptions)
            else RerankOptions(**dict(options or {}))
        )
        started_at = time.perf_counter()
        error: Exception | None = None
        try:
            return await self._rerank(query, texts, resolved_options)
        except Exception as exc:
            raise
        finally:
            self._record_ai_model_usage(
                request_kind="rerank",
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
                success=error is None,
                error=str(error) if error is not None else None,
                metadata={"input_count": len(texts)},
            )

    async def _rerank(
        self,
        query: str,
        texts: List[str],
        options: RerankOptions,
    ) -> List[RerankResult]:
        raise NotImplementedError(
            f"Provider {self.__class__.__name__} does not support reranking."
        )

    async def classify(
        self,
        texts: List[str],
        options: ClassificationOptions | dict[str, Any] | None = None,
    ) -> List[ClassificationResult]:
        resolved_options = (
            options
            if isinstance(options, ClassificationOptions)
            else ClassificationOptions(**dict(options or {}))
        )
        started_at = time.perf_counter()
        error: Exception | None = None
        try:
            return await self._classify(texts, resolved_options)
        except Exception as exc:
            raise
        finally:
            self._record_ai_model_usage(
                request_kind="classification",
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
                success=error is None,
                error=str(error) if error is not None else None,
                metadata={"input_count": len(texts)},
            )

    async def _classify(
        self,
        texts: List[str],
        options: ClassificationOptions,
    ) -> List[ClassificationResult]:
        raise NotImplementedError(
            f"Provider {self.__class__.__name__} does not support classification."
        )

    async def extract_tokens(self, text: str) -> List[TokenExtractionResult]:
        started_at = time.perf_counter()
        error: Exception | None = None
        try:
            return await self._extract_tokens(text)
        except Exception as exc:
            raise
        finally:
            self._record_ai_model_usage(
                request_kind="token_extraction",
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                duration_ms=(time.perf_counter() - started_at) * 1000.0,
                success=error is None,
                error=str(error) if error is not None else None,
                metadata={"input_count": 1 if text else 0},
            )

    async def _extract_tokens(self, text: str) -> List[TokenExtractionResult]:
        raise NotImplementedError(
            f"Provider {self.__class__.__name__} does not support token extraction."
        )

    async def download_model(
        self, model_id: str, destination_path: Optional[str] = None
    ) -> str:
        raise NotImplementedError(
            f"Provider {self.__class__.__name__} does not support model downloading."
        )

    def get_info(self) -> dict:
        return {
            "provider": self.__class__.__name__,
            "model": getattr(self, "model_name", None),
            "stream_supported": True,
        }
