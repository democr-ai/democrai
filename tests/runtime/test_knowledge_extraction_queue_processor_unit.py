from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from democrai.core.application.knowledge.extractor import queue_processor as processor_mod
from democrai.core.application.knowledge.ingestion_queue_processor import (
    KnowledgeIngestionQueueProcessor,
)
from democrai.core.application.knowledge.models import KnowledgeIngestItem
from democrai.core.application.knowledge.models import KnowledgeSourceInput
from democrai.core.application.knowledge.records import (
    KnowledgeExtractedItemRecord,
    KnowledgeExtractionRequestRecord,
    KnowledgeChatUploadContextRecord,
    KnowledgeIngestionRequestRecord,
    KnowledgeItemRecord,
    KnowledgeSourceRecord,
)
from democrai.core.application.knowledge.repository import KnowledgeRepository
from democrai.core.infrastructure.database.models import MediaUpload
from democrai.core.infrastructure.database.models import Base
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import RequestContext
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx
from democrai.core.runtime.foundation.app import reset_req_ctx
from democrai.core.runtime.foundation.app import set_req_ctx


class _Media:
    def load(self, path: str) -> bytes:
        assert path == "media/system/doc.pdf"
        return b"%PDF-1.4"


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_queue_processor_extracts_and_persists_items(monkeypatch):
    SessionLocal = _session_factory()
    repo = KnowledgeRepository(SessionLocal)
    with SessionLocal() as session:
        now = utc_now_naive()
        upload = MediaUpload(
            file_id="file-1",
            module_name="system",
            storage_path="media/system/doc.pdf",
            original_filename="doc.pdf",
            stored_filename="file-1_doc.pdf",
            content_type="application/pdf",
            size_bytes=8,
            sha256="abc",
            scope_type="user",
            owner_user_id=10,
            organization_id=None,
            uploaded_by=10,
            uploader_access_level=3,
            created_at=now,
            updated_at=now,
        )
        session.add(upload)
        session.commit()
        media_upload_id = int(upload.id)
    token = set_req_ctx(
        RequestContext(
            request_id="request-1",
            user=10,
            role="admin",
            organization_id=None,
            access_level=3,
            channel="bus",
            app=app_ctx(),
            session_key="session-1",
            action_name="system.upload",
            module_name="system",
            stream_id="stream-1",
        )
    )
    try:
        request = repo.enqueue_extraction_request(
            media_upload_id=media_upload_id,
            user_id=10,
            organization_id=None,
            owner_access_level=3,
            module_name="system",
            storage_path="media/system/doc.pdf",
            original_filename="doc.pdf",
            mime_type="application/pdf",
            source_context={"kind": "media_upload", "file_id": "file-1"},
            metadata={"sha256": "abc"},
            ingest_enabled=True,
        )
    finally:
        reset_req_ctx(token)
    monkeypatch.setattr(
        processor_mod,
        "resolve_active_extractor",
        lambda **_kwargs: {
            "row_id": 7,
            "extractor_id": "docling",
            "config": {"ocr": "rapidocr"},
        },
    )
    captured = {}

    def _extract_runtime(**kwargs):
        current = req_ctx()
        assert current.request_id == "request-1"
        assert current.session_key == "session-1"
        assert current.action_name == "system.upload"
        captured.update(kwargs)
        return {
            "markdown_content": "# Doc\n\nBody",
            "chunks": [{"id": "c1", "text": "Body"}],
            "structure": [{"type": "document"}],
            "index": [],
            "tables": [],
            "formulas": [],
            "images": [],
        }

    processor = processor_mod.KnowledgeExtractionQueueProcessor(
        repository=repo,
        media_provider=_Media(),
        extract_runtime=_extract_runtime,
    )

    stats = processor.process_batch(batch_size=1)

    assert stats.claimed == 1
    assert stats.completed == 1
    assert stats.failed == 0
    assert captured["extractor_row_id"] == 7
    assert captured["extractor_id"] == "docling"
    assert captured["config"] == {"ocr": "rapidocr"}
    assert captured["files"][0]["bytes"] == b"%PDF-1.4"
    with SessionLocal() as session:
        stored_request = session.get(KnowledgeExtractionRequestRecord, request.id)
        assert '"session_key": "session-1"' in stored_request.request_context_json
        assert stored_request.status == "completed"
        items = (
            session.query(KnowledgeExtractedItemRecord)
            .order_by(
                KnowledgeExtractedItemRecord.item_type,
                KnowledgeExtractedItemRecord.ordinal,
            )
            .all()
        )
        assert [(item.item_type, item.content_text) for item in items] == [
            ("chunk", "Body"),
            ("document", "# Doc\n\nBody"),
        ]
        ingestion = session.query(KnowledgeIngestionRequestRecord).one()
        assert ingestion.extraction_request_id == request.id
        assert ingestion.status == "pending"
        assert '"request-1"' in ingestion.request_context_json

    token = set_req_ctx(
        RequestContext(
            request_id="request-chat",
            user=10,
            role="admin",
            organization_id=None,
            access_level=3,
            channel="bus",
            app=app_ctx(),
            session_key="session-1",
            action_name="chat.send",
            module_name="system",
        )
    )
    try:
        repo.link_chat_upload_context(
            file_id="file-1",
            pipeline_id="pipeline-1",
            context={
                "source_type": "chat_attachment",
                "module_name": "system",
                "pipeline_id": "pipeline-1",
            },
        )
    finally:
        reset_req_ctx(token)
    with SessionLocal() as session:
        link = session.query(KnowledgeChatUploadContextRecord).one()
        assert link.file_id == "file-1"
        assert link.user_id == 10
        assert link.organization_id is None
        assert link.pipeline_id == "pipeline-1"
        assert repo._json_load(link.context_json) == {
            "source_type": "chat_attachment",
            "module_name": "system",
            "pipeline_id": "pipeline-1",
        }
    assert [
        (link.file_id, link.pipeline_id)
        for link in repo.list_chat_upload_contexts(
            user_id=10,
            organization_id=None,
            access_level=3,
            file_id="file-1",
            pipeline_id="pipeline-1",
        )
    ] == [("file-1", "pipeline-1")]

    captured_ingest = []

    def _ingest(request):
        current = req_ctx()
        assert current.request_id == "request-1"
        captured_ingest.append(request)

    ingestion_processor = KnowledgeIngestionQueueProcessor(
        service=SimpleNamespace(repository=repo, ingest=_ingest),
        repository=repo,
    )

    ingestion_stats = ingestion_processor.process_batch(batch_size=1)

    assert ingestion_stats.claimed == 1
    assert ingestion_stats.completed == 1
    assert ingestion_stats.failed == 0
    assert captured_ingest[0].user_id == 10
    assert captured_ingest[0].organization_id is None
    assert captured_ingest[0].source.source_id == "media:file-1"
    assert captured_ingest[0].source.source_type == "document"
    assert "message_context" not in captured_ingest[0].source.metadata
    assert [item.content for item in captured_ingest[0].items] == [
        "# Doc\n\nBody",
        "Body",
    ]
    assert captured_ingest[0].items[0].metadata["file_id"] == "file-1"
    assert captured_ingest[0].items[1].metadata["file_id"] == "file-1"
    assert "message_context" not in captured_ingest[0].items[0].metadata
    with SessionLocal() as session:
        ingestion = session.query(KnowledgeIngestionRequestRecord).one()
        assert ingestion.status == "completed"
        statuses = {
            item.ingestion_status
            for item in session.query(KnowledgeExtractedItemRecord).all()
        }
        assert statuses == {"ingested"}


