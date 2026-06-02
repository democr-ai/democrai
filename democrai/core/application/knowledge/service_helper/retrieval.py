"""Hybrid retrieval helpers combining lexical, vector, and graph signals.

Retrieval in the knowledge subsystem is deliberately multi-stage:

- vector search provides semantic recall over item embeddings
- lexical search recovers exact or recent textual matches
- graph expansion promotes adjacent items that are semantically connected

This module also applies metadata-aware weighting so high-level summaries and
segments can outrank raw chunks when both are relevant.
"""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Any

from democrai.core.application.knowledge.models import KnowledgeRetrieveMatch
from democrai.core.application.knowledge.models import KnowledgeRetrieveRequest
from democrai.core.application.knowledge.models import KnowledgeRetrieveResult
from democrai.core.application.knowledge.service_helper.metadata import infer_retrieval_tier
from democrai.core.application.knowledge.visibility import retrieval_scope_chain
from democrai.core.infrastructure.storage.vector.base import Query
from democrai.core.infrastructure.storage.vector.base import UserScope
from democrai.core.runtime.foundation.app import app_ctx


def _normalize_filter_values(value: Any) -> tuple[str, ...]:
    """Normalize a metadata filter value into a comparable tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(
            str(item).strip()
            for item in value
            if str(item).strip()
        )
    rendered = str(value).strip()
    return (rendered,) if rendered else ()


def _item_matches_metadata_filters(
    service,
    item: Any,
    filters: dict[str, Any],
) -> bool:
    """Return ``True`` when the item's metadata satisfies all requested filters."""
    if not filters:
        return True
    metadata = service._metadata_load(getattr(item, "metadata_json", "") or "")
    if not isinstance(metadata, dict):
        metadata = {}
    for key, raw_value in filters.items():
        expected_values = _normalize_filter_values(raw_value)
        if not expected_values:
            continue
        field = str(key)
        actual_value = str(metadata.get(field, "") or "").strip()
        if actual_value not in expected_values:
            return False
    return True


def _item_ranking_weight(service, item: Any) -> float:
    """Return a multiplicative score weight derived from item metadata.

    The weighting favors summary-like material and slightly penalizes raw or
    trace-oriented items so retrieval can surface overview nodes before deep
    detail while still keeping full recall available.
    """
    metadata = service._metadata_load(getattr(item, "metadata_json", "") or "")
    if not isinstance(metadata, dict):
        metadata = {}
    item_scope = str(metadata.get("item_scope") or "").strip().lower()
    item_kind = str(getattr(item, "kind", "") or "").strip().lower()
    source_kind = str(metadata.get("source_kind") or "").strip().lower()
    tier = int(metadata.get("retrieval_tier") or infer_retrieval_tier(item_scope=item_scope))

    weight = 1.0
    if tier == 1:
        weight += 0.28
    elif tier == 2:
        weight += 0.12
    elif tier >= 4:
        weight -= 0.18
    else:
        weight -= 0.04

    if item_scope in {"document", "chapter", "summary"}:
        weight += 0.08
    elif item_scope in {"paragraph", "segment", "transcript", "message"}:
        weight += 0.04
    elif item_scope in {"chunk", "paragraph_chunk", "raw"}:
        weight -= 0.08
    elif item_scope == "index":
        weight -= 0.14

    if item_kind in {"document_summary", "chapter_summary", "paragraph_summary"}:
        weight += 0.04
    elif item_kind in {"document_chunk", "agent_trace"}:
        weight -= 0.06

    if source_kind == "chat" and item_scope == "message":
        weight += 0.03
    elif source_kind in {"audio", "video"} and item_scope in {"transcript", "segment"}:
        weight += 0.03

    return max(0.35, weight)


def _rerank_item_scores(service, *, query_text: str, items: list[Any]) -> dict[str, float]:
    """Return model rerank scores keyed by item id."""
    provider = getattr(service, "rerank_provider", None)
    if provider is None or not items:
        return {}
    texts = [
        str(getattr(item, "summary", "") or getattr(item, "content", "") or "")
        for item in items
    ]
    results = provider.rerank(query=query_text, texts=texts)
    scores: dict[str, float] = {}
    for result in results or []:
        index = getattr(result, "index", None)
        score = getattr(result, "score", None)
        if isinstance(result, dict):
            index = result.get("index")
            score = result.get("score")
        try:
            item = items[int(index)]
            scores[item.id] = max(0.0, min(1.0, float(score)))
        except (TypeError, ValueError, IndexError):
            continue
    return scores


