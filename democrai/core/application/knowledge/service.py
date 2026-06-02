"""High-level orchestration service for the knowledge subsystem.

The service coordinates four distinct responsibilities:

- canonical persistence through :class:`KnowledgeRepository`
- asynchronous projection to vector and knowledge-graph stores
- retrieval that combines lexical, vector, and graph signals
- projection-scoped visibility derived from ownership and public flags

The service itself intentionally contains little business logic. Most
operations delegate to helper modules so ingestion, retrieval, and projection
policies can evolve independently while preserving a stable façade.
"""

from __future__ import annotations

import json
from typing import Any

from democrai.core.application.knowledge.classification import ClassificationProvider
from democrai.core.application.knowledge.embedding import EmbeddingProvider
from democrai.core.application.knowledge.models import KnowledgeIngestRequest
from democrai.core.application.knowledge.models import KnowledgeIngestResult
from democrai.core.application.knowledge.models import KnowledgeRebuildResult
from democrai.core.application.knowledge.models import KnowledgeRetrieveRequest
from democrai.core.application.knowledge.models import KnowledgeRetrieveResult
from democrai.core.application.knowledge.models import RelationInput
from democrai.core.application.knowledge.repository import ClaimedOutboxJob
from democrai.core.application.knowledge.repository import KnowledgeRepository
from democrai.core.application.knowledge.reranking import RerankProvider
from democrai.core.application.knowledge.service_helper.graph import entity_key
from democrai.core.application.knowledge.service_helper.graph import graph_entity_node_id
from democrai.core.application.knowledge.service_helper.graph import graph_scope_for_item
from democrai.core.application.knowledge.service_helper.graph import merge_graph_inputs
from democrai.core.application.knowledge.service_helper.graph import projection_scopes_for_item
from democrai.core.application.knowledge.service_helper.graph import refresh_item_graph
from democrai.core.application.knowledge.service_helper.graph import relation_key
from democrai.core.application.knowledge.service_helper.ingestion import admin_rebuild_sources
from democrai.core.application.knowledge.service_helper.ingestion import delete_by_metadata
from democrai.core.application.knowledge.service_helper.ingestion import delete_source
from democrai.core.application.knowledge.service_helper.ingestion import ingest
from democrai.core.application.knowledge.service_helper.ingestion import process_outbox_once
from democrai.core.application.knowledge.service_helper.ingestion import rebuild_source
from democrai.core.application.knowledge.service_helper.projection_graph import ensure_evidence
from democrai.core.application.knowledge.service_helper.projection_graph import (
    process_kg_delete_job,
)
from democrai.core.application.knowledge.service_helper.projection_graph import process_kg_job
from democrai.core.application.knowledge.service_helper.projection_classification import (
    process_classification_delete_job,
)
from democrai.core.application.knowledge.service_helper.projection_classification import (
    process_classification_job,
)
from democrai.core.application.knowledge.service_helper.projection_graph import upsert_edge
from democrai.core.application.knowledge.service_helper.projection_vector import (
    process_vector_delete_job,
)
from democrai.core.application.knowledge.service_helper.projection_vector import (
    process_vector_job,
)
from democrai.core.application.knowledge.service_helper.projection_vector import upsert_node
from democrai.core.application.knowledge.service_helper.retrieval import expand_graph_scores
from democrai.core.application.knowledge.service_helper.retrieval import (
    query_visible_vector_scopes,
)
from democrai.core.application.knowledge.service_helper.retrieval import retrieve
from democrai.core.application.knowledge.triples import TripleExtractor
from democrai.core.application.auth.roles import ROLE_LEVEL_GUEST
from democrai.core.infrastructure.storage.kg.providers.base import KGEdge
from democrai.core.infrastructure.storage.kg.providers.base import KGEvidence
from democrai.core.infrastructure.storage.kg.providers.base import KGNode
from democrai.core.infrastructure.storage.vector.base import IndexSpec
from democrai.core.infrastructure.database.models import MediaUpload
from democrai.core.runtime.foundation.app import app_ctx


def _metadata_load(payload: str) -> dict[str, Any]:
    return json.loads(payload or "{}")


