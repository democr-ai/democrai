from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import democrai.core.application.knowledge.repository_helper.extraction_queue as extraction_queue_mod
from democrai.core.application.knowledge.extractor.queue_processor import (
    ExtractionProcessStats,
    ExtractorNotInstalledOnNode,
    KnowledgeExtractionQueueProcessor,
)
from democrai.core.application.knowledge.repository import KnowledgeRepository
from democrai.core.infrastructure.database.models import Base
from democrai.core.platform.utils.timezone import utc_now_naive


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    engine.dispose()


@pytest.fixture
def repo(session_factory):
    return KnowledgeRepository(session_factory)


def _enqueue(repo, *, extractor_id=None, request_id=None, mime_type="application/pdf"):
    return repo.enqueue_extraction_request(
        request_id=request_id,
        user_id=10,
        organization_id=None,
        owner_access_level=3,
        module_name="system",
        storage_path="media/system/doc.pdf",
        original_filename="doc.pdf",
        mime_type=mime_type,
        request_context={},
        extractor_id=extractor_id,
    )


def test_claim_filter_none_keeps_legacy_behavior(repo):
    _enqueue(repo, extractor_id="docling")
    claimed = repo.claim_extraction_requests(
        batch_size=10, owner="w", lease_seconds=60
    )
    assert len(claimed) == 1


def test_claim_filter_excludes_not_installed(repo):
    _enqueue(repo, extractor_id="docling", request_id="row-docling")
    _enqueue(repo, extractor_id="markitdown", request_id="row-markitdown")
    _enqueue(repo, extractor_id=None, request_id="row-null")
    claimed = repo.claim_extraction_requests(
        batch_size=10,
        owner="w",
        lease_seconds=60,
        installed_extractor_ids=["docling"],
    )
    claimed_ids = sorted(item.id for item in claimed)
    # NULL passes (post-claim guard decides), markitdown stays for other nodes
    assert claimed_ids == ["row-docling", "row-null"]


def test_claim_filter_empty_list_only_null_rows(repo):
    _enqueue(repo, extractor_id="docling", request_id="row-docling")
    _enqueue(repo, extractor_id=None, request_id="row-null")
    claimed = repo.claim_extraction_requests(
        batch_size=10, owner="w", lease_seconds=60, installed_extractor_ids=[]
    )
    assert [item.id for item in claimed] == ["row-null"]


def test_release_extraction_request_no_attempt_consumed(repo, session_factory):
    row = _enqueue(repo, extractor_id="docling", request_id="row-r")
    claimed = repo.claim_extraction_requests(
        batch_size=1, owner="w", lease_seconds=60
    )
    assert claimed[0].id == "row-r"
    repo.release_extraction_request(
        "row-r", defer_seconds=5, reason="not installed here"
    )
    with session_factory() as session:
        record = session.get(repo.KnowledgeExtractionRequestRecord, "row-r")
        assert record.status == "pending"
        assert record.attempts == 0
        assert record.lease_owner is None
        assert record.available_at > utc_now_naive()
        assert "not installed" in record.last_error


def test_enqueue_resolves_extractor_id_with_node_coordination(repo, monkeypatch):
    monkeypatch.setattr(
        extraction_queue_mod, "_node_coordination_enabled", lambda: True
    )
    monkeypatch.setattr(
        extraction_queue_mod,
        "_resolve_extractor_id_for_mime",
        lambda mime_type: "docling" if mime_type == "application/pdf" else None,
    )
    row = _enqueue(repo, extractor_id=None, request_id="row-resolved")
    assert row.extractor_id == "docling"
    row = _enqueue(
        repo, extractor_id=None, request_id="row-unknown", mime_type="x/unknown"
    )
    assert row.extractor_id is None


def test_enqueue_does_not_resolve_without_node_coordination(repo, monkeypatch):
    monkeypatch.setattr(
        extraction_queue_mod, "_node_coordination_enabled", lambda: False
    )
    called = []
    monkeypatch.setattr(
        extraction_queue_mod,
        "_resolve_extractor_id_for_mime",
        lambda mime_type: called.append(mime_type),
    )
    row = _enqueue(repo, extractor_id=None, request_id="row-plain")
    assert row.extractor_id is None
    assert called == []


class _GuardRepo:
    """Repository double recording release/fail calls for the guard test."""

    def __init__(self, requests):
        self._requests = requests
        self.released = []
        self.failed = []

    def claim_extraction_requests(self, **kwargs):
        items, self._requests = self._requests, []
        return items

    def release_extraction_request(self, request_id, **kwargs):
        self.released.append((request_id, kwargs))

    def fail_extraction_request(self, request_id, **kwargs):
        self.failed.append((request_id, kwargs))


def _request(request_id="req-1"):
    return SimpleNamespace(
        id=request_id,
        original_filename="doc.pdf",
        mime_type="application/pdf",
        extractor_id=None,
        extractor_config={},
        request_context={},
        metadata={},
        source_context={},
        storage_path="media/system/doc.pdf",
        user_id=10,
        organization_id=None,
        ingest_enabled=False,
        attempts=0,
    )


@pytest.fixture
def guard_processor(monkeypatch):
    import democrai.core.application.knowledge.extractor.queue_processor as processor_mod

    monkeypatch.setattr(
        processor_mod,
        "resolve_active_extractor",
        lambda **kwargs: {
            "row_id": 1,
            "extractor_id": "docling",
            "config": {},
            "install_config": {},
        },
    )

    def _factory(*, installed, installed_elsewhere):
        repo = _GuardRepo([_request()])
        processor = KnowledgeExtractionQueueProcessor(
            repository=repo,
            media_provider=SimpleNamespace(load=lambda path: b"%PDF"),
            node_id="node-a",
            node_filter_enabled=True,
        )
        processor._refresh_installed_extractor_ids = lambda: None
        processor._installed_extractor_ids = installed
        processor._extractor_installed_on_active_node = (
            lambda extractor_id: installed_elsewhere
        )
        return processor, repo

    return _factory


def test_guard_releases_when_installed_elsewhere(guard_processor):
    processor, repo = guard_processor(installed=[], installed_elsewhere=True)
    stats = processor.process_batch(batch_size=1)
    assert stats == ExtractionProcessStats(
        claimed=1, completed=0, failed=0, released=1
    )
    assert len(repo.released) == 1
    assert repo.failed == []


def test_guard_fails_when_installed_nowhere(guard_processor):
    processor, repo = guard_processor(installed=[], installed_elsewhere=False)
    stats = processor.process_batch(batch_size=1)
    assert stats.failed == 1
    assert stats.released == 0
    assert len(repo.failed) == 1
    assert "not_installed_on_node" in repo.failed[0][1]["error"]


def test_guard_not_triggered_when_installed_here(guard_processor, monkeypatch):
    processor, repo = guard_processor(
        installed=["docling"], installed_elsewhere=False
    )
    completed = []
    monkeypatch.setattr(
        KnowledgeExtractionQueueProcessor,
        "_process_request",
        lambda self, request: completed.append(request.id),
    )
    stats = processor.process_batch(batch_size=1)
    assert stats.completed == 1
    assert completed == ["req-1"]
