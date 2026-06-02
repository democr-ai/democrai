from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pytest

from democrai.core.application.ai.engine.schemas.completion import CompletionResponse
from democrai.core.application.ai.constants import AICapability
from democrai.core.application.ai.pipeline_context import AIPipelineContext
from democrai.core.application.knowledge.ai_capture import ingest_ai_completion_call
import democrai.core.application.knowledge.configuration as knowledge_config_mod
from democrai.core.application.knowledge.embedding import HashEmbeddingProvider
from democrai.core.application.knowledge.ingestion_queue_processor import (
    KnowledgeIngestionQueueProcessor,
)
from democrai.core.application.knowledge.models import EntityInput
from democrai.core.application.knowledge.models import KnowledgeIngestItem
from democrai.core.application.knowledge.models import KnowledgeIngestRequest
from democrai.core.application.knowledge.models import KnowledgeRetrieveRequest
from democrai.core.application.knowledge.models import KnowledgeSourceInput
from democrai.core.application.knowledge.models import RelationInput
from democrai.core.application.knowledge.records import KnowledgeItemRecord
from democrai.core.application.knowledge.records import KnowledgeChatUploadContextRecord
from democrai.core.application.knowledge.records import KnowledgeExtractedItemRecord
from democrai.core.application.knowledge.records import KnowledgeExtractionRequestRecord
from democrai.core.application.knowledge.records import KnowledgeIngestionRequestRecord
from democrai.core.application.knowledge.records import KnowledgeOutboxRecord
from democrai.core.application.knowledge.repository import KnowledgeRepository
import democrai.core.application.knowledge.service as service_mod
from democrai.core.application.knowledge.service import KnowledgeService
from democrai.core.application.knowledge.triples import HeuristicTripleExtractor
from democrai.core.infrastructure.database.models import Base
from democrai.core.infrastructure.database.models import EngineRegistry
from democrai.core.infrastructure.database.models import MediaUpload
from democrai.core.infrastructure.database.models import ModelRegistry
from democrai.core.infrastructure.storage.vector.base import IndexSpec
from democrai.core.infrastructure.storage.vector.base import Match
from democrai.core.infrastructure.storage.vector.base import Metric
from democrai.core.infrastructure.storage.vector.base import ProviderInfo
from democrai.core.runtime.foundation.app import RequestContext
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx
from democrai.core.runtime.foundation.app import reset_req_ctx
from democrai.core.runtime.foundation.app import set_req_ctx


class _FakeVectorStore:
    def __init__(self):
        self.docs = {}
        self.ensure_calls = []

    async def info(self):
        return ProviderInfo(name="fake-vector", version="1", capabilities=0)

    async def ensure_index(self, spec):
        self.ensure_calls.append(spec.name)

    async def drop_index(self, spec):
        self.docs.clear()

    async def upsert(self, scope, spec, docs):
        for doc in docs:
            self.docs[(scope.user_id, scope.organization_id, doc.id)] = {
                "scope": scope,
                "spec": spec,
                "vector": list(doc.vector),
                "metadata": dict(doc.metadata or {}),
            }

    async def delete_ids(self, scope, spec, ids):
        for item_id in ids:
            self.docs.pop((scope.user_id, scope.organization_id, item_id), None)
        return len(ids)

    async def delete_by_filter(self, scope, spec, flt):
        return 0

    async def query(self, scope, spec, q):
        matches = []
        for (doc_user_id, doc_organization_id, item_id), payload in self.docs.items():
            if scope.user_id != doc_user_id or scope.organization_id != doc_organization_id:
                continue
            score = 0.95 if q.vector == payload["vector"] else 0.65
            matches.append(Match(id=item_id, score=score, metadata=payload["metadata"]))
        return sorted(matches, key=lambda item: item.score, reverse=True)[: q.top_k]

    async def rebuild(self, spec):
        return None


class _FakeKGStore:
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.evidence = {}
        self.edge_evidence = {}
        self.traversal_calls = []

    async def add_node(self, node):
        key = (node.user_id, node.organization_id, node.id)
        if key in self.nodes:
            raise RuntimeError("duplicate node")
        self.nodes[key] = node

    async def get_node(self, user_id, node_id, organization_id=None):
        return self.nodes.get((user_id, organization_id, node_id))

    async def update_node(self, user_id, node_id, properties, organization_id=None, **kwargs):
        node = self.nodes[(user_id, organization_id, node_id)]
        node.properties.update(properties)
        if "name" in kwargs:
            node.name = kwargs["name"]
        if "external_ref" in kwargs:
            node.external_ref = kwargs["external_ref"]

    async def delete_node(self, user_id, node_id, soft=True, organization_id=None):
        self.nodes.pop((user_id, organization_id, node_id), None)

    async def add_edge(self, edge):
        key = (edge.user_id, edge.organization_id, edge.id)
        if key in self.edges:
            raise RuntimeError("duplicate edge")
        self.edges[key] = edge

    async def get_edge(self, user_id, edge_id, organization_id=None):
        return self.edges.get((user_id, organization_id, edge_id))

    async def update_edge(self, user_id, edge_id, properties, organization_id=None, **kwargs):
        edge = self.edges[(user_id, organization_id, edge_id)]
        edge.properties.update(properties)
        edge.weight = kwargs.get("weight")
        edge.confidence = kwargs.get("confidence")
        edge.source = kwargs.get("source")
        edge.evidence_id = kwargs.get("evidence_id")

    async def delete_edge(self, user_id, edge_id, soft=True, organization_id=None):
        self.edges.pop((user_id, organization_id, edge_id), None)

    async def add_evidence(self, evidence):
        key = (evidence.user_id, evidence.organization_id, evidence.id)
        if key in self.evidence:
            raise RuntimeError("duplicate evidence")
        self.evidence[key] = evidence

    async def delete_evidence(self, user_id, evidence_id, organization_id=None):
        self.evidence.pop((user_id, organization_id, evidence_id), None)

    async def link_edge_to_evidence(self, user_id, edge_id, evidence_id, organization_id=None):
        self.edge_evidence.setdefault((user_id, organization_id, edge_id), set()).add(evidence_id)

    async def get_neighbors(self, user_id, node_id, edge_type=None, limit=10, organization_id=None):
        results = []
        for edge in self.edges.values():
            if edge.src != node_id:
                continue
            if edge.user_id != user_id or edge.organization_id != organization_id:
                continue
            if edge_type and edge.type != edge_type:
                continue
            results.append(
                {
                    "edge_id": edge.id,
                    "edge_type": edge.type,
                    "node_id": edge.dst,
                    "weight": edge.weight,
                    "confidence": edge.confidence,
                }
            )
        return results[:limit]

    async def traversal(self, user_id, start_node_id, max_depth=2, organization_id=None):
        self.traversal_calls.append(
            {
                "user_id": user_id,
                "start_node_id": start_node_id,
                "max_depth": max_depth,
                "organization_id": organization_id,
            }
        )
        frontier = [(start_node_id, 0)]
        visited = {start_node_id}
        results = []
        while frontier:
            node_id, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            for edge in self.edges.values():
                if edge.src != node_id:
                    continue
                if edge.user_id != user_id or edge.organization_id != organization_id:
                    continue
                next_node = edge.dst
                next_depth = depth + 1
                results.append({"node_id": next_node, "depth": next_depth})
                if next_node in visited:
                    continue
                visited.add(next_node)
                frontier.append((next_node, next_depth))
        return results

    async def prune_orphan_nodes(self, user_id, node_ids, organization_id=None):
        pruned = 0
        for node_id in dict.fromkeys(str(node_id) for node_id in node_ids if node_id):
            has_active_edges = any(
                edge.user_id == user_id
                and edge.organization_id == organization_id
                and edge.deleted_at is None
                and (edge.src == node_id or edge.dst == node_id)
                for edge in self.edges.values()
            )
            if has_active_edges:
                continue
            if self.nodes.pop((user_id, organization_id, node_id), None) is not None:
                pruned += 1
        return pruned

    def run_migrations(self):
        return None


