"""DB queue processor for canonical knowledge ingestion."""

from __future__ import annotations

import socket
from dataclasses import dataclass

from democrai.core.application.knowledge.repository import KnowledgeRepository
from democrai.core.application.knowledge.service import KnowledgeService
from democrai.core.application.knowledge.task_progress import (
    complete_extraction_task,
    extraction_task_id,
    fail_extraction_task,
    update_extraction_task,
)
from democrai.core.runtime.foundation.app import request_context_scope


@dataclass(frozen=True)
class IngestionProcessStats:
    claimed: int = 0
    completed: int = 0
    failed: int = 0


class KnowledgeIngestionQueueProcessor:
    """Process durable ingestion requests from the database queue."""

    def __init__(
        self,
        *,
        service: KnowledgeService,
        repository: KnowledgeRepository | None = None,
        owner: str | None = None,
        max_attempts: int = 3,
        lease_seconds: int = 600,
    ) -> None:
        self._service = service
        self._repository = repository or service.repository
        self._owner = owner if owner is not None else f"ingestion:{socket.gethostname()}"
        self._max_attempts = max_attempts
        self._lease_seconds = lease_seconds

    def process_one(self) -> bool:
        stats = self.process_batch(batch_size=1)
        return stats.completed > 0 or stats.failed > 0

    def process_batch(self, *, batch_size: int = 1) -> IngestionProcessStats:
        requests = self._repository.claim_ingestion_requests(
            batch_size=max(1, batch_size),
            owner=self._owner,
            lease_seconds=self._lease_seconds,
        )
        completed = 0
        failed = 0
        for request in requests:
            with request_context_scope(dict(request.request_context or {})):
                task_id = (
                    extraction_task_id(self._repository, request.extraction_request_id)
                    if request.extraction_request_id
                    else ""
                )
                update_extraction_task(
                    task_id,
                    progress=0.7,
                    label="Ingesting extracted content",
                    checkpoint={
                        "extraction_request_id": request.extraction_request_id,
                        "ingestion_request_id": request.id,
                    },
                )
                try:
                    ingest_request = self._repository.build_ingestion_request_payload(
                        request=request
                    )
                    self._service.ingest(ingest_request)
                    self._repository.complete_ingestion_request(request.id)
                    complete_extraction_task(
                        task_id,
                        result={
                            "extraction_request_id": request.extraction_request_id,
                            "ingestion_request_id": request.id,
                        },
                    )
                    completed += 1
                except Exception as exc:
                    self._repository.fail_ingestion_request(
                        request.id,
                        error=str(exc),
                        max_attempts=self._max_attempts,
                    )
                    if request.attempts + 1 >= self._max_attempts:
                        fail_extraction_task(task_id, error=str(exc))
                    else:
                        update_extraction_task(
                            task_id,
                            progress=0.7,
                            label="Ingestion retry scheduled",
                            checkpoint={
                                "extraction_request_id": request.extraction_request_id,
                                "ingestion_request_id": request.id,
                            },
                        )
                    failed += 1
        return IngestionProcessStats(
            claimed=len(requests),
            completed=completed,
            failed=failed,
        )