def _split_metadata_filters(
    request: KnowledgeRetrieveRequest,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    metadata_filters = dict(request.metadata_filters or {})
    context_filters: dict[str, Any] = {}
    item_chat_filters: dict[str, Any] = {}
    pipeline_values = _normalize_filter_values(metadata_filters.get("pipeline_id"))
    if pipeline_values:
        context_filters["pipeline_id"] = pipeline_values
        item_chat_filters = dict(metadata_filters)
    item_filters = dict(metadata_filters)
    return item_filters, context_filters, item_chat_filters


def _merge_chat_upload_contexts(
    service,
    *,
    request: KnowledgeRetrieveRequest,
    items: list[Any],
    context_filters: dict[str, Any],
    item_chat_filters: dict[str, Any],
):
    if not context_filters.get("pipeline_id") or not items:
        return {item.id: item for item in items}
    file_ids = [
        str(getattr(item, "media_file_id", "") or "").strip()
        for item in items
        if str(getattr(item, "media_file_id", "") or "").strip()
    ]
    contexts = ()
    if file_ids:
        contexts = service.repository.list_chat_upload_contexts(
            user_id=request.user_id,
            organization_id=request.organization_id,
            access_level=request.access_level,
            file_ids=tuple(dict.fromkeys(file_ids)),
            pipeline_id=context_filters.get("pipeline_id"),
        )
    context_by_file_id = {str(row.file_id): row for row in contexts}
    enriched: dict[str, Any] = {}
    for item in items:
        context_row = context_by_file_id.get(str(getattr(item, "media_file_id", "") or ""))
        if context_row is None:
            if not item_chat_filters or _item_matches_metadata_filters(
                service,
                item,
                item_chat_filters,
            ):
                enriched[item.id] = item
            continue
        metadata = service._metadata_load(getattr(item, "metadata_json", "") or "")
        if not isinstance(metadata, dict):
            metadata = {}
        context_payload = service._metadata_load(context_row.context_json)
        if not isinstance(context_payload, dict):
            context_payload = {}
        merged_metadata = {
            **metadata,
            **context_payload,
            "chat_context": context_payload,
        }
        if not _metadata_matches_filters(merged_metadata, item_chat_filters):
            continue
        payload = dict(getattr(item, "__dict__", {}) or {})
        payload["metadata_json"] = service.repository._json_dump(merged_metadata)
        payload.pop("_sa_instance_state", None)
        enriched[item.id] = SimpleNamespace(**payload)
    return enriched


def _metadata_matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, raw_value in filters.items():
        expected_values = _normalize_filter_values(raw_value)
        if not expected_values:
            continue
        actual_value = str(metadata.get(str(key), "") or "").strip()
        if actual_value not in expected_values:
            return False
    return True


async def retrieve(
    service, request: KnowledgeRetrieveRequest
) -> KnowledgeRetrieveResult:
    """Execute the full hybrid retrieval pipeline for a query."""
    query_vector = request.query_vector
    if query_vector is None and service.embedding_provider is not None:
        query_vector = service.embedding_provider.embed_texts([request.query_text])[0]

    item_filters, context_filters, item_chat_filters = _split_metadata_filters(request)
    vector_matches = []
    if query_vector is not None:
        vector_matches = await service._query_visible_vector_scopes(
            user_id=request.user_id,
            organization_id=request.organization_id,
            access_level=request.access_level,
            query_vector=query_vector,
            top_k=request.top_k,
            metadata_filters=item_filters,
        )

    lexical_items = service.repository.search_items(
        user_id=request.user_id,
        organization_id=request.organization_id,
        access_level=request.access_level,
        query_text=request.query_text,
        limit=request.lexical_limit,
        metadata_filters=item_filters,
    )
    if item_chat_filters:
        lexical_items.extend(
            service.repository.search_items(
                user_id=request.user_id,
                organization_id=request.organization_id,
                access_level=request.access_level,
                query_text=request.query_text,
                limit=request.lexical_limit,
                metadata_filters={**item_filters, **item_chat_filters},
            )
        )
    if context_filters.get("pipeline_id"):
        context_rows = service.repository.list_chat_upload_contexts(
            user_id=request.user_id,
            organization_id=request.organization_id,
            access_level=request.access_level,
            pipeline_id=context_filters.get("pipeline_id"),
        )
        lexical_items.extend(
            service.repository.search_items_by_media_file_ids(
                user_id=request.user_id,
                organization_id=request.organization_id,
                access_level=request.access_level,
                query_text=request.query_text,
                media_file_ids=tuple(row.file_id for row in context_rows),
                limit=request.lexical_limit,
                metadata_filters={},
            )
        )

    scores: dict[str, float] = defaultdict(float)
    ordered_ids: list[str] = []
    for match in vector_matches:
        scores[match.id] += float(match.score) * 0.8
        ordered_ids.append(match.id)
    for rank, item in enumerate(lexical_items):
        ordered_ids.append(item.id)
        scores[item.id] += max(0.05, 0.4 - (rank * 0.03))

    base_items = service.repository.get_items_by_ids(
        user_id=request.user_id,
        organization_id=request.organization_id,
        access_level=request.access_level,
        item_ids=ordered_ids,
        metadata_filters={} if context_filters else item_filters,
    )
    base_item_by_id = _merge_chat_upload_contexts(
        service,
        request=request,
        items=list(base_items),
        context_filters=context_filters,
        item_chat_filters=item_chat_filters,
    )
    base_items = [base_item_by_id[item.id] for item in base_items if item.id in base_item_by_id]
    for item in base_items:
        scores[item.id] = float(scores.get(item.id, 0.0)) * _item_ranking_weight(
            service, item
        )
    ordered_ids = [item.id for item in base_items]
    filtered_ids = set(ordered_ids)
    scores = {item_id: score for item_id, score in scores.items() if item_id in filtered_ids}

    for related_item_id, bonus_score in await service._expand_graph_scores(
        request=request,
        items=base_items,
        scores=scores,
    ):
        ordered_ids.append(related_item_id)
        scores[related_item_id] = float(scores.get(related_item_id, 0.0)) + float(
            bonus_score
        )

    items = service.repository.get_items_by_ids(
        user_id=request.user_id,
        organization_id=request.organization_id,
        access_level=request.access_level,
        item_ids=ordered_ids,
        metadata_filters={} if context_filters else item_filters,
    )
    item_by_id = _merge_chat_upload_contexts(
        service,
        request=request,
        items=list(items),
        context_filters=context_filters,
        item_chat_filters=item_chat_filters,
    )
    items = [item_by_id[item.id] for item in items if item.id in item_by_id]
    rerank_scores = _rerank_item_scores(
        service,
        query_text=request.query_text,
        items=items,
    )
    for item_id, rerank_score in rerank_scores.items():
        scores[item_id] = (float(scores.get(item_id, 0.0)) * 0.35) + (
            float(rerank_score) * 0.65
        )
    matches: list[KnowledgeRetrieveMatch] = []
    seen_item_ids: set[str] = set()
    logger = getattr(app_ctx(), "logger", None)
    for item in items:
        if item.id in seen_item_ids:
            continue
        seen_item_ids.add(item.id)
        try:
            (
                graph_scope_user_id,
                graph_scope_organization_id,
            ) = service._graph_scope_for_item(
                requester_user_id=request.user_id,
                requester_organization_id=request.organization_id,
                requester_access_level=request.access_level,
                owner_user_id=item.user_id,
                owner_organization_id=item.organization_id or None,
                owner_access_level=item.owner_access_level,
                is_public=bool(item.is_public),
                kind=item.kind,
            )
            neighbors = await service.kg_store.get_neighbors(
                graph_scope_user_id,
                f"ki:{item.id}",
                limit=request.graph_neighbors_limit,
                organization_id=graph_scope_organization_id,
            )
        except Exception as exc:
            neighbors = ()
            if logger is not None:
                logger.error(
                    "[KnowledgeRetrieve] neighbors_failed item_id=%s source_id=%s error=%r",
                    str(getattr(item, "id", "") or "-"),
                    str(getattr(item, "source_id", "") or "-"),
                    exc,
                )
        try:
            item_metadata = service._metadata_load(item.metadata_json)
        except Exception:
            item_metadata = {}
        matches.append(
            KnowledgeRetrieveMatch(
                item_id=item.id,
                source_id=item.source_id,
                kind=item.kind,
                title=item.title,
                content=item.content,
                summary=item.summary,
                score=min(1.0, scores.get(item.id, 0.0)),
                metadata=item_metadata,
                graph_neighbors=tuple(neighbors),
            )
        )
        if len(matches) >= request.top_k:
            break

    return KnowledgeRetrieveResult(
        matches=tuple(
            sorted(matches, key=lambda item: item.score, reverse=True)[: request.top_k]
        )
    )


async def query_visible_vector_scopes(
    service,
    *,
    user_id: int,
    organization_id: int | None,
    access_level: int,
    query_vector: list[float],
    top_k: int,
    metadata_filters: dict[str, Any] | None = None,
) -> list[Any]:
    """Query every visible vector scope and merge the best per-item score."""
    aggregated: dict[str, Any] = {}
    visible_module_names = service.repository.list_visible_source_module_names(
        user_id=user_id,
        organization_id=organization_id,
        access_level=access_level,
        metadata_filters=dict(metadata_filters or {}),
    )
    module_filter_values = set(
        _normalize_filter_values((metadata_filters or {}).get("module_name"))
    )
    if module_filter_values:
        module_names = tuple(
            name for name in visible_module_names if str(name) in module_filter_values
        )
    else:
        module_names = visible_module_names
    vector_specs = [
        service._vector_spec_for_module(module_name) for module_name in module_names
    ]
    if not vector_specs:
        return []
    for scope_user_id, scope_organization_id in retrieval_scope_chain(
        user_id=user_id,
        organization_id=organization_id,
        access_level=access_level,
    ):
        scope = UserScope(user_id=scope_user_id, organization_id=scope_organization_id)
        for vector_spec in vector_specs:
            matches = await service.vector_store.query(
                scope,
                vector_spec,
                Query(vector=query_vector, top_k=top_k),
            )
            for match in matches:
                current = aggregated.get(match.id)
                if current is None or float(match.score) > float(current.score):
                    aggregated[match.id] = match
    return sorted(aggregated.values(), key=lambda item: item.score, reverse=True)[
        :top_k
    ]


async def expand_graph_scores(
    service,
    *,
    request: KnowledgeRetrieveRequest,
    items: list[Any],
    scores: dict[str, float],
) -> list[tuple[str, float]]:
    """Promote related items discovered through bounded KG traversal."""
    if not items or service.graph_score_weight <= 0.0:
        return []

    ranked_items = sorted(
        items,
        key=lambda item: scores.get(item.id, 0.0),
        reverse=True,
    )[: service.graph_expansion_limit]
    aggregated: dict[str, float] = {}
    for item in ranked_items:
        seed_score = scores.get(item.id, 0.0)
        if seed_score <= 0.0:
            continue
        scope_user_id, scope_organization_id = service._graph_scope_for_item(
            requester_user_id=request.user_id,
            requester_organization_id=request.organization_id,
            requester_access_level=request.access_level,
            owner_user_id=item.user_id,
            owner_organization_id=item.organization_id or None,
            owner_access_level=item.owner_access_level,
            is_public=bool(item.is_public),
            kind=item.kind,
        )
        traversal = await service.kg_store.traversal(
            scope_user_id,
            f"ki:{item.id}",
            max_depth=service._graph_traversal_depth(),
            organization_id=scope_organization_id,
        )
        for entry in traversal:
            node_id = str(entry.get("node_id") or "")
            if not node_id.startswith("ki:"):
                continue
            related_item_id = node_id[3:]
            if related_item_id == item.id:
                continue
            depth = max(1, int(entry.get("depth") or service.graph_traversal_depth))
            bonus = max(0.01, (service.graph_score_weight * seed_score) / depth)
            current = aggregated.get(related_item_id, 0.0)
            if bonus > current:
                aggregated[related_item_id] = bonus
    return sorted(aggregated.items(), key=lambda entry: entry[1], reverse=True)