def _build_service(tmp_path, **service_kwargs):
    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge.db'}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    repository = KnowledgeRepository(SessionLocal)
    service = KnowledgeService(
        repository=repository,
        vector_store=_FakeVectorStore(),
        kg_store=_FakeKGStore(),
        vector_spec=IndexSpec(
            tenant_id="democrai",
            app_id="knowledge",
            name="items",
            dim=8,
            metric=Metric.COSINE,
            embedding_model_id="hash-embedding",
            embedding_model_version="1",
        ),
        embedding_provider=HashEmbeddingProvider(dim=8),
        triple_extractor=HeuristicTripleExtractor(),
        **service_kwargs,
    )
    return service


def test_knowledge_service_ingest_projection_and_retrieval(tmp_path):
    service = _build_service(tmp_path)
    item = KnowledgeIngestItem(
        item_id="item-1",
        kind="document_chunk",
        title="Acme contract",
        content="Acme works with Globex on a procurement platform.",
        summary="Acme and Globex partnership",
        metadata={"page": 1},
        entities=(
            EntityInput(name="Acme", entity_type="Organization"),
            EntityInput(name="Globex", entity_type="Organization"),
        ),
        relations=(
            RelationInput(
                relation_type="PARTNERS_WITH",
                source_entity_name="Acme",
                target_entity_name="Globex",
                weight=0.9,
                confidence=0.8,
            ),
        ),
    )
    result = service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-1",
                source_type="document",
                title="Contract",
                metadata={"module_name": "docs"},
            ),
            items=(item,),
        )
    )

    assert result.source_id == "src-1"
    assert result.item_ids == ("item-1",)
    assert len(result.outbox_ids) == 2

    processed = asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-1",
            lease_seconds=30,
            max_attempts=3,
        )
    )
    assert processed == 2
    assert (1, 101, "item-1") in service.vector_store.docs
    assert (1, 101, "ki:item-1") in service.kg_store.nodes
    assert (1, 101, "ks:src-1") in service.kg_store.nodes
    assert len([key for key in service.kg_store.nodes if key[2].startswith("entity:")]) == 2

    retrieved = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
            user_id=1,
                organization_id=101,
                query_text="Acme partnership",
                top_k=3,
            )
        )
    )
    assert retrieved.matches
    assert retrieved.matches[0].item_id == "item-1"
    assert retrieved.matches[0].graph_neighbors

    module_filtered = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                query_text="Acme partnership",
                top_k=3,
                metadata_filters={"module_name": "docs"},
            )
        )
    )
    assert [match.item_id for match in module_filtered.matches] == ["item-1"]

    wrong_module = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                query_text="Acme partnership",
                top_k=3,
                metadata_filters={"module_name": "other"},
            )
        )
    )
    assert wrong_module.matches == ()


def test_knowledge_service_delete_by_metadata_cleans_scoped_artifacts(tmp_path):
    service = _build_service(tmp_path)
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="chat-source",
                source_type="ai_engine_call",
                metadata={"module_name": "chat", "conversation_id": 42},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="chat-message",
                    kind="agent_message",
                    content="secret user text",
                    metadata={"conversation_id": 42},
                ),
                KnowledgeIngestItem(
                    item_id="chat-image",
                    kind="image_summary",
                    content="secret image summary",
                    metadata={"conversation_id": 42},
                ),
            ),
        )
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="other-source",
                source_type="ai_engine_call",
                metadata={"module_name": "other", "conversation_id": 42},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="other-message",
                    kind="agent_message",
                    content="other module text",
                    metadata={"conversation_id": 42},
                ),
            ),
        )
    )
    pending = service.repository.enqueue_ingestion_request(
        user_id=1,
        organization_id=101,
        source=KnowledgeSourceInput(
            source_type="ai_engine_call",
            metadata={"module_name": "chat"},
        ),
        items=(
            KnowledgeIngestItem(
                kind="agent_message",
                content="pending secret text",
                metadata={"conversation_id": 42},
            ),
        ),
        origin_type="ai_capture",
    )
    service.repository.enqueue_extraction_request(
        request_id="extract-chat",
        user_id=1,
        organization_id=101,
        owner_access_level=3,
        module_name="chat",
        storage_path="media/chat/file.txt",
        original_filename="file.txt",
        source_context={"module_name": "chat", "conversation_id": 42},
    )
    service.repository.complete_extraction_with_items(
        request_id="extract-chat",
        user_id=1,
        organization_id=101,
        items=[
            {
                "item_type": "chunk",
                "ordinal": 1,
                "content_text": "extracted secret text",
                "metadata": {"conversation_id": 42},
            }
        ],
        enqueue_ingestion=False,
    )
    with service.repository._session_factory() as session:
        session.add(
            KnowledgeChatUploadContextRecord(
                id="ctx-chat",
                file_id="file-1",
                user_id=1,
                organization_id=101,
                owner_access_level=3,
                pipeline_id="pipe-1",
                context_json=service.repository._json_dump(
                    {"module_name": "chat", "conversation_id": 42}
                ),
            )
        )
        session.commit()

    result = service.delete_by_metadata(
        user_id=1,
        organization_id=101,
        metadata_filters={"module_name": "chat", "conversation_id": 42},
    )

    assert {item["item_id"] for item in result["deleted_items"]} == {
        "chat-message",
        "chat-image",
    }
    assert len(result["outbox_ids"]) == 6
    assert result["cancelled_ingestion_ids"] == (pending.id,)
    assert result["cancelled_extraction_ids"] == ("extract-chat",)
    assert result["deleted_extracted_items"] == 1
    assert result["deleted_chat_upload_context_ids"] == ("ctx-chat",)
    with service.repository._session_factory() as session:
        assert session.get(KnowledgeItemRecord, "chat-message").deleted_at is not None
        assert session.get(KnowledgeItemRecord, "chat-image").deleted_at is not None
        assert session.get(KnowledgeItemRecord, "other-message").deleted_at is None
        assert session.get(KnowledgeIngestionRequestRecord, pending.id).status == "cancelled"
        assert session.get(KnowledgeExtractionRequestRecord, "extract-chat").status == "cancelled"
        assert session.query(KnowledgeExtractedItemRecord).count() == 0
        assert session.query(KnowledgeChatUploadContextRecord).count() == 0
        topics = sorted(row.topic for row in session.query(KnowledgeOutboxRecord).all())
    assert topics.count("knowledge.vector_delete") == 2
    assert topics.count("knowledge.kg_delete") == 2
    assert topics.count("knowledge.classification_delete") == 2


