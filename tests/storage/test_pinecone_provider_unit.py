from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import democrai.core.infrastructure.storage.vector.pinecone_store as pinecone_mod
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
from democrai.core.infrastructure.storage.vector.pinecone_store import PineconeVectorProvider


class _FakeIndex:
    def __init__(self):
        self.upsert_calls = []
        self.query_calls = []
        self.delete_calls = []

    def upsert(self, **kwargs):
        self.upsert_calls.append(kwargs)

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return SimpleNamespace(
            matches=[
                SimpleNamespace(
                    id="doc-1",
                    score=0.75,
                    metadata={"kind": "doc"},
                    values=[0.1, 0.2],
                )
            ]
        )

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)


class _FakePineconeClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.created = []
        self.deleted = []
        self._indexes = {}
        self._names = set()
        self._descriptions = {}

    def list_indexes(self):
        return list(self._names)

    def create_index(self, **kwargs):
        self.created.append(kwargs)
        self._names.add(kwargs["name"])
        self._descriptions[kwargs["name"]] = {
            "dimension": kwargs["dimension"],
            "metric": kwargs["metric"],
        }

    def describe_index(self, name):
        return self._descriptions[name]

    def delete_index(self, name):
        self.deleted.append(name)
        self._names.discard(name)

    def Index(self, name):
        self._names.add(name)
        index = self._indexes.get(name)
        if index is None:
            index = _FakeIndex()
            self._indexes[name] = index
        return index


class _FakeListWithNames:
    def __init__(self, names):
        self._names = list(names)

    def names(self):
        return list(self._names)


class _NamedItem:
    def __init__(self, name: str):
        self.name = name


def test_pinecone_filter_helpers_cover_supported_and_invalid_ops():
    flt = Filter.AND(
        Predicate("kind", Op.EQ, "report"),
        Filter.OR(
            Predicate("lang", Op.IN, ["it", "en"]),
            Predicate("rank", Op.GTE, 2),
        ),
    )
    rendered = pinecone_mod._filter_to_pinecone(flt)
    assert rendered == {
        "$and": [
            {"kind": {"$eq": "report"}},
            {"$or": [{"lang": {"$in": ["it", "en"]}}, {"rank": {"$gte": 2}}]},
        ]
    }
    with pytest.raises(ValueError, match="Empty filter"):
        pinecone_mod._filter_to_pinecone(Filter())
    with pytest.raises(ValueError, match="Unsupported predicate op"):
        pinecone_mod._predicate_to_filter(Predicate("kind", "BAD", "x"))


def test_pinecone_provider_paths(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pinecone_mod, "HAS_PINECONE", True)
    monkeypatch.setattr(pinecone_mod, "Pinecone", _FakePineconeClient)
    monkeypatch.setattr(
        pinecone_mod,
        "ServerlessSpec",
        lambda cloud, region: {"cloud": cloud, "region": region},
    )

    provider = PineconeVectorProvider(
        api_key="pc-key",
        cloud="aws",
        region="us-east-1",
        index_prefix="demo",
    )
    spec = IndexSpec(tenant_id="tenant", app_id="app", name="docs", dim=2, metric=Metric.COSINE)
    scope = UserScope(user_id="u1", organization_id="org-1")
    index_name = provider._index_name(spec)

    asyncio.run(provider.ensure_index(spec))
    assert provider._client.created[0]["name"] == index_name
    assert provider._client.created[0]["metric"] == "cosine"
    with pytest.raises(ValueError, match="dim mismatch"):
        asyncio.run(provider.ensure_index(IndexSpec(tenant_id="tenant", app_id="app", name="docs", dim=3, metric=Metric.COSINE)))
    with pytest.raises(ValueError, match="metric mismatch"):
        asyncio.run(provider.ensure_index(IndexSpec(tenant_id="tenant", app_id="app", name="docs", dim=2, metric=Metric.L2)))

    asyncio.run(
        provider.upsert(
            scope,
            spec,
            [
                VectorDoc(id="doc-1", vector=[0.1, 0.2], metadata={"kind": "doc"}),
            ],
        )
    )
    idx = provider._client._indexes[index_name]
    assert idx.upsert_calls[0]["namespace"] == "user:u1|org:org-1"

    matches = asyncio.run(
        provider.query(
            scope,
            spec,
            Query(
                vector=[0.1, 0.2],
                top_k=3,
                filter=Filter.p("kind", Op.EQ, "doc"),
                include_vectors=True,
            ),
        )
    )
    assert [item.id for item in matches] == ["doc-1"]
    assert matches[0].vector == [0.1, 0.2]
    assert idx.query_calls[0]["filter"] == {"kind": {"$eq": "doc"}}

    deleted_ids = asyncio.run(provider.delete_ids(scope, spec, ["doc-1"]))
    deleted_by_filter = asyncio.run(provider.delete_by_filter(scope, spec, Filter.p("kind", Op.EQ, "doc")))
    asyncio.run(provider.drop_index(spec))
    asyncio.run(provider.rebuild(spec))

    assert deleted_ids == 1
    assert deleted_by_filter == 0
    assert idx.delete_calls[0] == {"ids": ["doc-1"], "namespace": "user:u1|org:org-1"}
    assert idx.delete_calls[1]["filter"] == {"kind": {"$eq": "doc"}}
    assert provider._client.deleted == [index_name]


