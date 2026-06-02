from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import democrai.sdk.knowledge as knowledge_mod
from democrai.core.runtime.foundation.app import RequestContext
from democrai.core.runtime.foundation.app import reset_req_ctx
from democrai.core.runtime.foundation.app import set_req_ctx


def test_knowledge_sdk_uses_request_context_for_ingestion_scope(monkeypatch):
    sdk = SimpleNamespace(
        module_name="mod",
        session={"user": {"id": 999, "organization_id": 999, "access_level": 1}},
    )
    captured = []
    ingestion = SimpleNamespace(
        ingest_document=lambda **kwargs: captured.append(("doc", kwargs))
        or {"doc": kwargs["path"]},
        ingest_document_bytes=lambda **kwargs: captured.append(("bytes", kwargs))
        or {"bytes": kwargs["filename"]},
    )
    monkeypatch.setattr(
        knowledge_mod,
        "app_ctx",
        lambda: SimpleNamespace(knowledge_ingestion=ingestion),
    )
    token = set_req_ctx(
        RequestContext(
            request_id="req-knowledge-sdk",
            user=7,
            role="user",
            organization_id=11,
            access_level=3,
            channel="test",
        )
    )
    try:
        knowledge = knowledge_mod.Knowledge(sdk)
        assert knowledge.ingest_document(path="a.pdf")["doc"] == "a.pdf"
        assert (
            knowledge.ingest_document_bytes(filename="a.txt", data=b"x")["bytes"]
            == "a.txt"
        )
    finally:
        reset_req_ctx(token)

    assert captured[0][1]["user_id"] == 7
    assert captured[0][1]["organization_id"] == 11
    assert captured[1][1]["user_id"] == 7
    assert captured[1][1]["organization_id"] == 11


def test_knowledge_sdk_requires_request_context_for_ingestion(monkeypatch):
    sdk = SimpleNamespace(module_name="mod", session={"user": {"id": 1}})
    monkeypatch.setattr(
        knowledge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            knowledge_ingestion=SimpleNamespace(
                ingest_document=lambda **_kwargs: None,
            )
        ),
    )

    with pytest.raises(RuntimeError, match="knowledge_ingestion_missing_request_context"):
        knowledge_mod.Knowledge(sdk).ingest_document(path="a.pdf")


def test_knowledge_sdk_uses_request_context_for_retrieval_scope(monkeypatch):
    sdk = SimpleNamespace(
        module_name="mod",
        session={"user": {"id": 999, "organization_id": 999, "access_level": 1}},
    )
    captured = []

    class KnowledgeService:
        async def retrieve(self, request):
            captured.append(request)
            return SimpleNamespace(matches=())

    monkeypatch.setattr(
        knowledge_mod,
        "app_ctx",
        lambda: SimpleNamespace(knowledge_service=KnowledgeService()),
    )
    monkeypatch.setenv("DEMOCRAI_KNOWLEDGE_QUERY_SERVICE", "1")
    token = set_req_ctx(
        RequestContext(
            request_id="req-knowledge-retrieval",
            user=7,
            role="user",
            organization_id=11,
            access_level=3,
            channel="test",
        )
    )
    try:
        result = asyncio.run(
            knowledge_mod.Knowledge(sdk).retrieve(
                query_text="  budget  ",
                top_k=3,
                lexical_limit=4,
                graph_neighbors_limit=2,
                metadata_filters={"module_name": "docs"},
            )
        )
    finally:
        reset_req_ctx(token)

    assert result.matches == ()
    assert captured[0].user_id == 7
    assert captured[0].organization_id == 11
    assert captured[0].access_level == 3
    assert captured[0].query_text == "budget"
    assert captured[0].top_k == 3
    assert captured[0].lexical_limit == 4
    assert captured[0].graph_neighbors_limit == 2
    assert dict(captured[0].metadata_filters) == {"module_name": "docs"}


def test_knowledge_sdk_requires_request_context_for_retrieval(monkeypatch):
    sdk = SimpleNamespace(module_name="mod", session={"user": {"id": 1}})
    monkeypatch.setattr(
        knowledge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            knowledge_service=SimpleNamespace(retrieve=lambda _request: None),
        ),
    )

    with pytest.raises(RuntimeError, match="knowledge_retrieval_missing_request_context"):
        asyncio.run(knowledge_mod.Knowledge(sdk).retrieve(query_text="budget"))