def test_knowledge_service_force_delete_by_metadata_purges_scoped_artifacts(tmp_path):
    service = _build_service(tmp_path)
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="chat-force-source",
                source_type="ai_engine_call",
                metadata={"module_name": "chat", "conversation_id": 42},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="chat-force-message",
                    kind="agent_message",
                    content="Alice knows Bob",
                    metadata={"conversation_id": 42},
                ),
                KnowledgeIngestItem(
                    item_id="chat-force-image",
                    kind="image_summary",
                    content="Image mentions Alice",
                    metadata={"conversation_id": 42},
                ),
            ),
        )
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="other-force-source",
                source_type="ai_engine_call",
                metadata={"module_name": "other", "conversation_id": 42},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="other-force-message",
                    kind="agent_message",
                    content="Other module text",
                    metadata={"conversation_id": 42},
                ),
            ),
        )
    )
    asyncio.run(
        service.process_outbox_once(
            batch_size=20,
            lease_owner="worker-force-upsert",
            lease_seconds=30,
            max_attempts=3,
        )
    )

    result = service.delete_by_metadata(
        user_id=1,
        organization_id=101,
        metadata_filters={"module_name": "chat", "conversation_id": 42},
        force=True,
    )
    assert result["force"] is True
    assert len(result["outbox_ids"]) == 6
    assert result["deleted_ingestion_ids"] == ()
    processed = asyncio.run(
        service.process_outbox_once(
            batch_size=20,
            lease_owner="worker-force-delete",
            lease_seconds=30,
            max_attempts=3,
        )
    )

    assert processed == 6
    with service.repository._session_factory() as session:
        assert session.get(service.repository.KnowledgeItemRecord, "chat-force-message") is None
        assert session.get(service.repository.KnowledgeItemRecord, "chat-force-image") is None
        assert session.get(service.repository.KnowledgeSourceRecord, "chat-force-source") is None
        assert session.get(service.repository.KnowledgeItemRecord, "other-force-message") is not None
        assert session.query(service.repository.KnowledgeEntityRecord).filter(
            service.repository.KnowledgeEntityRecord.item_id.in_(
                ("chat-force-message", "chat-force-image")
            )
        ).count() == 0
        assert session.query(service.repository.KnowledgeRelationRecord).filter(
            service.repository.KnowledgeRelationRecord.item_id.in_(
                ("chat-force-message", "chat-force-image")
            )
        ).count() == 0
        assert session.query(KnowledgeOutboxRecord).filter(
            KnowledgeOutboxRecord.aggregate_id.in_(
                ("chat-force-message", "chat-force-image")
            )
        ).count() == 0
    assert (1, 101, "chat-force-message") not in service.vector_store.docs
    assert (1, 101, "chat-force-image") not in service.vector_store.docs
    assert (1, 101, "other-force-message") in service.vector_store.docs
    assert not [
        key for key in service.kg_store.nodes
        if key[2] in {"ki:chat-force-message", "ki:chat-force-image", "ks:chat-force-source"}
    ]
    assert not [
        key for key in service.kg_store.evidence
        if key[2].startswith("evidence:chat-force-")
    ]


def test_knowledge_force_delete_removes_matching_ingestion_requests(tmp_path):
    service = _build_service(tmp_path)
    row = service.repository.enqueue_ingestion_request(
        user_id=1,
        organization_id=101,
        origin_type="chat",
        source=KnowledgeSourceInput(
            source_id="queued-sensitive",
            source_type="chat",
            metadata={"module_name": "chat", "conversation_id": 42},
        ),
        items=(
            KnowledgeIngestItem(
                item_id="queued-sensitive-item",
                kind="chat_turn",
                content="sensitive queued text",
                metadata={"conversation_id": 42},
            ),
        ),
        request_context={"module_name": "chat", "prompt": "sensitive prompt"},
    )
    processor = KnowledgeIngestionQueueProcessor(
        service=service,
        repository=service.repository,
    )
    assert processor.process_batch(batch_size=1).completed == 1

    result = service.delete_by_metadata(
        user_id=1,
        organization_id=101,
        metadata_filters={"module_name": "chat", "conversation_id": 42},
        force=True,
    )

    assert result["deleted_ingestion_ids"] == (row.id,)
    with service.repository._session_factory() as session:
        assert session.get(service.repository.KnowledgeIngestionRequestRecord, row.id) is None


def test_knowledge_service_rejects_cross_tenant_ingest_identifier_reuse(tmp_path):
    service = _build_service(tmp_path)
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-shared",
                source_type="document",
                metadata={"module_name": "docs"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="item-shared",
                    kind="document_chunk",
                    content="Tenant one knowledge",
                ),
            ),
        )
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="media-noise-source",
                source_type="document",
                metadata={"module_name": "system"},
            ),
            items=tuple(
                KnowledgeIngestItem(
                    item_id=f"media-noise-{index}",
                    kind="document_chunk",
                    content="Attachment context mentions Atlas",
                    metadata={"file_id": f"media-noise-file-{index}"},
                )
                for index in range(12)
            ),
        )
    )

    with pytest.raises(PermissionError):
        service.ingest(
            KnowledgeIngestRequest(
                user_id=2,
                organization_id=202,
                source=KnowledgeSourceInput(
                    source_id="src-shared",
                    source_type="document",
                    metadata={"module_name": "docs"},
                ),
                items=(
                    KnowledgeIngestItem(
                        kind="document_chunk",
                        content="Tenant two source collision",
                    ),
                ),
            )
        )
    assert service.repository.get_source("src-shared").user_id == 1

    with pytest.raises(PermissionError):
        service.ingest(
            KnowledgeIngestRequest(
                user_id=2,
                organization_id=202,
                source=KnowledgeSourceInput(
                    source_id="src-tenant-two",
                    source_type="document",
                    metadata={"module_name": "docs"},
                ),
                items=(
                    KnowledgeIngestItem(
                        item_id="item-shared",
                        kind="document_chunk",
                        content="Tenant two item collision",
                    ),
                ),
            )
        )
    assert service.repository.get_item("item-shared").user_id == 1


def test_knowledge_ingestion_queue_persists_via_service_and_outbox(tmp_path):
    service = _build_service(tmp_path)
    row = service.repository.enqueue_ingestion_request(
        user_id=1,
        organization_id=101,
        origin_type="chat",
        source=KnowledgeSourceInput(
            source_id="queued-chat",
            source_type="chat",
            metadata={"module_name": "chat"},
        ),
        items=(
            KnowledgeIngestItem(
                item_id="queued-chat-item",
                kind="chat_turn",
                content="Queued chat knowledge",
                metadata={"role": "user"},
            ),
        ),
    )
    processor = KnowledgeIngestionQueueProcessor(
        service=service,
        repository=service.repository,
    )

    stats = processor.process_batch(batch_size=1)

    assert stats.claimed == 1
    assert stats.completed == 1
    assert stats.failed == 0
    assert service.repository.get_source("queued-chat").user_id == 1
    assert service.repository.get_item("queued-chat-item").organization_id == 101
    with service.repository._session_factory() as session:
        assert (
            session.get(service.repository.KnowledgeIngestionRequestRecord, row.id).status
            == "completed"
        )

    processed = asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-ingestion-queue",
            lease_seconds=30,
            max_attempts=3,
        )
    )
    assert processed == 2
    assert (1, 101, "queued-chat-item") in service.vector_store.docs


