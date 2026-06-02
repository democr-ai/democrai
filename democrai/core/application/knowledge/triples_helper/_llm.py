"""LLM-backed triple extractors used by the knowledge subsystem.

Knowledge graph extraction is bound to the specific model selected in the
database-backed knowledge runtime configuration.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from democrai.core.application.ai.constants import AIRuntimeMethod, methods_for_capabilities
from democrai.core.application.ai.engine.schemas.completion import CompletionOptions
from democrai.core.application.ai.engine.schemas.runtime import EngineMethodResponse
from democrai.core.application.ai.engine.schemas.kg import KGExtractionOptions
from democrai.core.application.ai.engine.manifests import get_engine_manifest
from democrai.core.application.ai.engine.manifests import get_provider_definition
from democrai.core.application.ai.security.prompt.builder import PromptContextBuilder
from democrai.core.application.ai.security.prompt.messages import (
    normalize_prompt_messages_with_audit,
)

from ._base import (
    GRAPH_SYSTEM_PROMPT,
    ExtractedKnowledgeGraph,
    TripleExtractor,
    build_llm_prompt,
    clamp_limit,
    normalize_graph_payload,
)

_TRIPLE_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="knowledge-graph",
)

_KG_EXTRACTION_METHODS = (
    AIRuntimeMethod.EXTRACT_TRIPLES,
    AIRuntimeMethod.GENERATE_COMPLETION,
)


def _run_sync(coro):
    """Execute an async graph-extraction coroutine from sync call sites."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    ctx = contextvars.copy_context()
    return _TRIPLE_EXECUTOR.submit(
        lambda queued_coro: ctx.run(asyncio.run, queued_coro),
        coro,
    ).result()


def _runtime_methods_for_model(model: Any) -> tuple[str, ...]:
    model_methods = set(methods_for_capabilities(getattr(model, "capabilities", None)))
    engine = getattr(model, "engine", None)
    provider_id = engine.provider.lower()
    provider_definition = get_provider_definition(provider_id) or {}
    provider_methods = provider_definition.get("runtime_methods")
    if not isinstance(provider_methods, list) or not provider_methods:
        engine_manifest = get_engine_manifest(provider_id) or {}
        manifest_provider = engine_manifest.get("provider")
        if isinstance(manifest_provider, dict):
            provider_methods = manifest_provider.get("runtime_methods")
    if not isinstance(provider_methods, list) or not provider_methods:
        raise RuntimeError(
            "knowledge_triple_extractor_runtime_methods_missing:"
            f"model_registry_id={getattr(model, 'id', '-')}"
        )
    supported = [method for method in provider_methods if method in model_methods]
    return tuple(method for method in _KG_EXTRACTION_METHODS if method in supported)


def _graph_response_payload(response: Any) -> dict[str, object]:
    if isinstance(response, EngineMethodResponse):
        return _graph_response_payload(response.result)
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    elif isinstance(response, dict):
        payload = response
    else:
        payload = {
            "entities": getattr(response, "entities", ()),
            "relations": getattr(response, "relations", ()),
        }
    return payload if isinstance(payload, dict) else {}


def _completion_response_content(response: Any) -> str | None:
    if isinstance(response, EngineMethodResponse):
        return _completion_response_content(response.result)
    if isinstance(response, dict):
        content = response.get("content")
    else:
        content = getattr(response, "content", None)
    return content if isinstance(content, str) else None