def test_ingestion_queue_processor_reconstructs_direct_payload():
    SessionLocal = _session_factory()
    repo = KnowledgeRepository(SessionLocal)
    captured = []
    token = set_req_ctx(
        RequestContext(
            request_id="request-direct",
            user=22,
            role="user",
            organization_id=44,
            access_level=3,
            channel="bus",
            app=app_ctx(),
            session_key="session-direct",
            action_name="chat.send",
            module_name="chat",
        )
    )
    try:
        row = repo.enqueue_ingestion_request(
            user_id=22,
            organization_id=44,
            origin_type="chat",
            source=KnowledgeSourceInput(
                source_id="chat:session-direct",
                source_type="chat",
                title="Conversation",
                metadata={"pipeline_id": "pipe-1"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="chat:session-direct:1",
                    kind="chat_turn",
                    content="Hello",
                    metadata={"role": "user"},
                ),
            ),
        )
    finally:
        reset_req_ctx(token)

    def _ingest(request):
        current = req_ctx()
        assert current.request_id == "request-direct"
        assert current.session_key == "session-direct"
        captured.append(request)

    processor = KnowledgeIngestionQueueProcessor(
        service=SimpleNamespace(repository=repo, ingest=_ingest),
        repository=repo,
    )

    stats = processor.process_batch(batch_size=1)

    assert stats.claimed == 1
    assert stats.completed == 1
    assert stats.failed == 0
    assert captured[0].user_id == 22
    assert captured[0].organization_id == 44
    assert captured[0].source.source_id == "chat:session-direct"
    assert captured[0].source.metadata["pipeline_id"] == "pipe-1"
    assert captured[0].items[0].content == "Hello"
    with SessionLocal() as session:
        assert session.get(KnowledgeIngestionRequestRecord, row.id).status == "completed"