def test_knowledge_ai_capture_uses_pipeline_source_and_request_context(monkeypatch):
    captured = []
    original_service = getattr(app_ctx(), "knowledge_service", None)
    app_ctx().knowledge_service = SimpleNamespace(
        repository=SimpleNamespace(
            enqueue_ingestion_request=lambda **kwargs: captured.append(kwargs)
        )
    )
    token = set_req_ctx(
        RequestContext(
            request_id="req-ai-capture",
            user=7,
            role="admin",
            organization_id=11,
            access_level=3,
            channel="bus",
            app=app_ctx(),
            session_key="session-ai-capture",
            action_name="chat.send",
            module_name="chat",
            stream_id="stream-ai-capture",
        )
    )
    try:
        context = AIPipelineContext(
            pipeline_id="pipe-1",
            current_pipeline_id="pipe-child-1",
            parent_pipeline_id=None,
            request_id="req-ai-capture",
            root_method="generate_completion",
            provider="vllm",
            engine="vllm",
            engine_row_id=3,
            model_registry_id=9,
            model_name="Qwen",
            caller_module="chat",
            user_id=7,
            organization_id=11,
        )
        ingest_ai_completion_call(
            context=context,
            method="generate_completion",
            messages=[
                {"role": "system", "content": "Do not persist this."},
                {"role": "user", "content": "Remember this answer."},
            ],
            response=CompletionResponse(id="resp-1", content="Stored answer."),
            ingest_meta={"module_name": "chat", "chat_id": "chat-1"},
        )
    finally:
        reset_req_ctx(token)
        app_ctx().knowledge_service = original_service

    assert len(captured) == 1
    request = captured[0]
    assert request["user_id"] == 7
    assert request["organization_id"] == 11
    assert request["origin_type"] == "ai_capture"
    assert request["source"].source_type == "ai_engine_call"
    assert request["source"].source_id == "pipe-1"
    assert request["source"].metadata["chat_id"] == "chat-1"
    assert request["source"].metadata["pipeline_id"] == "pipe-1"
    assert [item.content for item in request["items"]] == [
        "Remember this answer.",
        "Stored answer.",
    ]
    assert request["items"][0].item_id == "pipe-child-1:message:1"
    assert request["items"][1].item_id == "pipe-child-1:response"


def test_knowledge_ai_capture_persists_pipeline_and_request_context_to_queue(tmp_path):
    service = _build_service(tmp_path)
    original_service = getattr(app_ctx(), "knowledge_service", None)
    app_ctx().knowledge_service = service
    token = set_req_ctx(
        RequestContext(
            request_id="req-ai-queue",
            user=7,
            role="admin",
            organization_id=11,
            access_level=3,
            channel="bus",
            app=app_ctx(),
            session_key="session-ai-queue",
            action_name="chat.send",
            module_name="chat",
            stream_id="stream-ai-queue",
        )
    )
    try:
        ingest_ai_completion_call(
            context=AIPipelineContext(
                pipeline_id="pipe-queue-1",
                current_pipeline_id="pipe-queue-child-1",
                parent_pipeline_id="pipe-parent-1",
                request_id="req-ai-queue",
                root_method="generate_stream",
                provider="vllm",
                engine="vllm",
                engine_row_id=3,
                model_registry_id=9,
                model_name="Qwen",
                caller_module="chat",
                user_id=7,
                organization_id=11,
            ),
            method="generate_stream",
            messages=[{"role": "user", "content": "Remember queued answer."}],
            stream_chunks=[
                SimpleNamespace(delta="Queued "),
                SimpleNamespace(delta="answer."),
            ],
            ingest_meta={"module_name": "chat", "chat_id": "chat-queue"},
        )
    finally:
        reset_req_ctx(token)
        app_ctx().knowledge_service = original_service

    with service.repository._session_factory() as session:
        row = session.query(service.repository.KnowledgeIngestionRequestRecord).one()
        source = service.repository._json_load(row.source_json)
        items = service.repository._json_load(row.items_json)
        request_context = service.repository._json_load(row.request_context_json)

    assert row.origin_type == "ai_capture"
    assert row.status == "pending"
    assert request_context["request_id"] == "req-ai-queue"
    assert request_context["session_key"] == "session-ai-queue"
    assert source["source_id"] == "pipe-queue-1"
    assert source["metadata"]["pipeline_id"] == "pipe-queue-1"
    assert source["metadata"]["parent_pipeline_id"] == "pipe-parent-1"
    assert source["metadata"]["chat_id"] == "chat-queue"
    assert [item["content"] for item in items] == [
        "Remember queued answer.",
        "Queued answer.",
    ]
    assert items[0]["item_id"] == "pipe-queue-child-1:message:0"
    assert items[1]["item_id"] == "pipe-queue-child-1:response"


def test_knowledge_config_model_options_show_embedding_without_dim_and_engine_label(
    tmp_path,
    monkeypatch,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge-config.db'}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        engine_row = EngineRegistry(
            name="vllm engine",
            provider="vllm",
            status="active",
            supported=True,
        )
        session.add(engine_row)
        session.flush()
        session.add(
            ModelRegistry(
                name="Embedder",
                engine_id=engine_row.id,
                capabilities="embedding",
                status="active",
                extra_config={},
            )
        )
        session.commit()
    monkeypatch.setattr(knowledge_config_mod, "SessionLocal", SessionLocal)

    options = knowledge_config_mod.list_model_options_for_capability(
        AICapability.EMBEDDING
    )

    assert {"label": "Embedder (vllm engine)", "value": 1} in options


def test_count_existing_embeddings_reads_core_knowledge_items(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge-config-count.db'}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.add_all(
            [
                KnowledgeItemRecord(
                    id="item-with-embedding",
                    source_id="source-1",
                    user_id=1,
                    organization_id=101,
                    kind="document_chunk",
                    content="Embedded content",
                    embedding_text="Embedded content",
                    metadata_json="{}",
                    content_hash="hash-1",
                    embedding_vector_json="[0.1,0.2]",
                ),
                KnowledgeItemRecord(
                    id="item-without-embedding",
                    source_id="source-1",
                    user_id=1,
                    organization_id=101,
                    kind="document_chunk",
                    content="Pending content",
                    embedding_text="Pending content",
                    metadata_json="{}",
                    content_hash="hash-2",
                ),
            ]
        )
        session.commit()
    monkeypatch.setattr(knowledge_config_mod, "SessionLocal", SessionLocal)

    assert knowledge_config_mod.count_existing_embeddings() == 1


@pytest.mark.asyncio
async def test_save_knowledge_runtime_config_reloads_runtime_after_save(monkeypatch):
    from democrai.core.application.knowledge import runtime_reload as reload_mod
    import democrai.sdk.knowledge as knowledge_sdk_mod
    from modules.system.actions.knowledge import config as action_mod

    calls = []
    monkeypatch.setattr(
        knowledge_config_mod,
        "update_knowledge_runtime_config",
        lambda payload, *, confirm_embedding_model_change=False: calls.append(
            ("update", payload, confirm_embedding_model_change)
        )
        or {"enabled": True},
    )
    monkeypatch.setattr(
        reload_mod,
        "reload_knowledge_runtime",
        lambda: calls.append(("reload",)),
    )

    class Effects:
        @staticmethod
        def notify(channel, payload):
            return {"notify": {"channel": channel, "payload": payload}}

        @staticmethod
        def ui_messages(messages):
            return {"ui_messages": messages}

        @staticmethod
        def render():
            return {"render": True}

        @staticmethod
        def respond(*effects):
            return {"effects": effects}

    module_sdk = SimpleNamespace(
        knowledge=knowledge_sdk_mod.Knowledge(SimpleNamespace()),
        effects=Effects(),
        i18n=SimpleNamespace(t=lambda key, **_kwargs: key),
    )

    result = await action_mod.save_knowledge_runtime_config(
        {
            "knowledge_runtime_config_form": {
                "enabled": True,
                "embedding_model_registry_id": 7,
            }
        },
        {},
        module_sdk,
    )

    assert calls == [
        (
            "update",
            {"enabled": True, "embedding_model_registry_id": 7},
            False,
        ),
        ("reload",),
    ]
    assert result["effects"][1]["notify"]["payload"]["level"] == "success"


