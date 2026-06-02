"""DB queue processor for background knowledge extraction."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any, Callable

from democrai.core.application.knowledge.extractor.resolver import (
    resolve_active_extractor,
)
from democrai.core.application.knowledge.extractor.runtime import extract_with_runtime
from democrai.core.application.knowledge.repository import KnowledgeRepository
from democrai.core.application.knowledge.task_progress import (
    complete_extraction_task,
    extraction_task_id_from_metadata,
    fail_extraction_task,
    update_extraction_task,
)
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import request_context_scope


@dataclass(frozen=True)
class ExtractionProcessStats:
    claimed: int = 0
    completed: int = 0
    failed: int = 0


class KnowledgeExtractionQueueProcessor:
    """Process durable extraction requests from the database queue."""

    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        media_provider: Any,
        owner: str | None = None,
        extract_runtime: Callable[..., dict[str, Any]] = extract_with_runtime,
        max_attempts: int = 3,
        lease_seconds: int = 600,
    ) -> None:
        self._repository = repository
        self._media_provider = media_provider
        self._owner = str(owner or f"extractor:{socket.gethostname()}").strip()
        self._extract_runtime = extract_runtime
        self._max_attempts = max_attempts
        self._lease_seconds = lease_seconds

    def process_one(self) -> bool:
        stats = self.process_batch(batch_size=1)
        return stats.completed > 0 or stats.failed > 0

    def process_batch(self, *, batch_size: int = 1) -> ExtractionProcessStats:
        requests = self._repository.claim_extraction_requests(
            batch_size=max(1, batch_size),
            owner=self._owner,
            lease_seconds=self._lease_seconds,
        )
        completed = 0
        failed = 0
        for request in requests:
            with request_context_scope(dict(request.request_context or {})):
                task_id = extraction_task_id_from_metadata(request.metadata)
                update_extraction_task(
                    task_id,
                    progress=0.2,
                    label=f"Extracting: {request.original_filename}",
                    checkpoint={"extraction_request_id": request.id},
                )
                try:
                    self._process_request(request)
                    if request.ingest_enabled:
                        update_extraction_task(
                            task_id,
                            progress=0.55,
                            label=(
                                "Extraction completed, ingestion queued: "
                                f"{request.original_filename}"
                            ),
                            checkpoint={"extraction_request_id": request.id},
                        )
                    else:
                        complete_extraction_task(
                            task_id,
                            result={"extraction_request_id": request.id},
                        )
                    completed += 1
                except Exception as exc:
                    self._repository.fail_extraction_request(
                        request.id,
                        error=str(exc),
                        max_attempts=self._max_attempts,
                    )
                    if request.attempts + 1 >= self._max_attempts:
                        fail_extraction_task(task_id, error=str(exc))
                    else:
                        update_extraction_task(
                            task_id,
                            progress=0.2,
                            label=(
                                "Extraction retry scheduled: "
                                f"{request.original_filename}"
                            ),
                            checkpoint={"extraction_request_id": request.id},
                        )
                    failed += 1
        return ExtractionProcessStats(
            claimed=len(requests),
            completed=completed,
            failed=failed,
        )

    def _process_request(self, request) -> None:
        resolved = resolve_active_extractor(
            filename=request.original_filename,
            mime_type=request.mime_type,
        )
        if resolved is None:
            raise RuntimeError("knowledge_extraction_no_active_extractor")
        if request.extractor_id and request.extractor_id != resolved["extractor_id"]:
            raise RuntimeError("knowledge_extraction_configured_extractor_unavailable")
        config = dict(resolved.get("install_config") or {})
        config.update(dict(resolved.get("config") or {}))
        config.update(dict(request.extractor_config or {}))
        data = bytes(self._media_provider.load(request.storage_path))
        payload = self._extract_runtime(
            extractor_row_id=resolved["row_id"],
            extractor_id=resolved["extractor_id"],
            config=config,
            files=[
                {
                    "bytes": data,
                    "name": request.original_filename,
                    "source": request.storage_path,
                    "mime_type": request.mime_type,
                    "metadata": request.source_context,
                }
            ],
        )
        payload["resolved_extractor"] = resolved
        self._repository.complete_extraction_with_items(
            request_id=request.id,
            user_id=request.user_id,
            organization_id=request.organization_id,
            items=_extracted_items_from_payload(
                payload,
                title=request.original_filename,
                metadata={
                    **dict(request.metadata or {}),
                    "storage_path": request.storage_path,
                    "mime_type": request.mime_type,
                },
            ),
            enqueue_ingestion=request.ingest_enabled,
            priority=0,
        )


def _extracted_items_from_payload(
    payload: dict[str, Any],
    *,
    title: str,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    items = [
        {
            "item_type": "document",
            "ordinal": 0,
            "title": title,
            "content_text": str(payload.get("markdown_content") or "").strip(),
            "content": payload,
            "metadata": metadata,
        }
    ]
    for index, chunk in enumerate(list(payload.get("chunks") or [])):
        text = str(dict(chunk).get("text") or "").strip()
        items.append(
            {
                "item_type": "chunk",
                "ordinal": index,
                "title": title,
                "content_text": text,
                "content": chunk,
                "metadata": metadata,
            }
        )
    for item_type in ("table", "formula", "image"):
        payload_key = f"{item_type}s"
        for index, item in enumerate(list(payload.get(payload_key) or [])):
            items.append(
                {
                    "item_type": item_type,
                    "ordinal": index,
                    "title": title,
                    "content_text": "",
                    "content": item,
                    "metadata": metadata,
                }
            )
    return items


def build_default_extraction_queue_processor() -> KnowledgeExtractionQueueProcessor:
    ctx = app_ctx()
    repository = getattr(getattr(ctx, "knowledge_service", None), "repository", None)
    if repository is None:
        db = getattr(ctx, "db", None)
        if db is None:
            raise RuntimeError("knowledge_repository_unavailable")
        repository = KnowledgeRepository(db.get_session)
    media_provider = getattr(ctx, "media", None)
    if media_provider is None:
        raise RuntimeError("media_provider_unavailable")
    return KnowledgeExtractionQueueProcessor(
        repository=repository,
        media_provider=media_provider,
    )