class KnowledgeService:
    """Coordinate ingestion, retrieval, and downstream projections.

    :param repository: Canonical persistence façade for all knowledge records.
    :param vector_store: Vector backend used for semantic retrieval.
    :param kg_store: Knowledge-graph backend used for expansion and neighbors.
    :param vector_spec: Base vector index specification later specialized per
        module/source partition.
    :param embedding_provider: Provider used to compute item and query
        embeddings.
    :param triple_extractor: Optional extractor used to enrich items with
        entities and relations before KG projection.
    :param graph_traversal_depth: Default traversal depth for graph expansion.
    :param graph_expansion_limit: Number of seed items eligible for graph
        expansion during retrieval.
    :param graph_score_weight: Bonus multiplier applied to graph-derived items.
    :param graph_backend_key: Backend identifier used for traversal overrides.
    :param graph_traversal_depth_overrides: Optional backend-specific traversal
        depth values.
    """

    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        vector_store,
        kg_store,
        vector_spec: IndexSpec,
        embedding_provider: EmbeddingProvider | None = None,
        rerank_provider: RerankProvider | None = None,
        classification_provider: ClassificationProvider | None = None,
        triple_extractor: TripleExtractor | None = None,
        graph_traversal_depth: int = 2,
        graph_expansion_limit: int = 8,
        graph_score_weight: float = 0.2,
        graph_backend_key: str | None = None,
        graph_traversal_depth_overrides: dict[str, int] | None = None,
    ) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.kg_store = kg_store
        self.vector_spec = vector_spec
        self.embedding_provider = embedding_provider
        self.rerank_provider = rerank_provider
        self.classification_provider = classification_provider
        self.triple_extractor = triple_extractor
        self.graph_traversal_depth = max(1, graph_traversal_depth)
        self.graph_expansion_limit = max(1, graph_expansion_limit)
        self.graph_score_weight = max(0.0, graph_score_weight)
        self.graph_backend_key = (
            graph_backend_key if graph_backend_key is not None else type(kg_store).__name__
        ).lower()
        self.graph_traversal_depth_overrides = {
            key.lower(): max(1, value)
            for key, value in (graph_traversal_depth_overrides or {}).items()
        }

    _metadata_load = staticmethod(_metadata_load)

    def ingest(self, request: KnowledgeIngestRequest) -> KnowledgeIngestResult:
        return ingest(self, request)

    def delete_source(
        self,
        *,
        user_id: int,
        organization_id: int | None,
        source_id: str,
    ) -> tuple[str, ...]:
        return delete_source(
            self, user_id=user_id, organization_id=organization_id, source_id=source_id
        )

    def delete_by_metadata(
        self,
        *,
        user_id: int,
        organization_id: int | None,
        metadata_filters: dict,
        force: bool = False,
    ) -> dict:
        return delete_by_metadata(
            self,
            user_id=user_id,
            organization_id=organization_id,
            metadata_filters=metadata_filters,
            force=force,
        )

    def purge_deleted_item_if_ready(self, item_id: str) -> bool:
        return self.repository.purge_deleted_item_if_ready(item_id=item_id)

    def rebuild_source(
        self,
        *,
        user_id: int,
        organization_id: int | None,
        source_id: str,
    ) -> tuple[str, ...]:
        return rebuild_source(
            self, user_id=user_id, organization_id=organization_id, source_id=source_id
        )

    def admin_rebuild_sources(
        self,
        *,
        source_id: str | None = None,
        user_id: int | None = None,
        organization_id: int | None = None,
        source_type: str | None = None,
        limit: int | None = None,
    ) -> tuple[KnowledgeRebuildResult, ...]:
        return admin_rebuild_sources(
            self,
            source_id=source_id,
            user_id=user_id,
            organization_id=organization_id,
            source_type=source_type,
            limit=limit,
        )

    async def process_outbox_once(
        self,
        *,
        batch_size: int,
        lease_owner: str,
        lease_seconds: int,
        max_attempts: int,
    ) -> int:
        return await process_outbox_once(
            self,
            batch_size=batch_size,
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )

    async def retrieve(
        self, request: KnowledgeRetrieveRequest
    ) -> KnowledgeRetrieveResult:
        return await retrieve(self, request)

    async def _process_vector_job(self, job: ClaimedOutboxJob) -> None:
        await process_vector_job(self, job)

    async def _process_kg_job(self, job: ClaimedOutboxJob) -> None:
        await process_kg_job(self, job)

    async def _process_vector_delete_job(self, job: ClaimedOutboxJob) -> None:
        await process_vector_delete_job(self, job)

    async def _process_kg_delete_job(self, job: ClaimedOutboxJob) -> None:
        await process_kg_delete_job(self, job)

    async def _process_classification_job(self, job: ClaimedOutboxJob) -> None:
        await process_classification_job(self, job)

    async def _process_classification_delete_job(self, job: ClaimedOutboxJob) -> None:
        await process_classification_delete_job(self, job)

    async def _upsert_node(self, node: KGNode) -> None:
        await upsert_node(self, node)

    async def _upsert_edge(self, edge: KGEdge) -> None:
        await upsert_edge(self, edge)

    async def _ensure_evidence(self, evidence: KGEvidence) -> None:
        await ensure_evidence(self, evidence)

    async def _query_visible_vector_scopes(
        self,
        *,
        user_id: int,
        organization_id: int | None,
        access_level: int,
        query_vector: list[float],
        top_k: int,
        metadata_filters: dict[str, Any] | None = None,
    ) -> list[Any]:
        return await query_visible_vector_scopes(
            self,
            user_id=user_id,
            organization_id=organization_id,
            access_level=access_level,
            query_vector=query_vector,
            top_k=top_k,
            metadata_filters=metadata_filters,
        )

    async def _expand_graph_scores(
        self,
        *,
        request: KnowledgeRetrieveRequest,
        items: list[Any],
        scores: dict[str, float],
    ) -> list[tuple[str, float]]:
        return await expand_graph_scores(
            self, request=request, items=items, scores=scores
        )

    def _refresh_item_graph(
        self,
        *,
        item_id: str,
        user_id: int,
        organization_id: int | None,
    ) -> tuple[list[Any], list[Any]]:
        return refresh_item_graph(
            self, item_id=item_id, user_id=user_id, organization_id=organization_id
        )

    def _merge_graph_inputs(
        self, *, item: Any, entities: list[Any], relations: list[Any]
    ):
        return merge_graph_inputs(
            self, item=item, entities=entities, relations=relations
        )

    @staticmethod
    def _entity_key(name: str) -> str:
        return entity_key(name)

    @staticmethod
    def _relation_key(relation: RelationInput) -> tuple[str, str, str]:
        return relation_key(relation)

    @staticmethod
    def _graph_entity_node_id(entity: Any) -> str:
        return graph_entity_node_id(entity)

    def _projection_scopes_for_item(
        self,
        *,
        owner_user_id: int,
        owner_organization_id: int | None,
        owner_access_level: int,
        is_public: bool,
        kind: str,
    ) -> tuple[tuple[int, int | None], ...]:
        return projection_scopes_for_item(
            self,
            owner_user_id=owner_user_id,
            owner_organization_id=owner_organization_id,
            owner_access_level=owner_access_level,
            is_public=is_public,
            kind=kind,
        )

    def _graph_scope_for_item(
        self,
        *,
        requester_user_id: int,
        requester_organization_id: int | None,
        requester_access_level: int,
        owner_user_id: int,
        owner_organization_id: int | None,
        owner_access_level: int,
        is_public: bool,
        kind: str,
    ) -> tuple[int, int | None]:
        return graph_scope_for_item(
            self,
            requester_user_id=requester_user_id,
            requester_organization_id=requester_organization_id,
            requester_access_level=requester_access_level,
            owner_user_id=owner_user_id,
            owner_organization_id=owner_organization_id,
            owner_access_level=owner_access_level,
            is_public=is_public,
            kind=kind,
        )

    def _module_name_for_source_id(self, source_id: str) -> str:
        """Return the module name stored in the source metadata.

        Vector indexes are partitioned by module. Missing ``module_name`` means
        the source cannot be projected into the semantic index and is therefore
        treated as a configuration error.
        """

        source = self.repository.get_source(source_id)
        if source is None:
            raise ValueError(f"knowledge source not found: {source_id}")
        metadata = self._metadata_load(source.metadata_json)
        module_name = str((metadata or {}).get("module_name") or "").strip()
        if not module_name and source_id.startswith("media:"):
            file_id = source_id.removeprefix("media:").strip()
            with self.repository._session_factory() as session:
                upload = (
                    session.query(MediaUpload.module_name)
                    .filter(MediaUpload.file_id == file_id)
                    .one_or_none()
                )
            module_name = str(upload[0] if upload is not None else "").strip()
        if not module_name:
            raise ValueError(
                f"knowledge source '{source_id}' metadata missing module_name"
            )
        return module_name

    def _vector_spec_for_module(self, module_name: str) -> IndexSpec:
        """Derive the effective vector index specification for a module."""
        if not module_name:
            raise ValueError("module_name required for vector index app_id")
        return IndexSpec(
            tenant_id=self.vector_spec.tenant_id,
            app_id=module_name,
            name=self.vector_spec.name,
            dim=self.vector_spec.dim,
            metric=self.vector_spec.metric,
            embedding_model_id=self.vector_spec.embedding_model_id,
            embedding_model_version=self.vector_spec.embedding_model_version,
        )

    def _resolve_access_level(self, user_id: int) -> int:
        """Resolve the owner's access level used for projection scopes."""
        try:
            from democrai.core.application.auth.service import get_user_access_profile

            profile = get_user_access_profile(user_id)
            if profile is not None and profile.get("access_level") is not None:
                return int(profile["access_level"])
        except Exception as exc:
            logger = getattr(app_ctx(), "logger", None)
            if logger is not None:
                logger.error(
                    f"[Knowledge] Failed to resolve access level for {user_id}: {exc}"
                )
        return ROLE_LEVEL_GUEST

    def _graph_traversal_depth(self) -> int:
        """Resolve the graph traversal depth for the active KG backend."""
        backend_key = self.graph_backend_key
        if backend_key in self.graph_traversal_depth_overrides:
            return self.graph_traversal_depth_overrides[backend_key]
        for candidate, depth in self.graph_traversal_depth_overrides.items():
            if candidate != "default" and candidate in backend_key:
                return depth
        return self.graph_traversal_depth_overrides.get(
            "default", self.graph_traversal_depth
        )