@pytest.mark.asyncio
async def test_save_knowledge_runtime_config_returns_error_when_reload_fails(monkeypatch):
    from democrai.core.application.knowledge import runtime_reload as reload_mod
    import democrai.sdk.knowledge as knowledge_sdk_mod
    from modules.system.actions.knowledge import config as action_mod

    monkeypatch.setattr(
        knowledge_config_mod,
        "update_knowledge_runtime_config",
        lambda payload, *, confirm_embedding_model_change=False: {"enabled": True},
    )

    def _raise_reload_error():
        raise RuntimeError("knowledge_reload_failed")

    monkeypatch.setattr(reload_mod, "reload_knowledge_runtime", _raise_reload_error)

    class Effects:
        @staticmethod
        def notify(channel, payload):
            return {"notify": {"channel": channel, "payload": payload}}

        @staticmethod
        def render():
            return {"render": True}

        @staticmethod
        def respond(*effects):
            return {"effects": effects}

    module_sdk = SimpleNamespace(
        knowledge=knowledge_sdk_mod.Knowledge(SimpleNamespace()),
        effects=Effects(),
        i18n=SimpleNamespace(t=lambda key, **_kwargs: key),
    )

    result = await action_mod.save_knowledge_runtime_config(
        {"knowledge_runtime_config_form": {"enabled": True}},
        {},
        module_sdk,
    )

    assert result["effects"][0]["notify"]["payload"] == {
        "level": "error",
        "message": "knowledge_reload_failed",
    }
    assert result["effects"][1] == {"render": True}


@pytest.mark.asyncio
async def test_save_knowledge_runtime_config_keeps_embedding_change_warning():
    from modules.system.actions.knowledge import config as action_mod

    class Knowledge:
        @staticmethod
        def update_runtime_config(payload, *, confirm_embedding_model_change=False):
            raise RuntimeError("knowledge_embedding_model_change_requires_rebuild")

        @staticmethod
        def count_existing_embeddings():
            return 4

    class Builder:
        def __init__(self):
            self.data = []

        def set_data(self, path, value):
            self.data.append((path, value))

    builder = Builder()

    class Effects:
        @staticmethod
        def ui_messages(messages):
            return {"ui_messages": messages}

        @staticmethod
        def build_aux_surface_messages(_builder, surface):
            return [{"surface": surface}]

        @staticmethod
        def respond(*effects):
            return {"effects": effects}

    module_sdk = SimpleNamespace(
        knowledge=Knowledge(),
        effects=Effects(),
        ui=SimpleNamespace(load=lambda _path: builder),
        i18n=SimpleNamespace(t=lambda key, **_kwargs: key),
    )

    result = await action_mod.save_knowledge_runtime_config(
        {"knowledge_runtime_config_form": {"enabled": True}},
        {},
        module_sdk,
    )

    assert result == {"effects": ({"ui_messages": [{"surface": "modal"}]},)}
    assert builder.data[0][0] == "/knowledge/embedding_model_change_warning"


def test_knowledge_outbox_persists_and_restores_request_context(tmp_path):
    service = _build_service(tmp_path)
    token = set_req_ctx(
        RequestContext(
            request_id="knowledge-request-1",
            user=1,
            role="admin",
            organization_id=101,
            access_level=3,
            channel="bus",
            app=app_ctx(),
            session_key="knowledge-session-1",
            action_name="system.knowledge.ingest",
            module_name="system",
            stream_id="stream-1",
        )
    )
    try:
        result = service.ingest(
            KnowledgeIngestRequest(
                user_id=1,
                organization_id=101,
                source=KnowledgeSourceInput(
                    source_id="src-context",
                    source_type="document",
                    title="Context",
                    metadata={"module_name": "docs"},
                ),
                items=(
                    KnowledgeIngestItem(
                        item_id="item-context",
                        kind="document",
                        title="Context",
                        content="Context body",
                    ),
                ),
            )
        )
    finally:
        reset_req_ctx(token)

    seen = []
    original = service._process_vector_job

    async def _wrapped(job):
        current = req_ctx()
        seen.append((current.request_id, current.session_key, current.action_name))
        await original(job)

    service._process_vector_job = _wrapped
    processed = asyncio.run(
        service.process_outbox_once(
            batch_size=1,
            lease_owner="worker-context",
            lease_seconds=30,
            max_attempts=3,
        )
    )

    assert processed == 1
    assert result.outbox_ids
    assert seen == [
        (
            "knowledge-request-1",
            "knowledge-session-1",
            "system.knowledge.ingest",
        )
    ]


def test_knowledge_repository_filters_items_by_metadata(tmp_path):
    service = _build_service(tmp_path)
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-chat-memory",
                source_type="ai_engine_call",
                metadata={"module_name": "chat"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="chat-memory-1",
                    kind="agent_message",
                    content="Memory about Atlas",
                    metadata={"module_name": "chat", "chat_id": "chat-a"},
                ),
                KnowledgeIngestItem(
                    item_id="chat-memory-2",
                    kind="agent_message",
                    content="Memory about Atlas",
                    metadata={"module_name": "chat", "chat_id": "chat-b"},
                ),
            ),
        )
    )

    rows = service.repository.search_items(
        user_id=1,
        organization_id=101,
        access_level=3,
        query_text="Atlas",
        limit=10,
        metadata_filters={"chat_id": "chat-a"},
    )

    assert [row.id for row in rows] == ["chat-memory-1"]


def test_knowledge_retrieve_keeps_pipeline_filter_without_thread_context(tmp_path):
    service = _build_service(tmp_path)
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-pipeline-filter",
                source_type="ai_engine_call",
                metadata={"module_name": "chat"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="pipeline-item-1",
                    kind="agent_message",
                    content="Memory about Atlas",
                    metadata={"pipeline_id": "pipe-a"},
                ),
                KnowledgeIngestItem(
                    item_id="pipeline-item-2",
                    kind="agent_message",
                    content="Memory about Atlas",
                    metadata={"pipeline_id": "pipe-b"},
                ),
            ),
        )
    )

    result = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                access_level=3,
                query_text="Atlas",
                top_k=10,
                metadata_filters={"pipeline_id": "pipe-a"},
            )
        )
    )

    assert [match.item_id for match in result.matches] == ["pipeline-item-1"]