def test_pinecone_provider_import_error_when_package_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pinecone_mod, "HAS_PINECONE", False)
    with pytest.raises(ImportError, match="pinecone"):
        PineconeVectorProvider(api_key="pc-key")


def test_pinecone_filter_helpers_cover_range_ops_and_index_helpers():
    assert pinecone_mod._predicate_to_filter(Predicate("n", Op.LT, 1)) == {"n": {"$lt": 1}}
    assert pinecone_mod._predicate_to_filter(Predicate("n", Op.LTE, 1)) == {"n": {"$lte": 1}}
    assert pinecone_mod._predicate_to_filter(Predicate("n", Op.GT, 1)) == {"n": {"$gt": 1}}

    long_spec = IndexSpec(
        tenant_id="TENANT__ID",
        app_id="APP__ID",
        name="Very Long Name With Spaces" * 3,
        dim=2,
        metric=Metric.COSINE,
    )
    idx_name = pinecone_mod._provider_index_name("My Prefix", long_spec)
    assert idx_name.startswith("vec")
    assert len(idx_name) == 35
    assert "_" not in idx_name
    assert "-" not in idx_name

    assert pinecone_mod._scope_namespace(UserScope(user_id="u", organization_id=None)) == "user:u|org:-"


def test_pinecone_provider_list_index_name_shapes_and_metric_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pinecone_mod, "HAS_PINECONE", True)
    monkeypatch.setattr(pinecone_mod, "Pinecone", _FakePineconeClient)
    monkeypatch.setattr(pinecone_mod, "ServerlessSpec", None)

    provider = PineconeVectorProvider(api_key="pc-key")

    provider._client.list_indexes = lambda: _FakeListWithNames(["a", "b"])  # type: ignore[method-assign]
    assert provider._list_index_names() == {"a", "b"}

    provider._client.list_indexes = lambda: ["x", {"name": "y"}, _NamedItem("z")]  # type: ignore[method-assign]
    assert provider._list_index_names() == {"x", "y", "z"}

    provider._client.list_indexes = lambda: object()  # type: ignore[method-assign]
    assert provider._list_index_names() == set()

    assert provider._metric_name(Metric.L2) == "euclidean"
    with pytest.raises(ValueError, match="Unsupported vector metric"):
        provider._metric_name("bad")


def test_pinecone_provider_noop_paths_and_query_mapping(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pinecone_mod, "HAS_PINECONE", True)
    monkeypatch.setattr(pinecone_mod, "Pinecone", _FakePineconeClient)
    monkeypatch.setattr(
        pinecone_mod,
        "ServerlessSpec",
        lambda cloud, region: {"cloud": cloud, "region": region},
    )

    provider = PineconeVectorProvider(api_key="pc-key", index_prefix="demo")
    spec = IndexSpec(tenant_id="tenant", app_id="app", name="docs", dim=2, metric=Metric.COSINE)
    scope = UserScope(user_id="u1", organization_id="org-1")

    asyncio.run(provider.ensure_index(spec))
    created_len = len(provider._client.created)
    asyncio.run(provider.ensure_index(spec))
    assert len(provider._client.created) == created_len
    assert provider._client.created[0]["spec"] == {"cloud": "aws", "region": "us-east-1"}

    assert asyncio.run(provider.upsert(scope, spec, [])) is None
    assert asyncio.run(provider.delete_ids(scope, spec, [])) == 0

    idx = provider._client._indexes[provider._index_name(spec)]

    class _Resp:
        matches = [
            {"id": "m1", "score": 0.7, "metadata": {"k": "v"}, "values": [0.3, 0.4]},
            {"score": 0.1},
        ]

    idx.query = lambda **kwargs: _Resp()  # type: ignore[method-assign]
    matches = asyncio.run(
        provider.query(
            scope,
            spec,
            Query(
                vector=[0.1, 0.2],
                top_k=2,
                filter=None,
                include_metadata=True,
                include_vectors=False,
            ),
        )
    )
    assert len(matches) == 1
    assert matches[0].id == "m1"
    assert matches[0].metadata == {"k": "v"}
    assert matches[0].vector is None

    info = asyncio.run(provider.info())
    assert info.name == "pinecone-serverless"
