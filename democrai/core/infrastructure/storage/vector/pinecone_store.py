from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from .base import (
    Capability,
    Filter,
    IndexSpec,
    Match,
    Metric,
    Op,
    Predicate,
    ProviderInfo,
    Query,
    UserScope,
    VectorDoc,
    VectorProvider,
    normalize_score,
    physical_index_name,
)

try:
    from pinecone import Pinecone, ServerlessSpec

    HAS_PINECONE = True
except ImportError:
    Pinecone = None  # type: ignore[assignment]
    ServerlessSpec = None  # type: ignore[assignment]
    HAS_PINECONE = False


def _provider_index_name(prefix: str, spec: IndexSpec) -> str:
    return physical_index_name(spec, prefix)


def _scope_namespace(scope: UserScope) -> str:
    org = str(scope.organization_id or "-")
    return f"user:{scope.user_id}|org:{org}"


def _predicate_to_filter(pred: Predicate) -> Dict[str, Any]:
    if pred.op == Op.EQ:
        return {pred.key: {"$eq": pred.value}}
    if pred.op == Op.IN:
        values = pred.value if isinstance(pred.value, (list, tuple, set)) else [pred.value]
        return {pred.key: {"$in": list(values)}}
    if pred.op == Op.LT:
        return {pred.key: {"$lt": pred.value}}
    if pred.op == Op.LTE:
        return {pred.key: {"$lte": pred.value}}
    if pred.op == Op.GT:
        return {pred.key: {"$gt": pred.value}}
    if pred.op == Op.GTE:
        return {pred.key: {"$gte": pred.value}}
    raise ValueError(f"Unsupported predicate op: {pred.op}")


def _filter_item_to_pinecone(item: Filter | Predicate) -> Dict[str, Any]:
    if isinstance(item, Predicate):
        return _predicate_to_filter(item)
    return _filter_to_pinecone(item)


def _filter_to_pinecone(flt: Filter) -> Dict[str, Any]:
    if flt.pred is not None:
        return _predicate_to_filter(flt.pred)
    if flt.and_:
        return {"$and": [_filter_item_to_pinecone(item) for item in flt.and_]}
    if flt.or_:
        return {"$or": [_filter_item_to_pinecone(item) for item in flt.or_]}
    raise ValueError("Empty filter is not valid")