def test_knowledge_retrieve_applies_chat_filters_to_items_or_upload_context(tmp_path):
    service = _build_service(tmp_path)
    with service.repository._session_factory() as session:
        session.add(
            MediaUpload(
                file_id="file-or-1",
                module_name="system",
                storage_path="media/system/or.pdf",
                original_filename="or.pdf",
                stored_filename="file-or-1_or.pdf",
                content_type="application/pdf",
                size_bytes=12,
                sha256="sha-or",
                scope_type="user",
                owner_user_id=1,
                organization_id=101,
                uploaded_by=1,
                uploader_access_level=3,
            )
        )
        session.commit()

    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="media:file-or-1",
                source_type="document",
                title="or.pdf",
                media_uri="media/system/or.pdf",
                metadata={"module_name": "system", "file_id": "file-or-1"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="media-chunk-or-1",
                    kind="document_chunk",
                    content="Attachment context mentions Atlas",
                    metadata={"page": 1},
                ),
            ),
        )
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="chat-filter-source",
                source_type="chat",
                metadata={"module_name": "chat"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="chat-filter-a",
                    kind="chat_turn",
                    content="Atlas in the selected chat",
                    metadata={"thread_id": "thread-a", "pipeline_id": "pipe-a"},
                ),
                KnowledgeIngestItem(
                    item_id="chat-filter-b",
                    kind="chat_turn",
                    content="Atlas in the wrong chat",
                    metadata={"thread_id": "thread-b", "pipeline_id": "pipe-b"},
                ),
            ),
        )
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="chat-filter-noise-source",
                source_type="chat",
                metadata={"module_name": "chat"},
            ),
            items=tuple(
                KnowledgeIngestItem(
                    item_id=f"chat-filter-noise-{index}",
                    kind="chat_turn",
                    content="Atlas noisy chat",
                    metadata={"thread_id": "thread-noise", "pipeline_id": "pipe-noise"},
                )
                for index in range(12)
            ),
        )
    )
    token = set_req_ctx(
        RequestContext(
            request_id="req-context-or",
            user=1,
            role=None,
            organization_id=101,
            access_level=3,
            channel="test",
            module_name="chat",
        )
    )
    try:
        service.repository.link_chat_upload_context(
            file_id="file-or-1",
            pipeline_id="pipe-a",
            context={
                "module_name": "chat",
                "pipeline_id": "pipe-a",
            },
        )
    finally:
        reset_req_ctx(token)

    result = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                access_level=3,
                query_text="Atlas",
                top_k=10,
                metadata_filters={"pipeline_id": "pipe-a"},
            )
        )
    )

    assert {match.item_id for match in result.matches} == {
        "media-chunk-or-1",
        "chat-filter-a",
    }
    assert "chat-filter-b" not in {match.item_id for match in result.matches}

    multi_pipeline = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                access_level=3,
                query_text="Atlas",
                top_k=10,
                metadata_filters={
                    "pipeline_id": ["missing", "pipe-a"],
                },
            )
        )
    )

    assert {match.item_id for match in multi_pipeline.matches} == {
        "media-chunk-or-1",
        "chat-filter-a",
    }

    missing_pipeline = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                access_level=3,
                query_text="Atlas",
                top_k=10,
                metadata_filters={"pipeline_id": "missing"},
            )
        )
    )

    assert missing_pipeline.matches == ()


def test_knowledge_retrieve_does_not_merge_other_user_chat_context(tmp_path):
    service = _build_service(tmp_path)
    with service.repository._session_factory() as session:
        session.add(
            MediaUpload(
                file_id="file-scope-1",
                module_name="system",
                storage_path="media/system/scope.pdf",
                original_filename="scope.pdf",
                stored_filename="file-scope-1_scope.pdf",
                content_type="application/pdf",
                size_bytes=12,
                sha256="sha-scope",
                scope_type="user",
                owner_user_id=1,
                organization_id=101,
                uploaded_by=1,
                uploader_access_level=3,
            )
        )
        session.commit()

    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="media:file-scope-1",
                source_type="document",
                title="scope.pdf",
                media_uri="media/system/scope.pdf",
                metadata={"module_name": "system", "file_id": "file-scope-1"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="media-chunk-scope-1",
                    kind="document_chunk",
                    content="Attachment context mentions Atlas",
                    metadata={"page": 1},
                    is_public=True,
                ),
            ),
        )
    )
    with service.repository._session_factory() as session:
        item = session.get(service.repository.KnowledgeItemRecord, "media-chunk-scope-1")
        item.owner_access_level = 3
        session.commit()
    token = set_req_ctx(
        RequestContext(
            request_id="req-context-scope",
            user=1,
            role=None,
            organization_id=101,
            access_level=3,
            channel="test",
            module_name="chat",
        )
    )
    try:
        service.repository.link_chat_upload_context(
            file_id="file-scope-1",
            pipeline_id="pipe-scope",
            context={
                "pipeline_id": "pipe-scope",
            },
        )
    finally:
        reset_req_ctx(token)

    result = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=2,
                organization_id=101,
                access_level=2,
                query_text="Atlas",
                top_k=10,
            )
        )
    )

    assert [match.item_id for match in result.matches] == ["media-chunk-scope-1"]
    assert "chat_context" not in result.matches[0].metadata
    assert "pipeline_id" not in result.matches[0].metadata

    super_result = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=2,
                organization_id=101,
                access_level=1,
                query_text="Atlas",
                top_k=10,
            )
        )
    )

    assert [match.item_id for match in super_result.matches] == ["media-chunk-scope-1"]
    assert "chat_context" not in super_result.matches[0].metadata
    assert "pipeline_id" not in super_result.matches[0].metadata


def test_knowledge_retrieve_reconciles_media_context_at_read_time(tmp_path):
    service = _build_service(tmp_path)
    with service.repository._session_factory() as session:
        session.add(
            MediaUpload(
                file_id="file-ctx-1",
                module_name="system",
                storage_path="media/system/context.pdf",
                original_filename="context.pdf",
                stored_filename="file-ctx-1_context.pdf",
                content_type="application/pdf",
                size_bytes=12,
                sha256="sha-context",
                scope_type="user",
                owner_user_id=1,
                organization_id=101,
                uploaded_by=1,
                uploader_access_level=3,
            )
        )
        session.commit()

    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="media:file-ctx-1",
                source_type="document",
                title="context.pdf",
                media_uri="media/system/context.pdf",
                metadata={"module_name": "system", "file_id": "file-ctx-1"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="media-chunk-ctx-1",
                    kind="document_chunk",
                    content="Attachment context mentions Atlas",
                    metadata={"page": 1},
                ),
            ),
        )
    )
    token = set_req_ctx(
        RequestContext(
            request_id="req-context-link",
            user=1,
            role=None,
            organization_id=101,
            access_level=3,
            channel="test",
            module_name="chat",
        )
    )
    try:
        service.repository.link_chat_upload_context(
            file_id="file-ctx-1",
            pipeline_id="pipe-ctx",
            context={
                "module_name": "chat",
                "pipeline_id": "pipe-ctx",
                "scenario": "attachment",
            },
        )
        service.repository.link_chat_upload_context(
            file_id="file-ctx-1",
            pipeline_id="pipe-ctx",
            context={
                "module_name": "chat",
                "pipeline_id": "pipe-ctx",
                "scenario": "attachment",
            },
        )
    finally:
        reset_req_ctx(token)
    with service.repository._session_factory() as session:
        assert session.query(service.repository.KnowledgeChatUploadContextRecord).count() == 1
        item = session.get(service.repository.KnowledgeItemRecord, "media-chunk-ctx-1")
        assert item.media_file_id == "file-ctx-1"

    result = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                access_level=3,
                query_text="Atlas",
                top_k=5,
                metadata_filters={
                    "pipeline_id": "pipe-ctx",
                    "scenario": "attachment",
                },
            )
        )
    )

    assert [match.item_id for match in result.matches] == ["media-chunk-ctx-1"]
    assert result.matches[0].metadata["pipeline_id"] == "pipe-ctx"
    assert result.matches[0].metadata["scenario"] == "attachment"
    assert result.matches[0].metadata["module_name"] == "chat"
    assert result.matches[0].metadata["chat_context"]["pipeline_id"] == "pipe-ctx"
    assert result.matches[0].metadata["chat_context"]["scenario"] == "attachment"

    token = set_req_ctx(
        RequestContext(
            request_id="req-context-link-other",
            user=1,
            role=None,
            organization_id=101,
            access_level=3,
            channel="test",
            module_name="chat",
        )
    )
    try:
        service.repository.link_chat_upload_context(
            file_id="file-ctx-1",
            pipeline_id="pipe-other",
            context={
                "module_name": "chat",
                "pipeline_id": "pipe-other",
            },
        )
    finally:
        reset_req_ctx(token)
    other_thread = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                access_level=3,
                query_text="Atlas",
                top_k=5,
                metadata_filters={"pipeline_id": "pipe-other"},
            )
        )
    )
    assert [match.item_id for match in other_thread.matches] == ["media-chunk-ctx-1"]
    assert other_thread.matches[0].metadata["pipeline_id"] == "pipe-other"

    no_matching_pipeline = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                access_level=3,
                query_text="Atlas",
                top_k=5,
                metadata_filters={"pipeline_id": "pipe-missing"},
            )
        )
    )
    assert no_matching_pipeline.matches == ()

    unfiltered = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                access_level=3,
                query_text="Atlas",
                top_k=5,
            )
        )
    )

    assert [match.item_id for match in unfiltered.matches] == [
        "media-chunk-ctx-1",
    ]
    assert "pipeline_id" not in unfiltered.matches[0].metadata
    assert "chat_context" not in unfiltered.matches[0].metadata