def test_knowledge_sdk_injects_module_scope_for_metadata_delete(monkeypatch):
    sdk = SimpleNamespace(module_name="chat", session={"user": {"id": 999}})
    captured = []

    class KnowledgeService:
        def delete_by_metadata(self, **kwargs):
            captured.append(kwargs)
            return {"deleted_items": ()}

    monkeypatch.setattr(
        knowledge_mod,
        "app_ctx",
        lambda: SimpleNamespace(knowledge_service=KnowledgeService()),
    )
    token = set_req_ctx(
        RequestContext(
            request_id="req-knowledge-delete",
            user=7,
            role="user",
            organization_id=11,
            access_level=3,
            channel="test",
        )
    )
    try:
        result = knowledge_mod.Knowledge(sdk).delete_by_metadata(
            {"conversation_id": 42}
        )
    finally:
        reset_req_ctx(token)

    assert result == {"deleted_items": ()}
    assert captured == [
        {
            "user_id": 7,
            "organization_id": 11,
            "metadata_filters": {"module_name": "chat", "conversation_id": 42},
            "force": False,
        }
    ]


def test_knowledge_sdk_passes_force_for_metadata_delete(monkeypatch):
    sdk = SimpleNamespace(module_name="chat", session={"user": {"id": 999}})
    captured = []

    class KnowledgeService:
        def delete_by_metadata(self, **kwargs):
            captured.append(kwargs)
            return {"deleted_items": ()}

    monkeypatch.setattr(
        knowledge_mod,
        "app_ctx",
        lambda: SimpleNamespace(knowledge_service=KnowledgeService()),
    )
    token = set_req_ctx(
        RequestContext(
            request_id="req-knowledge-delete-force",
            user=7,
            role="user",
            organization_id=11,
            access_level=3,
            channel="test",
        )
    )
    try:
        knowledge_mod.Knowledge(sdk).delete_by_metadata(
            {"conversation_id": 42},
            force=True,
        )
    finally:
        reset_req_ctx(token)

    assert captured == [
        {
            "user_id": 7,
            "organization_id": 11,
            "metadata_filters": {"module_name": "chat", "conversation_id": 42},
            "force": True,
        }
    ]


def test_knowledge_sdk_rejects_manual_module_scope_for_metadata_delete():
    sdk = SimpleNamespace(module_name="chat", session={"user": {"id": 1}})

    with pytest.raises(ValueError, match="module_name is injected"):
        knowledge_mod.Knowledge(sdk).delete_by_metadata({"module_name": "chat"})


def test_knowledge_sdk_uses_request_context_for_extraction_scope(monkeypatch):
    sdk = SimpleNamespace(
        module_name="mod",
        session={"user": {"id": 999, "organization_id": 999, "access_level": 1}},
    )
    captured = []
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.services.media_uploads",
        SimpleNamespace(
            can_access_media_upload=lambda **_kwargs: True,
            enqueue_media_extraction=lambda **kwargs: captured.append(kwargs)
            or "extraction-1"
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.database.media_uploads",
        SimpleNamespace(
            get_media_upload_by_storage_path=lambda storage_path: SimpleNamespace(
                id=4,
                file_id="file-1",
                original_filename="doc.pdf",
                content_type="application/pdf",
                owner_user_id=8,
                organization_id=12,
            )
        ),
    )

    token = set_req_ctx(
        RequestContext(
            request_id="req-knowledge-extraction",
            user=8,
            role="organization",
            organization_id=12,
            access_level=2,
            channel="test",
        )
    )
    try:
        result = knowledge_mod.Knowledge(sdk).enqueue_extraction(
            storage_path="media/doc.pdf"
        )
    finally:
        reset_req_ctx(token)

    assert result == "extraction-1"
    assert captured[0]["user_id"] == 8
    assert captured[0]["organization_id"] == 12
    assert captured[0]["owner_access_level"] == 2
    assert captured[0]["media_upload_id"] == 4


def test_knowledge_sdk_rejects_inaccessible_extraction_media(monkeypatch):
    sdk = SimpleNamespace(module_name="mod", session={})
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.services.media_uploads",
        SimpleNamespace(
            can_access_media_upload=lambda **_kwargs: False,
            enqueue_media_extraction=lambda **_kwargs: "unexpected",
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.database.media_uploads",
        SimpleNamespace(
            get_media_upload_by_storage_path=lambda storage_path: SimpleNamespace(
                id=4,
                file_id="file-1",
                original_filename="doc.pdf",
                content_type="application/pdf",
                owner_user_id=99,
                organization_id=77,
            )
        ),
    )
    token = set_req_ctx(
        RequestContext(
            request_id="req-knowledge-extraction",
            user=8,
            role="user",
            organization_id=12,
            access_level=3,
            channel="test",
        )
    )
    try:
        with pytest.raises(PermissionError, match="knowledge_extraction_media_upload_denied"):
            knowledge_mod.Knowledge(sdk).enqueue_extraction(storage_path="media/doc.pdf")
    finally:
        reset_req_ctx(token)