class PineconeVectorProvider(VectorProvider):
    def __init__(
        self,
        api_key: str,
        *,
        cloud: str = "aws",
        region: str = "us-east-1",
        index_prefix: str = "democrai",
    ):
        if not HAS_PINECONE:
            raise ImportError(
                "The 'pinecone' package is required for PineconeVectorProvider. "
                "Install it with 'pip install pinecone'."
            )
        self.cloud = cloud
        self.region = region
        self.index_prefix = index_prefix
        self._client = Pinecone(api_key=api_key)
        self._index_cache: Dict[str, Any] = {}

    async def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="pinecone-serverless",
            version=None,
            capabilities=Capability.FILTER_EQ
            | Capability.FILTER_IN
            | Capability.FILTER_RANGE
            | Capability.FILTER_AND
            | Capability.FILTER_OR
            | Capability.BULK_UPSERT
            | Capability.USER_SCOPED
            | Capability.DELETE_BY_FILTER
            | Capability.RETURN_VECTORS,
        )

    def _metric_name(self, metric: Metric) -> str:
        mapped = {
            Metric.COSINE: "cosine",
            Metric.L2: "euclidean",
        }.get(metric)
        if mapped is None:
            raise ValueError(f"Unsupported vector metric for Pinecone: {metric}")
        return mapped

    def _index_name(self, spec: IndexSpec) -> str:
        return _provider_index_name(self.index_prefix, spec)

    def _list_index_names(self) -> set[str]:
        listed = self._client.list_indexes()
        if hasattr(listed, "names") and callable(listed.names):
            return {str(name) for name in listed.names()}
        if isinstance(listed, list):
            out: set[str] = set()
            for item in listed:
                if isinstance(item, str):
                    out.add(item)
                elif isinstance(item, Mapping) and item.get("name"):
                    out.add(str(item["name"]))
                elif hasattr(item, "name"):
                    out.add(str(item.name))
            return out
        return set()

    def _get_index(self, spec: IndexSpec):
        index_name = self._index_name(spec)
        cached = self._index_cache.get(index_name)
        if cached is not None:
            return cached
        idx = self._client.Index(index_name)
        self._index_cache[index_name] = idx
        return idx

    def _describe_index(self, index_name: str) -> Mapping[str, Any]:
        describe = getattr(self._client, "describe_index", None)
        if not callable(describe):
            raise ValueError(f"Pinecone client cannot validate existing index: {index_name}")
        description = describe(index_name)
        if isinstance(description, Mapping):
            return description
        values: dict[str, Any] = {}
        for key in ("dimension", "metric"):
            if hasattr(description, key):
                values[key] = getattr(description, key)
        return values

    def _validate_existing_index(self, spec: IndexSpec) -> None:
        index_name = self._index_name(spec)
        description = self._describe_index(index_name)
        dim = description.get("dimension")
        if int(dim) != int(spec.dim):
            raise ValueError(
                "Pinecone vector index dim mismatch for "
                f"{index_name}: existing={dim} requested={int(spec.dim)}"
            )
        metric = str(description.get("metric") or "").lower()
        expected_metric = self._metric_name(spec.metric)
        if metric != expected_metric:
            raise ValueError(
                "Pinecone vector index metric mismatch for "
                f"{index_name}: existing={metric} requested={expected_metric}"
            )

    async def ensure_index(self, spec: IndexSpec) -> None:
        index_name = self._index_name(spec)
        if index_name not in self._list_index_names():
            create_kwargs: dict[str, Any] = {
                "name": index_name,
                "dimension": spec.dim,
                "metric": self._metric_name(spec.metric),
            }
            if ServerlessSpec is not None:
                create_kwargs["spec"] = ServerlessSpec(cloud=self.cloud, region=self.region)
            self._client.create_index(**create_kwargs)
        else:
            self._validate_existing_index(spec)
        self._get_index(spec)

    async def drop_index(self, spec: IndexSpec) -> None:
        index_name = self._index_name(spec)
        self._client.delete_index(index_name)
        self._index_cache.pop(index_name, None)

    async def upsert(self, scope: UserScope, spec: IndexSpec, docs: Sequence[VectorDoc]) -> None:
        if not docs:
            return
        index = self._get_index(spec)
        vectors = [
            {
                "id": doc.id,
                "values": list(doc.vector),
                "metadata": dict(doc.metadata or {}),
            }
            for doc in docs
        ]
        index.upsert(vectors=vectors, namespace=_scope_namespace(scope))

    async def delete_ids(self, scope: UserScope, spec: IndexSpec, ids: Sequence[str]) -> int:
        if not ids:
            return 0
        index = self._get_index(spec)
        id_list = list(ids)
        index.delete(ids=id_list, namespace=_scope_namespace(scope))
        return len(id_list)

    async def delete_by_filter(self, scope: UserScope, spec: IndexSpec, flt: Filter) -> int:
        index = self._get_index(spec)
        index.delete(filter=_filter_to_pinecone(flt), namespace=_scope_namespace(scope))
        # Pinecone delete-by-filter API does not return deleted count.
        return 0

    async def query(self, scope: UserScope, spec: IndexSpec, q: Query) -> List[Match]:
        index = self._get_index(spec)
        query_kwargs: dict[str, Any] = {
            "vector": list(q.vector),
            "top_k": q.top_k,
            "namespace": _scope_namespace(scope),
            "include_metadata": q.include_metadata,
            "include_values": q.include_vectors,
        }
        if q.filter is not None:
            query_kwargs["filter"] = _filter_to_pinecone(q.filter)
        response = index.query(**query_kwargs)

        matches: List[Match] = []
        for item in getattr(response, "matches", []) or []:
            item_id = getattr(item, "id", None)
            if item_id is None and isinstance(item, Mapping):
                item_id = item.get("id")
            if item_id is None:
                continue
            raw_score = getattr(item, "score", None)
            if raw_score is None and isinstance(item, Mapping):
                raw_score = item.get("score", 0.0)
            metadata = getattr(item, "metadata", None)
            if metadata is None and isinstance(item, Mapping):
                metadata = item.get("metadata")
            values = getattr(item, "values", None)
            if values is None and isinstance(item, Mapping):
                values = item.get("values")
            matches.append(
                Match(
                    id=str(item_id),
                    score=normalize_score(spec.metric, float(raw_score or 0.0)),
                    metadata=metadata if q.include_metadata else None,
                    vector=list(values) if (q.include_vectors and values is not None) else None,
                )
            )
        return matches

    async def rebuild(self, spec: IndexSpec) -> None:
        _ = spec
        return None