def test_knowledge_service_reprocessing_updated_item_is_idempotent(tmp_path):
    service = _build_service(tmp_path)
    first = KnowledgeIngestItem(
        item_id="item-1",
        kind="chat_turn",
        title="Turn 1",
        content="Alice works at Acme.",
        entities=(
            EntityInput(name="Alice", entity_type="Person"),
            EntityInput(name="Acme", entity_type="Organization"),
        ),
        relations=(
            RelationInput(
                relation_type="WORKS_AT",
                source_entity_name="Alice",
                target_entity_name="Acme",
            ),
        ),
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=None,
            source=KnowledgeSourceInput(
                source_id="chat-1",
                source_type="chat",
                metadata={"module_name": "chat"},
            ),
            items=(first,),
        )
    )
    asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-1",
            lease_seconds=30,
            max_attempts=3,
        )
    )

    updated = KnowledgeIngestItem(
        item_id="item-1",
        kind="chat_turn",
        title="Turn 1",
        content="Alice works at Acme and advises Globex.",
        entities=(
            EntityInput(name="Alice", entity_type="Person"),
            EntityInput(name="Acme", entity_type="Organization"),
            EntityInput(name="Globex", entity_type="Organization"),
        ),
        relations=(
            RelationInput(
                relation_type="WORKS_AT",
                source_entity_name="Alice",
                target_entity_name="Acme",
            ),
            RelationInput(
                relation_type="ADVISES",
                source_entity_name="Alice",
                target_entity_name="Globex",
            ),
        ),
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=None,
            source=KnowledgeSourceInput(
                source_id="chat-1",
                source_type="chat",
                metadata={"module_name": "chat"},
            ),
            items=(updated,),
        )
    )
    processed = asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-1",
            lease_seconds=30,
            max_attempts=3,
        )
    )

    assert processed == 2
    assert len(service.vector_store.docs) == 1
    assert (1, None, "edge:source:item-1") in service.kg_store.edges
    assert any(edge.type == "ADVISES" for edge in service.kg_store.edges.values())
    assert any(edge.type == "MENTIONED_IN" for edge in service.kg_store.edges.values())


def test_knowledge_service_marks_vector_job_dead_letter_without_embedder(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge.db'}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    repository = KnowledgeRepository(SessionLocal)
    service = KnowledgeService(
        repository=repository,
        vector_store=_FakeVectorStore(),
        kg_store=_FakeKGStore(),
        vector_spec=IndexSpec(
            tenant_id="democrai",
            app_id="knowledge",
            name="items",
            dim=8,
            metric=Metric.COSINE,
        ),
        embedding_provider=None,
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=None,
            source=KnowledgeSourceInput(
                source_type="chat",
                metadata={"module_name": "chat"},
            ),
            items=(KnowledgeIngestItem(kind="chat_turn", content="Missing embeddings"),),
        )
    )

    processed = asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-1",
            lease_seconds=30,
            max_attempts=1,
        )
    )

    assert processed == 2
    with SessionLocal() as session:
        dead_letter = session.execute(
            text("SELECT status FROM knowledge_outbox WHERE topic = 'knowledge.vector_upsert'")
        ).fetchone()
    assert dead_letter[0] == "dead_letter"


def test_knowledge_service_persists_classification_projection(tmp_path):
    class _ClassificationProvider:
        model_registry_id = 44
        model_id = "classification-model"
        model_version = "v1"

        def classify(self, texts):
            assert texts == ["Classify this content"]
            return [
                SimpleNamespace(
                    label="support",
                    score=0.91,
                    scores={"support": 0.91, "other": 0.09},
                )
            ]

    service = _build_service(
        tmp_path,
        classification_provider=_ClassificationProvider(),
    )
    result = service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-classification",
                source_type="document",
                metadata={"module_name": "docs"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="classification-item",
                    kind="document_chunk",
                    content="Classify this content",
                ),
            ),
        )
    )

    assert len(result.outbox_ids) == 3
    processed = asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-classification",
            lease_seconds=30,
            max_attempts=3,
        )
    )

    assert processed == 3
    with service.repository._session_factory() as session:
        row = session.execute(
            text(
                "SELECT model_registry_id, model_version, label, score, scores_json "
                "FROM knowledge_item_classifications "
                "WHERE item_id = 'classification-item'"
            )
        ).fetchone()
    assert row[0] == 44
    assert row[1] == "v1"
    assert row[2] == "support"
    assert row[3] == 0.91
    assert '"support": 0.91' in row[4]


def test_knowledge_service_delete_and_rebuild_source(tmp_path, monkeypatch):
    service = _build_service(tmp_path)
    monkeypatch.setattr(service, "_resolve_access_level", lambda user_id: 3)
    ingest_result = service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-1",
                source_type="document",
                is_public=True,
                metadata={"module_name": "docs"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="item-1",
                    kind="document_chunk",
                    content="Knowledge delete and rebuild flow",
                    is_public=True,
                    entities=(EntityInput(name="Acme", entity_type="Organization"),),
                ),
            ),
        )
    )
    asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-1",
            lease_seconds=30,
            max_attempts=3,
        )
    )
    assert (1, 101, "item-1") in service.vector_store.docs

    service.vector_store.docs.clear()
    assert service.rebuild_source(
        user_id=2,
        organization_id=101,
        source_id=ingest_result.source_id,
    ) == ()

    rebuild_jobs = service.rebuild_source(
        user_id=1,
        organization_id=101,
        source_id=ingest_result.source_id,
    )
    assert len(rebuild_jobs) == 2
    asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-rebuild",
            lease_seconds=30,
            max_attempts=3,
        )
    )
    assert (1, 101, "item-1") in service.vector_store.docs

    delete_jobs = service.delete_source(user_id=1, organization_id=101, source_id="src-1")
    assert len(delete_jobs) == 3
    asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-2",
            lease_seconds=30,
            max_attempts=3,
        )
    )
    assert (1, 101, "item-1") not in service.vector_store.docs
    assert (-1000000101, 101, "item-1") not in service.vector_store.docs
    assert (1, 101, "ki:item-1") not in service.kg_store.nodes

    assert service.rebuild_source(user_id=1, organization_id=101, source_id="src-1") == ()


