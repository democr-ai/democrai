from __future__ import annotations

import hashlib
from typing import Any, List, Optional, Sequence

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
    from pymilvus import (
        DataType,
        MilvusClient,
    )

    HAS_MILVUS = True
except ImportError:
    HAS_MILVUS = False


def _scope_org_value(scope: UserScope) -> int:
    return int(scope.organization_id or 0)


def _doc_key(scope: UserScope, doc_id: str) -> str:
    logical_key = f"{int(scope.user_id)}\x1f{_scope_org_value(scope)}\x1f{doc_id}"
    return hashlib.sha256(logical_key.encode("utf-8")).hexdigest()


def _milvus_literal(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _metadata_expr(key: str) -> str:
    safe_key = str(key).replace("\\", "\\\\").replace('"', '\\"')
    return f'metadata["{safe_key}"]'


def _predicate_to_expr(pred: Predicate) -> str:
    field_expr = _metadata_expr(pred.key)
    if pred.op == Op.EQ:
        return f"{field_expr} == {_milvus_literal(pred.value)}"
    if pred.op == Op.IN:
        values = pred.value if isinstance(pred.value, (list, tuple, set)) else [pred.value]
        rendered = ", ".join(_milvus_literal(item) for item in values)
        return f"{field_expr} in [{rendered}]"
    if pred.op == Op.LT:
        return f"{field_expr} < {_milvus_literal(pred.value)}"
    if pred.op == Op.LTE:
        return f"{field_expr} <= {_milvus_literal(pred.value)}"
    if pred.op == Op.GT:
        return f"{field_expr} > {_milvus_literal(pred.value)}"
    if pred.op == Op.GTE:
        return f"{field_expr} >= {_milvus_literal(pred.value)}"
    raise ValueError(f"Unsupported predicate op: {pred.op}")


def _filter_to_expr(flt: Filter) -> str:
    if flt.pred is not None:
        return _predicate_to_expr(flt.pred)
    if flt.and_:
        return "(" + " and ".join(_filter_item_expr(item) for item in flt.and_) + ")"
    if flt.or_:
        return "(" + " or ".join(_filter_item_expr(item) for item in flt.or_) + ")"
    raise ValueError("Empty filter is not valid")


def _filter_item_expr(item: Filter | Predicate) -> str:
    if isinstance(item, Predicate):
        return _predicate_to_expr(item)
    return _filter_to_expr(item)


def _field_name(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("name") or "")
    return str(getattr(field, "name", "") or "")


def _field_dim(field: Any) -> int | None:
    params = field.get("params") if isinstance(field, dict) else getattr(field, "params", None)
    if isinstance(params, dict) and params.get("dim") is not None:
        return int(params["dim"])
    if isinstance(field, dict) and field.get("dim") is not None:
        return int(field["dim"])
    dim = getattr(field, "dim", None)
    return int(dim) if dim is not None else None


def _schema_field_names(fields: Any) -> set[str]:
    return {_field_name(field) for field in list(fields or []) if _field_name(field)}


def _index_metric(index: Any) -> str | None:
    params = index.get("params") if isinstance(index, dict) else getattr(index, "params", None)
    if isinstance(params, dict) and params.get("metric_type"):
        return str(params["metric_type"]).upper()
    metric_type = index.get("metric_type") if isinstance(index, dict) else getattr(index, "metric_type", None)
    return str(metric_type).upper() if metric_type else None


class MilvusVectorProvider(VectorProvider):
    def __init__(
        self,
        host: str,
        port: int,
        user: Optional[str] = None,
        password: Optional[str] = None,
        alias: str = "default",
        index_prefix: str = "democrai",
    ):
        if not HAS_MILVUS:
            raise ImportError(
                "The 'pymilvus' package is required for MilvusVectorProvider. Install it with 'pip install pymilvus'."
            )

        self.alias = alias
        self.index_prefix = index_prefix
        client_kwargs: dict[str, Any] = {"uri": f"http://{host}:{int(port)}"}
        if user or password:
            client_kwargs["user"] = str(user or "")
            client_kwargs["password"] = str(password or "")
        self.client = MilvusClient(**client_kwargs)

    async def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="milvus-vector-remote",
            version="2.x",
            capabilities=Capability.FILTER_EQ
            | Capability.FILTER_IN
            | Capability.FILTER_RANGE
            | Capability.FILTER_AND
            | Capability.FILTER_OR
            | Capability.UPSERT_IDEMPOTENT
            | Capability.BULK_UPSERT
            | Capability.USER_SCOPED
            | Capability.DELETE_BY_FILTER
            | Capability.PARTITIONS
            | Capability.REBUILD_INDEX
            | Capability.RETURN_VECTORS,
        )

    def _get_collection_name(self, spec: IndexSpec) -> str:
        return physical_index_name(spec, getattr(self, "index_prefix", "democrai"))

    def _metric_name(self, metric: Metric) -> str:
        mapped = {
            Metric.COSINE: "COSINE",
            Metric.L2: "L2",
        }.get(metric)
        if mapped is None:
            raise ValueError(f"Unsupported vector metric for Milvus: {metric}")
        return mapped

    def _scope_expr(self, scope: UserScope) -> str:
        return (
            f'user_id == {_milvus_literal(scope.user_id)} and '
            f'organization_id == {_milvus_literal(_scope_org_value(scope))}'
        )

    def _build_expr(self, scope: UserScope, flt: Filter | None = None) -> str:
        expr = self._scope_expr(scope)
        if flt is None or (flt.pred is None and not flt.and_ and not flt.or_):
            return expr
        return f"{expr} and {_filter_to_expr(flt)}"

    def _load_collection(self, spec: IndexSpec) -> None:
        self.client.load_collection(collection_name=self._get_collection_name(spec))

    def _flush_collection(self, spec: IndexSpec) -> None:
        self.client.flush(collection_name=self._get_collection_name(spec))

    def _index_params(self, spec: IndexSpec):
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="IVF_FLAT",
            metric_type=self._metric_name(spec.metric),
            params={"nlist": 1024},
        )
        return index_params

    def _validate_existing_index(self, collection: dict[str, Any], spec: IndexSpec) -> None:
        schema = collection.get("schema") if isinstance(collection, dict) else None
        fields = schema.get("fields") if isinstance(schema, dict) else None
        if fields is None and isinstance(collection, dict):
            fields = collection.get("fields")
        field_names = _schema_field_names(fields)
        required_fields = {"id", "doc_id", "user_id", "organization_id", "vector", "metadata"}
        missing_fields = sorted(required_fields - field_names)
        if missing_fields:
            raise ValueError(
                "Milvus vector index schema missing required fields for "
                f"{self._get_collection_name(spec)}: {missing_fields}"
            )
        vector_field = None
        for field in list(fields or []):
            if _field_name(field) == "vector":
                vector_field = field
                break
        if vector_field is None:
            raise ValueError(f"Milvus vector index schema missing vector field: {self._get_collection_name(spec)}")
        dim = _field_dim(vector_field)
        if dim != int(spec.dim):
            raise ValueError(
                "Milvus vector index dim mismatch for "
                f"{self._get_collection_name(spec)}: existing={dim} requested={int(spec.dim)}"
            )
        expected_metric = self._metric_name(spec.metric)
        col_name = self._get_collection_name(spec)
        index_names = self.client.list_indexes(collection_name=col_name)
        metrics = []
        for index_name in list(index_names or []):
            index = self.client.describe_index(
                collection_name=col_name,
                index_name=str(index_name),
            )
            metric = _index_metric(index)
            if metric:
                metrics.append(metric)
        if not metrics:
            self.client.create_index(
                collection_name=col_name,
                index_params=self._index_params(spec),
            )
            self._load_collection(spec)
            return
        if metrics and expected_metric not in metrics:
            raise ValueError(
                "Milvus vector index metric mismatch for "
                f"{self._get_collection_name(spec)}: existing={metrics} requested={expected_metric}"
            )

    async def ensure_index(self, spec: IndexSpec) -> None:
        col_name = self._get_collection_name(spec)
        if not self.client.has_collection(collection_name=col_name):
            schema = MilvusClient.create_schema(
                auto_id=False,
                enable_dynamic_field=False,
            )
            schema.add_field(
                field_name="id",
                datatype=DataType.VARCHAR,
                is_primary=True,
                max_length=128,
            )
            schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=512)
            schema.add_field(field_name="user_id", datatype=DataType.INT64)
            schema.add_field(field_name="organization_id", datatype=DataType.INT64)
            schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=spec.dim)
            schema.add_field(field_name="metadata", datatype=DataType.JSON)
            self.client.create_collection(
                collection_name=col_name,
                schema=schema,
                index_params=self._index_params(spec),
                consistency_level="Session",
            )
            self._load_collection(spec)
            return

        self._validate_existing_index(
            self.client.describe_collection(collection_name=col_name),
            spec,
        )
        self._load_collection(spec)

    async def drop_index(self, spec: IndexSpec) -> None:
        col_name = self._get_collection_name(spec)
        if self.client.has_collection(collection_name=col_name):
            self.client.drop_collection(collection_name=col_name)

    async def upsert(
        self, scope: UserScope, spec: IndexSpec, docs: Sequence[VectorDoc]
    ) -> None:
        if not docs:
            return
        col_name = self._get_collection_name(spec)
        self._load_collection(spec)
        org_value = _scope_org_value(scope)
        ids_expr = ", ".join(_milvus_literal(_doc_key(scope, doc.id)) for doc in docs)
        self.client.delete(
            collection_name=col_name,
            filter=f"{self._scope_expr(scope)} and id in [{ids_expr}]",
        )
        self.client.insert(
            collection_name=col_name,
            data=[
                {
                    "id": _doc_key(scope, doc.id),
                    "doc_id": doc.id,
                    "user_id": int(scope.user_id),
                    "organization_id": org_value,
                    "vector": list(doc.vector),
                    "metadata": dict(doc.metadata or {}),
                }
                for doc in docs
            ],
        )
        self._flush_collection(spec)

    async def delete_ids(
        self, scope: UserScope, spec: IndexSpec, ids: Sequence[str]
    ) -> int:
        if not ids:
            return 0
        col_name = self._get_collection_name(spec)
        self._load_collection(spec)
        ids_expr = ", ".join(_milvus_literal(_doc_key(scope, item)) for item in ids)
        expr = f"{self._scope_expr(scope)} and id in [{ids_expr}]"
        self.client.delete(collection_name=col_name, filter=expr)
        self._flush_collection(spec)
        return len(ids)

    async def delete_by_filter(
        self, scope: UserScope, spec: IndexSpec, flt: Any
    ) -> int:
        if not isinstance(flt, Filter):
            raise TypeError("Milvus delete_by_filter expects a Filter instance")
        col_name = self._get_collection_name(spec)
        self._load_collection(spec)
        deleted = 0
        while True:
            query_res = self.client.query(
                collection_name=col_name,
                filter=self._build_expr(scope, flt),
                output_fields=["doc_id"],
                limit=16384,
            )
            if not query_res:
                return deleted
            ids = [row["doc_id"] for row in query_res if "doc_id" in row]
            if not ids:
                return deleted
            deleted += await self.delete_ids(scope, spec, ids)

    async def query(self, scope: UserScope, spec: IndexSpec, q: Query) -> List[Match]:
        col_name = self._get_collection_name(spec)
        self._load_collection(spec)
        output_fields = ["doc_id", "metadata"]
        if q.include_vectors:
            output_fields.append("vector")

        results = self.client.search(
            collection_name=col_name,
            data=[list(q.vector)],
            anns_field="vector",
            search_params={
                "metric_type": self._metric_name(spec.metric),
                "params": {"nprobe": 10},
            },
            limit=q.top_k,
            filter=self._build_expr(scope, q.filter),
            output_fields=output_fields,
        )

        matches: List[Match] = []
        for hit in results[0] if results else []:
            entity = hit.get("entity") if isinstance(hit, dict) else {}
            raw_id = hit.get("id") if isinstance(hit, dict) else None
            raw_score = hit.get("distance", hit.get("score", 0.0)) if isinstance(hit, dict) else 0.0
            matches.append(
                Match(
                    id=str((entity or {}).get("doc_id") or raw_id),
                    score=normalize_score(spec.metric, float(raw_score or 0.0)),
                    metadata=entity.get("metadata") if q.include_metadata else None,
                    vector=entity.get("vector") if q.include_vectors else None,
                )
            )
        return matches

    async def rebuild(self, spec: IndexSpec) -> None:
        col_name = self._get_collection_name(spec)
        for index_name in list(self.client.list_indexes(collection_name=col_name) or []):
            self.client.drop_index(collection_name=col_name, index_name=str(index_name))
        self.client.create_index(
            collection_name=col_name,
            index_params=self._index_params(spec),
        )
        self._load_collection(spec)
