from __future__ import annotations

import asyncio

import pytest

import democrai.core.infrastructure.storage.vector.milvus_store as milvus_mod
from democrai.core.infrastructure.storage.vector.base import (
    Filter,
    IndexSpec,
    Metric,
    Op,
    Predicate,
    Query,
    UserScope,
    VectorDoc,
)
from democrai.core.infrastructure.storage.vector.milvus_store import MilvusVectorProvider


class _Schema:
    def __init__(self):
        self.fields = []

    def add_field(self, **kwargs):
        self.fields.append(dict(kwargs))


class _IndexParams:
    def __init__(self):
        self.indexes = []

    def add_index(self, **kwargs):
        self.indexes.append(dict(kwargs))


class _MockMilvusClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.collections = {}
        self.created_collections = []
        self.loaded = []
        self.flushed = []
        self.insert_calls = []
        self.delete_calls = []
        self.query_calls = []
        self.search_calls = []
        self.created_indexes = []
        self.dropped_indexes = []
        self.dropped_collections = []
        self.query_results = []
        self.search_results = []
        self.indexes = [{"params": {"metric_type": "COSINE"}}]
        _MockMilvusClient.instances.append(self)

    @staticmethod
    def create_schema(**kwargs):
        schema = _Schema()
        schema.kwargs = dict(kwargs)
        return schema

    def prepare_index_params(self):
        return _IndexParams()

    def has_collection(self, *, collection_name):
        return collection_name in self.collections

    def create_collection(self, **kwargs):
        self.created_collections.append(dict(kwargs))
        fields = [
            {**field, "name": field.get("name") or field.get("field_name")}
            for field in kwargs["schema"].fields
        ]
        self.collections[kwargs["collection_name"]] = {
            "schema": {"fields": fields}
        }
        self.indexes = [
            {"params": {"metric_type": kwargs["index_params"].indexes[0]["metric_type"]}}
        ]

    def describe_collection(self, *, collection_name):
        return self.collections[collection_name]

    def drop_collection(self, *, collection_name):
        self.dropped_collections.append(collection_name)
        self.collections.pop(collection_name, None)

    def load_collection(self, *, collection_name):
        self.loaded.append(collection_name)

    def flush(self, *, collection_name):
        self.flushed.append(collection_name)

    def list_indexes(self, *, collection_name):
        return [f"idx-{idx}" for idx, _index in enumerate(self.indexes)]

    def describe_index(self, *, collection_name, index_name):
        return self.indexes[int(index_name.rsplit("-", 1)[1])]

    def create_index(self, *, collection_name, index_params):
        self.created_indexes.append((collection_name, index_params))
        self.indexes = [{"params": {"metric_type": index_params.indexes[0]["metric_type"]}}]

    def drop_index(self, *, collection_name, index_name):
        self.dropped_indexes.append((collection_name, index_name))

    def insert(self, *, collection_name, data):
        self.insert_calls.append((collection_name, data))

    def delete(self, *, collection_name, filter):
        self.delete_calls.append((collection_name, filter))

    def query(self, **kwargs):
        self.query_calls.append(dict(kwargs))
        if self.query_results:
            return self.query_results.pop(0)
        return []

    def search(self, **kwargs):
        self.search_calls.append(dict(kwargs))
        if self.search_results:
            return [self.search_results.pop(0)]
        return []


def _install_milvus_client(monkeypatch):
    _MockMilvusClient.instances = []
    monkeypatch.setattr(milvus_mod, "HAS_MILVUS", True)
    monkeypatch.setattr(milvus_mod, "MilvusClient", _MockMilvusClient)
    monkeypatch.setattr(
        milvus_mod,
        "DataType",
        type(
            "DataType",
            (),
            {
                "VARCHAR": "varchar",
                "INT64": "int64",
                "FLOAT_VECTOR": "float_vector",
                "JSON": "json",
            },
        ),
    )


def _provider(monkeypatch) -> tuple[MilvusVectorProvider, _MockMilvusClient]:
    _install_milvus_client(monkeypatch)
    provider = MilvusVectorProvider("localhost", 19530, user="u", password="p")
    return provider, _MockMilvusClient.instances[-1]


def _spec(metric: Metric = Metric.COSINE, dim: int = 3) -> IndexSpec:
    return IndexSpec(tenant_id="tenant", app_id="app", name="docs", dim=dim, metric=metric)


def _scope() -> UserScope:
    return UserScope(user_id=1, organization_id=10)


def test_milvus_provider_initializes_milvus_client_and_reports_info(monkeypatch):
    provider, client = _provider(monkeypatch)

    assert client.kwargs == {
        "uri": "http://localhost:19530",
        "user": "u",
        "password": "p",
    }
    info = asyncio.run(provider.info())
    assert info.name == "milvus-vector-remote"

    monkeypatch.setattr(milvus_mod, "HAS_MILVUS", False)
    with pytest.raises(ImportError, match="pymilvus"):
        MilvusVectorProvider("localhost", 19530)