def test_knowledge_service_admin_rebuild_sources(tmp_path, monkeypatch):
    service = _build_service(tmp_path)
    monkeypatch.setattr(service, "_resolve_access_level", lambda user_id: 3)

    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-doc",
                source_type="document",
                metadata={"module_name": "docs"},
            ),
            items=(KnowledgeIngestItem(item_id="item-doc", kind="document_chunk", content="Doc"),),
        )
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=2,
            organization_id=None,
            source=KnowledgeSourceInput(
                source_id="src-chat",
                source_type="chat_session",
                metadata={"module_name": "chat"},
            ),
            items=(KnowledgeIngestItem(item_id="item-chat", kind="chat_turn", content="Chat"),),
        )
    )

    filtered = service.admin_rebuild_sources(
        user_id=1,
        organization_id=101,
        source_type="document",
    )
    assert len(filtered) == 1
    assert filtered[0].source_id == "src-doc"
    assert filtered[0].user_id == 1
    assert filtered[0].organization_id == 101
    assert filtered[0].source_type == "document"
    assert len(filtered[0].outbox_ids) == 2

    def fail_request_bound_rebuild(**kwargs):
        raise AssertionError("admin rebuild must use canonical source scope")

    monkeypatch.setattr(service, "rebuild_source", fail_request_bound_rebuild)
    all_results = service.admin_rebuild_sources(limit=5)
    assert {result.source_id for result in all_results} == {"src-doc", "src-chat"}


def test_knowledge_service_retrieval_honors_public_visibility_and_strict_user_filter(tmp_path, monkeypatch):
    service = _build_service(tmp_path)
    monkeypatch.setattr(service, "_resolve_access_level", lambda user_id: {1: 3}.get(user_id, 3))

    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-doc",
                source_type="document",
                is_public=True,
                metadata={"module_name": "docs"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="doc-1",
                    kind="document_chunk",
                    title="Shared note",
                    content="Budget planning for Acme expansion",
                    is_public=True,
                ),
            ),
        )
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-chat",
                source_type="chat",
                is_public=True,
                metadata={"module_name": "chat"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="chat-1",
                    kind="chat_turn",
                    title="Private chat",
                    content="Sensitive agent conversation about Acme expansion",
                    is_public=True,
                ),
            ),
        )
    )
    asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-1",
            lease_seconds=30,
            max_attempts=3,
        )
    )

    shared = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=2,
                organization_id=101,
                query_text="Acme expansion",
                top_k=10,
                access_level=2,
            )
        )
    )
    match_ids = {match.item_id for match in shared.matches}
    assert "doc-1" in match_ids
    assert "chat-1" not in match_ids
    assert (-1000000101, 101, "doc-1") in service.vector_store.docs
    assert (-2000000000, None, "doc-1") in service.vector_store.docs
    assert (-1000000101, 101, "chat-1") not in service.vector_store.docs


@pytest.mark.parametrize(
    ("request_user_id", "request_access_level", "expected"),
    [
        (1, 3, {"doc-1", "chat-1"}),
        (3, 3, set()),
        (2, 2, {"doc-1"}),
    ],
)
def test_knowledge_service_retrieval_visibility_matrix(
    tmp_path,
    monkeypatch,
    request_user_id,
    request_access_level,
    expected,
):
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        service,
        "_resolve_access_level",
        lambda user_id: {1: 3, 2: 2, 3: 3}.get(user_id, 3),
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-1",
                source_type="document",
                is_public=True,
                metadata={"module_name": "docs"},
            ),
            items=(
                KnowledgeIngestItem(item_id="doc-1", kind="document_chunk", content="Visible public doc", is_public=True),
                KnowledgeIngestItem(item_id="chat-1", kind="chat_turn", content="Visible only to owner", is_public=True),
            ),
        )
    )
    asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-1",
            lease_seconds=30,
            max_attempts=3,
        )
    )
    retrieved = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=request_user_id,
                organization_id=101,
                access_level=request_access_level,
                query_text="Visible",
                top_k=10,
            )
        )
    )
    assert {match.item_id for match in retrieved.matches} == expected


def test_knowledge_service_extracts_graph_and_expands_retrieval(tmp_path):
    service = _build_service(tmp_path)
    service.vector_store.query = lambda scope, spec, q: asyncio.sleep(0, result=[Match(id="item-1", score=0.95, metadata={})])

    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-1",
                source_type="document",
                metadata={"module_name": "docs"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="item-1",
                    kind="document_chunk",
                    title="Partnership note",
                    content="Acme works with Globex on the Atlas platform.",
                ),
                KnowledgeIngestItem(
                    item_id="item-2",
                    kind="document_chunk",
                    title="Follow-up note",
                    content="Globex uses Atlas for procurement workflows.",
                ),
            ),
        )
    )
    asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-graph",
            lease_seconds=30,
            max_attempts=3,
        )
    )

    retrieved = asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                query_text="Acme partnership",
                top_k=5,
                lexical_limit=1,
            )
        )
    )

    match_ids = [match.item_id for match in retrieved.matches]
    assert "item-1" in match_ids
    assert "item-2" in match_ids
    assert any(edge.type == "PARTNERS_WITH" for edge in service.kg_store.edges.values())


def test_knowledge_service_uses_backend_specific_graph_depth(tmp_path):
    service = _build_service(
        tmp_path,
        graph_backend_key="neo4j",
        graph_traversal_depth=2,
        graph_traversal_depth_overrides={"default": 2, "ladybug": 1, "neo4j": 4},
    )
    service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-1",
                source_type="document",
                metadata={"module_name": "docs"},
            ),
            items=(
                KnowledgeIngestItem(
                    item_id="item-1",
                    kind="document_chunk",
                    content="Acme works with Globex.",
                ),
            ),
        )
    )
    asyncio.run(
        service.process_outbox_once(
            batch_size=10,
            lease_owner="worker-depth",
            lease_seconds=30,
            max_attempts=3,
        )
    )
    asyncio.run(
        service.retrieve(
            KnowledgeRetrieveRequest(
                user_id=1,
                organization_id=101,
                query_text="Acme",
                top_k=5,
            )
        )
    )
    assert service.kg_store.traversal_calls
    assert service.kg_store.traversal_calls[-1]["max_depth"] == 4


def test_knowledge_service_helper_branches_and_errors(tmp_path, monkeypatch):
    service = _build_service(
        tmp_path,
        graph_backend_key="custom-neo4j-backend",
        graph_traversal_depth=2,
        graph_traversal_depth_overrides={"default": 2, "neo4j": 6},
    )

    assert service._metadata_load("") == {}
    assert service._graph_traversal_depth() == 6

    with pytest.raises(ValueError, match="knowledge source not found"):
        service._module_name_for_source_id("missing-source")

    ingested = service.ingest(
        KnowledgeIngestRequest(
            user_id=1,
            organization_id=101,
            source=KnowledgeSourceInput(
                source_id="src-no-module",
                source_type="document",
                metadata={},
            ),
            items=(KnowledgeIngestItem(item_id="item-no-module", kind="document_chunk", content="x"),),
        )
    )
    with pytest.raises(ValueError, match="metadata missing module_name"):
        service._module_name_for_source_id(ingested.source_id)

    with pytest.raises(ValueError, match="module_name required"):
        service._vector_spec_for_module("")

    errors = []
    monkeypatch.setattr(
        service_mod,
        "app_ctx",
        lambda: type("Ctx", (), {"logger": type("L", (), {"error": lambda _self, msg: errors.append(msg)})()})(),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.auth.service",
        type(
            "AuthSvcMod",
            (),
            {"get_user_access_profile": staticmethod(lambda _uid: (_ for _ in ()).throw(RuntimeError("boom")))},
        )(),
    )
    assert service._resolve_access_level(1) == service_mod.ROLE_LEVEL_GUEST
    assert errors and "Failed to resolve access level" in errors[-1]