class ModelRegistryTripleExtractor(TripleExtractor):
    """Triple extractor bound to one explicit model_registry row."""

    def __init__(
        self,
        *,
        model_registry_id: int,
        model_id: str | None = None,
        model_version: str = "1",
        max_entities: int = 24,
        max_relations: int = 48,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> None:
        if model_registry_id <= 0:
            raise ValueError("model_registry_id must be greater than zero")
        self.model_registry_id = model_registry_id
        self.model_id = model_id
        self.model_version = model_version
        self.max_entities = clamp_limit(max_entities, fallback=24)
        self.max_relations = clamp_limit(max_relations, fallback=48)
        self.temperature = temperature
        self.max_tokens = max(64, max_tokens)

    def extract_item(
        self, *, kind: str, title: str | None, summary: str | None, content: str
    ) -> ExtractedKnowledgeGraph:
        """Synchronously extract a graph through the resolved LLM provider."""
        if not content.strip():
            return ExtractedKnowledgeGraph(entities=(), relations=())
        return _run_sync(
            self._extract_item_async(
                kind=kind,
                title=title,
                summary=summary,
                content=content,
            )
        )

    async def _extract_item_async(
        self, *, kind: str, title: str | None, summary: str | None, content: str
    ) -> ExtractedKnowledgeGraph:
        model = self._resolve_model()
        runtime_methods = _runtime_methods_for_model(model)
        if AIRuntimeMethod.EXTRACT_TRIPLES in runtime_methods:
            return await self._extract_item_with_kg_provider(
                kind=kind,
                title=title,
                summary=summary,
                content=content,
            )
        if AIRuntimeMethod.GENERATE_COMPLETION in runtime_methods:
            return await self._extract_item_with_llm_provider(
                kind=kind,
                title=title,
                summary=summary,
                content=content,
            )
        raise RuntimeError(
            "knowledge_triple_extractor_unsupported_runtime_method:"
            f"model_registry_id={self.model_registry_id}"
        )

    async def _extract_item_with_kg_provider(
        self, *, kind: str, title: str | None, summary: str | None, content: str
    ) -> ExtractedKnowledgeGraph:
        result = await self._resolve_provider()
        if result.get("status") != "ok" or "provider" not in result:
            raise RuntimeError(
                "Failed to resolve graph extraction provider for "
                f"model_registry_id={self.model_registry_id}: {result}"
            )

        provider = result["provider"]
        response = await provider.extract_triples(
            kind=kind,
            title=title,
            summary=summary,
            content=content,
            options=KGExtractionOptions(
                max_entities=self.max_entities,
                max_relations=self.max_relations,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            ),
        )
        return normalize_graph_payload(
            _graph_response_payload(response),
            max_entities=self.max_entities,
            max_relations=self.max_relations,
        )

    async def _extract_item_with_llm_provider(
        self, *, kind: str, title: str | None, summary: str | None, content: str
    ) -> ExtractedKnowledgeGraph:
        result = await self._resolve_provider()
        if result.get("status") != "ok" or "provider" not in result:
            raise RuntimeError(
                "Failed to resolve graph extraction provider for "
                f"model_registry_id={self.model_registry_id}: {result}"
            )

        provider = result["provider"]
        prompt_builder = PromptContextBuilder()
        messages = await normalize_prompt_messages_with_audit(
            [
                prompt_builder.trusted_instruction(
                    GRAPH_SYSTEM_PROMPT,
                    origin="knowledge_graph_extraction",
                ),
                prompt_builder.document_text(
                    build_llm_prompt(
                        kind=kind,
                        title=title,
                        summary=summary,
                        content=content,
                    ),
                    origin="knowledge_graph_extraction",
                    metadata={"kind": kind},
                ),
            ],
            stage="knowledge_graph_extraction",
        )
        response = await provider.generate_completion(
            messages=messages,
            options=CompletionOptions(
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            ),
        )
        message = _completion_response_content(response)
        if not message:
            return ExtractedKnowledgeGraph(entities=(), relations=())
        return normalize_graph_payload(
            json.loads(message),
            max_entities=self.max_entities,
            max_relations=self.max_relations,
        )

    async def _resolve_provider(self):
        from democrai.core.application.ai.orchestrator import model_orchestrator

        return await model_orchestrator.get_provider_by_model_registry_id(
            self.model_registry_id,
        )

    def _resolve_model(self):
        from democrai.core.application.ai.orchestrator import model_orchestrator

        model = model_orchestrator.get_model_by_registry_id(self.model_registry_id)
        if model is None:
            raise RuntimeError(
                f"model_registry_row_not_found:{self.model_registry_id}"
            )
        return model