def test_milvus_provider_ensure_index_creates_and_validates_collection(monkeypatch):
    provider, client = _provider(monkeypatch)
    spec = _spec(metric=Metric.L2)
    collection_name = provider._get_collection_name(spec)

    asyncio.run(provider.ensure_index(spec))

    created = client.created_collections[0]
    assert created["collection_name"] == collection_name
    assert created["consistency_level"] == "Session"
    assert created["index_params"].indexes == [
        {
            "field_name": "vector",
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            "params": {"nlist": 1024},
        }
    ]
    assert [field["field_name"] for field in created["schema"].fields] == [
        "id",
        "doc_id",
        "user_id",
        "organization_id",
        "vector",
        "metadata",
    ]
    assert client.loaded == [collection_name]

    asyncio.run(provider.ensure_index(spec))
    assert client.loaded[-1] == collection_name

    with pytest.raises(ValueError, match="dim mismatch"):
        asyncio.run(provider.ensure_index(_spec(metric=Metric.L2, dim=4)))

    client.collections[collection_name]["schema"]["fields"][-2]["dim"] = 3
    client.indexes = [{"params": {"metric_type": "COSINE"}}]
    with pytest.raises(ValueError, match="metric mismatch"):
        asyncio.run(provider.ensure_index(spec))

    client.indexes = []
    asyncio.run(provider.ensure_index(spec))
    assert client.created_indexes[-1][0] == collection_name


def test_milvus_provider_upsert_delete_query_and_filter_expressions(monkeypatch):
    provider, client = _provider(monkeypatch)
    spec = _spec()
    scope = _scope()
    collection_name = provider._get_collection_name(spec)
    client.collections[collection_name] = {
        "schema": {
            "fields": [
                {"name": "id"},
                {"name": "doc_id"},
                {"name": "user_id"},
                {"name": "organization_id"},
                {"name": "vector", "params": {"dim": 3}},
                {"name": "metadata"},
            ]
        }
    }

    docs = [
        VectorDoc(id="doc-1", vector=[0.1, 0.2, 0.3], metadata={"kind": "report"}),
        VectorDoc(id="doc-2", vector=[0.4, 0.5, 0.6], metadata={"kind": "note"}),
    ]
    asyncio.run(provider.upsert(scope, spec, docs))
    assert client.delete_calls[0][0] == collection_name
    assert "id in [" in client.delete_calls[0][1]
    assert client.insert_calls[0][1][0]["doc_id"] == "doc-1"
    assert client.insert_calls[0][1][0]["organization_id"] == 10
    assert client.flushed[-1] == collection_name

    flt = Filter.AND(
        Predicate("kind", Op.EQ, "report"),
        Filter.OR(
            Predicate("lang", Op.IN, ["it", "en"]),
            Predicate("rank", Op.GTE, 2),
        ),
    )
    client.search_results = [
        [
            {
                "id": "physical-doc-1",
                "distance": 0.25,
                "entity": {
                    "doc_id": "doc-1",
                    "metadata": {"kind": "report"},
                    "vector": [0.1, 0.2, 0.3],
                },
            }
        ]
    ]

    matches = asyncio.run(
        provider.query(
            scope,
            spec,
            Query(vector=[0.1, 0.2, 0.3], top_k=3, filter=flt, include_vectors=True),
        )
    )

    assert [match.id for match in matches] == ["doc-1"]
    search_call = client.search_calls[0]
    assert search_call["collection_name"] == collection_name
    assert search_call["output_fields"] == ["doc_id", "metadata", "vector"]
    assert search_call["filter"] == (
        'user_id == 1 and organization_id == 10 and '
        '(metadata["kind"] == "report" and '
        '(metadata["lang"] in ["it", "en"] or metadata["rank"] >= 2))'
    )

    assert milvus_mod._scope_org_value(UserScope(user_id=1)) == 0
    assert milvus_mod._milvus_literal(None) == '""'
    assert milvus_mod._milvus_literal(True) == "true"
    assert milvus_mod._metadata_expr('bad"key') == 'metadata["bad\\"key"]'
    with pytest.raises(ValueError, match="Empty filter"):
        milvus_mod._filter_to_expr(Filter())
    with pytest.raises(ValueError, match="Unsupported predicate op"):
        milvus_mod._predicate_to_expr(Predicate("kind", "BAD", "x"))


def test_milvus_provider_delete_by_filter_rebuild_and_drop(monkeypatch):
    provider, client = _provider(monkeypatch)
    spec = _spec()
    scope = _scope()
    collection_name = provider._get_collection_name(spec)
    client.collections[collection_name] = {"schema": {"fields": []}}
    client.query_results = [[{"doc_id": "doc-1"}, {"doc_id": "doc-2"}], []]

    deleted = asyncio.run(
        provider.delete_by_filter(scope, spec, Filter.p("kind", Op.EQ, "report"))
    )

    assert deleted == 2
    assert client.query_calls[0]["filter"] == (
        'user_id == 1 and organization_id == 10 and metadata["kind"] == "report"'
    )
    assert client.delete_calls[0][1].startswith("user_id == 1 and organization_id == 10 and id in")

    assert asyncio.run(provider.delete_ids(scope, spec, [])) == 0
    with pytest.raises(TypeError, match="expects a Filter"):
        asyncio.run(provider.delete_by_filter(scope, spec, "bad"))

    asyncio.run(provider.rebuild(spec))
    assert client.dropped_indexes == [(collection_name, "idx-0")]
    assert client.created_indexes[-1][0] == collection_name
    assert client.loaded[-1] == collection_name

    asyncio.run(provider.drop_index(spec))
    assert client.dropped_collections == [collection_name]
