"""Rerank providers used by knowledge retrieval."""

from __future__ import annotations

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol, Sequence

from democrai.core.application.ai.engine.schemas.completion import RerankOptions


class RerankProvider(Protocol):
    """Protocol implemented by knowledge rerank providers."""

    model_id: str
    model_version: str

    def rerank(self, *, query: str, texts: Sequence[str]) -> list[object]: ...


_RERANK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="knowledge-rerank")


def _run_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    ctx = contextvars.copy_context()
    return _RERANK_EXECUTOR.submit(
        lambda queued_coro: ctx.run(asyncio.run, queued_coro),
        coro,
    ).result()


class ModelRegistryRerankProvider:
    """Rerank provider bound to one explicit model_registry row."""

    def __init__(
        self,
        *,
        model_registry_id: int,
        model_id: str,
        model_version: str = "1",
        runtime_options: dict[str, Any] | None = None,
    ) -> None:
        if model_registry_id <= 0:
            raise ValueError("model_registry_id must be greater than zero")
        self.model_registry_id = model_registry_id
        self.model_id = model_id
        self.model_version = model_version
        self.options = RerankOptions(
            **(runtime_options if runtime_options is not None else {})
        )

    def rerank(self, *, query: str, texts: Sequence[str]) -> list[object]:
        """Synchronously rerank texts through the configured model."""
        if not texts:
            return []
        return _run_sync(
            self._rerank_async(
                query=query,
                texts=list(texts),
            )
        )

    async def _rerank_async(self, *, query: str, texts: list[str]) -> list[object]:
        from democrai.core.application.ai.orchestrator import model_orchestrator

        result = await model_orchestrator.get_provider_by_model_registry_id(
            self.model_registry_id,
        )
        if result.get("status") != "ok" or "provider" not in result:
            raise RuntimeError(
                "Failed to resolve rerank provider for "
                f"model_registry_id={self.model_registry_id}: {result}"
            )
        return list(
            await result["provider"].rerank(
                query=query,
                texts=texts,
                options=self.options,
            )
            or []
        )
