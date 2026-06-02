"""Embedding provider abstractions used by the knowledge subsystem.

The runtime knowledge configuration binds embedding to a specific
``model_registry`` row. The provider below resolves that configured model
through the AI orchestrator by id; objective-based selection is intentionally not
part of the knowledge runtime path.
"""

from __future__ import annotations

import hashlib
import math
import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    """Protocol implemented by synchronous embedding providers.

    Providers expose model metadata and a single :meth:`embed_texts` method.
    The surrounding knowledge pipeline treats all implementations uniformly.
    """

    dim: int
    model_id: str
    model_version: str

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """
    Deterministic embedding provider useful for local smoke runs and tests.
    Production deployments should inject a real embedding provider.
    """

    def __init__(
        self,
        *,
        dim: int = 32,
        model_id: str = "hash-embedding",
        model_version: str = "1",
    ) -> None:
        if dim <= 0:
            raise ValueError("dim must be greater than zero")
        self.dim = dim
        self.model_id = model_id
        self.model_version = model_version

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts deterministically without any external dependency."""
        return [self._embed_single(text) for text in texts]

    def _embed_single(self, text: str) -> list[float]:
        buckets = [0.0] * self.dim
        normalized = " ".join(text.lower().split())
        if not normalized:
            return buckets
        for token in normalized.split(" "):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(self.dim):
                buckets[index] += (digest[index % len(digest)] / 255.0) - 0.5
        norm = math.sqrt(sum(value * value for value in buckets))
        if norm == 0.0:
            return buckets
        return [value / norm for value in buckets]


_EMBEDDING_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="knowledge-embed")


def _run_sync(coro):
    """Execute an async embedding resolution flow from sync code.

    The knowledge pipeline performs embeddings from projection workers and from
    synchronous call sites. When an event loop is already running the coroutine
    is offloaded to a small thread pool so the caller can keep a synchronous
    API.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    ctx = contextvars.copy_context()
    return _EMBEDDING_EXECUTOR.submit(
        lambda queued_coro: ctx.run(asyncio.run, queued_coro),
        coro,
    ).result()


class ModelRegistryEmbeddingProvider:
    """Embedding provider bound to one explicit model_registry row."""

    def __init__(
        self,
        *,
        model_registry_id: int,
        dim: int,
        model_id: str,
        model_version: str = "1",
    ) -> None:
        if model_registry_id <= 0:
            raise ValueError("model_registry_id must be greater than zero")
        if dim <= 0:
            raise ValueError("dim must be greater than zero")
        self.model_registry_id = model_registry_id
        self.dim = dim
        self.model_id = model_id
        self.model_version = model_version

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Synchronously embed texts through the configured model."""
        if not texts:
            return []
        return _run_sync(self._embed_texts_async(list(texts)))

    async def _embed_texts_async(self, texts: list[str]) -> list[list[float]]:
        from democrai.core.application.ai.orchestrator import model_orchestrator

        result = await model_orchestrator.get_provider_by_model_registry_id(
            self.model_registry_id,
        )
        if result.get("status") != "ok" or "provider" not in result:
            raise RuntimeError(
                "Failed to resolve embedding provider for "
                f"model_registry_id={self.model_registry_id}: {result}"
            )
        vectors = await result["provider"].embed_texts(texts)
        for vector in vectors or []:
            if len(vector) != self.dim:
                raise ValueError(
                    f"Embedding dimension mismatch for {self.model_id}: "
                    f"expected {self.dim}, got {len(vector)}"
                )
        return vectors