def test_chat_upload_context_upsert_deduplicates_null_and_real_organization():
    SessionLocal = _session_factory()
    repo = KnowledgeRepository(SessionLocal)
    with SessionLocal() as session:
        now = utc_now_naive()
        session.add_all(
            [
                MediaUpload(
                    file_id="file-no-org",
                    module_name="system",
                    storage_path="media/system/no-org.pdf",
                    original_filename="no-org.pdf",
                    stored_filename="file-no-org_no-org.pdf",
                    content_type="application/pdf",
                    size_bytes=8,
                    sha256="no-org",
                    scope_type="user",
                    owner_user_id=10,
                    organization_id=None,
                    uploaded_by=10,
                    uploader_access_level=3,
                    created_at=now,
                    updated_at=now,
                ),
                MediaUpload(
                    file_id="file-org",
                    module_name="system",
                    storage_path="media/system/org.pdf",
                    original_filename="org.pdf",
                    stored_filename="file-org_org.pdf",
                    content_type="application/pdf",
                    size_bytes=8,
                    sha256="org",
                    scope_type="organization",
                    owner_user_id=20,
                    organization_id=44,
                    uploaded_by=20,
                    uploader_access_level=2,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

    token = set_req_ctx(
        RequestContext(
            request_id="request-chat-no-org",
            user=10,
            role="user",
            organization_id=None,
            access_level=3,
            channel="bus",
            app=app_ctx(),
            session_key="session-no-org",
            action_name="chat.send",
            module_name="system",
        )
    )
    try:
        repo.link_chat_upload_context(
            file_id="file-no-org",
            pipeline_id="pipeline-1",
            context={"version": 1},
        )
        repo.link_chat_upload_context(
            file_id="file-no-org",
            pipeline_id="pipeline-1",
            context={"version": 2},
        )
    finally:
        reset_req_ctx(token)

    token = set_req_ctx(
        RequestContext(
            request_id="request-chat-org",
            user=20,
            role="organization",
            organization_id=44,
            access_level=2,
            channel="bus",
            app=app_ctx(),
            session_key="session-org",
            action_name="chat.send",
            module_name="system",
        )
    )
    try:
        repo.link_chat_upload_context(
            file_id="file-org",
            pipeline_id="pipeline-1",
            context={"version": 1},
        )
        repo.link_chat_upload_context(
            file_id="file-org",
            pipeline_id="pipeline-1",
            context={"version": 2},
        )
    finally:
        reset_req_ctx(token)

    with SessionLocal() as session:
        rows = (
            session.query(KnowledgeChatUploadContextRecord)
            .order_by(KnowledgeChatUploadContextRecord.file_id)
            .all()
        )
        assert len(rows) == 2
        assert [(row.file_id, row.organization_id) for row in rows] == [
            ("file-no-org", None),
            ("file-org", 44),
        ]
        assert [repo._json_load(row.context_json)["version"] for row in rows] == [2, 2]


def test_media_context_link_after_ingestion_completed_stays_separate():
    SessionLocal = _session_factory()
    repo = KnowledgeRepository(SessionLocal)
    with SessionLocal() as session:
        now = utc_now_naive()
        upload = MediaUpload(
            file_id="file-done",
            module_name="system",
            storage_path="media/system/done.pdf",
            original_filename="done.pdf",
            stored_filename="file-done_done.pdf",
            content_type="application/pdf",
            size_bytes=8,
            sha256="done",
            scope_type="user",
            owner_user_id=10,
            organization_id=None,
            uploaded_by=10,
            uploader_access_level=3,
            created_at=now,
            updated_at=now,
        )
        source = KnowledgeSourceRecord(
            id="media:file-done",
            user_id=10,
            organization_id=None,
            source_type="document",
            title="done.pdf",
            media_uri="media/system/done.pdf",
            owner_access_level=3,
            metadata_json=repo._json_dump({"kind": "media_upload"}),
            created_at=now,
            updated_at=now,
        )
        item = KnowledgeItemRecord(
            id="item-done",
            source_id="media:file-done",
            user_id=10,
            organization_id=None,
            kind="document_chunk",
            content="Done",
            embedding_text="Done",
            metadata_json=repo._json_dump({"item_type": "document"}),
            owner_access_level=3,
            content_hash="hash",
            created_at=now,
            updated_at=now,
        )
        session.add_all([upload, source, item])
        session.commit()
        media_upload_id = int(upload.id)

    token = set_req_ctx(
        RequestContext(
            request_id="request-chat-late",
            user=10,
            role="admin",
            organization_id=None,
            access_level=3,
            channel="bus",
            app=app_ctx(),
            session_key="session-1",
            action_name="chat.send",
            module_name="system",
        )
    )
    try:
        row = repo.link_chat_upload_context(
            file_id="file-done",
            pipeline_id="pipeline-late",
            context={
                "source_type": "chat_attachment",
                "module_name": "system",
                "pipeline_id": "pipeline-late",
            },
        )
    finally:
        reset_req_ctx(token)

    assert row is not None
    with SessionLocal() as session:
        link = session.query(KnowledgeChatUploadContextRecord).one()
        source = session.get(KnowledgeSourceRecord, "media:file-done")
        item = session.get(KnowledgeItemRecord, "item-done")
        assert link.file_id == "file-done"
        assert link.user_id == 10
        assert link.organization_id is None
        assert link.pipeline_id == "pipeline-late"
        assert repo._json_load(link.context_json)["pipeline_id"] == "pipeline-late"
        assert source.source_type == "document"
        assert repo._json_load(source.metadata_json) == {"kind": "media_upload"}
        assert repo._json_load(item.metadata_json) == {"item_type": "document"}
    assert [
        (link.file_id, link.pipeline_id)
        for link in repo.list_chat_upload_contexts(
            user_id=10,
            organization_id=None,
            access_level=3,
            file_id="file-done",
            pipeline_id="pipeline-late",
        )
    ] == [("file-done", "pipeline-late")]
