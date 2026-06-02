from __future__ import annotations

import asyncio

from democrai.core.infrastructure.storage.vector.base import Capability
from democrai.core.infrastructure.storage.vector.base import Filter
from democrai.core.infrastructure.storage.vector.base import IndexSpec
from democrai.core.infrastructure.storage.vector.base import Metric
from democrai.core.infrastructure.storage.vector.base import Op
from democrai.core.infrastructure.storage.vector.base import Query
from democrai.core.infrastructure.storage.vector.base import UserScope
from democrai.core.infrastructure.storage.vector.base import VectorDoc
from democrai.core.infrastructure.storage.vector.sqlite_vec_store import _index_table_name
from democrai.core.infrastructure.storage.vector.sqlite_vec_store import SQLiteVecVectorProvider
from democrai.core.infrastructure.storage.vector.sqlite_vec_store import sqlite_vec_available


def _provider(tmp_path):
    ok, reason = sqlite_vec_available()
    assert ok, reason
    return SQLiteVecVectorProvider(str(tmp_path / "vector.db"))


def test_sqlite_vec_provider_uses_vec0_and_integer_scope(tmp_path):
    provider = _provider(tmp_path)
    spec = IndexSpec(tenant_id="t1", app_id="a1", name="docs", dim=2, metric=Metric.COSINE)

    asyncio.run(provider.ensure_index(spec))
    asyncio.run(
        provider.upsert(
            UserScope(user_id=1, organization_id=10),
            spec,
            [VectorDoc(id="doc-1", vector=[1.0, 0.0], metadata={"org": 10})],
        )
    )
    asyncio.run(
        provider.upsert(
            UserScope(user_id=1, organization_id=11),
            spec,
            [VectorDoc(id="doc-1", vector=[0.0, 1.0], metadata={"org": 11})],
        )
    )

    res_a = asyncio.run(
        provider.query(
            UserScope(user_id=1, organization_id=10),
            spec,
            Query(vector=[1.0, 0.0], top_k=5),
        )
    )
    res_b = asyncio.run(
        provider.query(
            UserScope(user_id=1, organization_id=11),
            spec,
            Query(vector=[0.0, 1.0], top_k=5),
        )
    )
    res_none = asyncio.run(
        provider.query(
            UserScope(user_id=1),
            spec,
            Query(vector=[1.0, 0.0], top_k=5),
        )
    )

    assert [match.metadata["org"] for match in res_a] == [10]
    assert [match.metadata["org"] for match in res_b] == [11]
    assert res_none == []


def test_sqlite_vec_provider_upsert_filters_delete_and_capabilities(tmp_path):
    provider = _provider(tmp_path)
    spec = IndexSpec(tenant_id="t1", app_id="a1", name="docs", dim=2, metric=Metric.L2)
    scope = UserScope(user_id=1, organization_id=10)

    info = asyncio.run(provider.info())
    assert info.name == "sqlite-vec-embedded"
    assert info.capabilities & Capability.UPSERT_IDEMPOTENT
    assert info.capabilities & Capability.RETURN_VECTORS
    assert info.capabilities & Capability.FILTER_IN
    assert info.capabilities & Capability.FILTER_RANGE

    asyncio.run(provider.ensure_index(spec))
    asyncio.run(
        provider.upsert(
            scope,
            spec,
            [
                VectorDoc(id="near", vector=[0.0, 0.0], metadata={"kind": "keep", "rank": 1}),
                VectorDoc(id="far", vector=[10.0, 0.0], metadata={"kind": "drop", "rank": 3}),
            ],
        )
    )
    asyncio.run(
        provider.upsert(
            scope,
            spec,
            [VectorDoc(id="far", vector=[0.1, 0.0], metadata={"kind": "keep", "rank": 2})],
        )
    )

    matches = asyncio.run(
        provider.query(
            scope,
            spec,
            Query(
                vector=[0.0, 0.0],
                top_k=2,
                filter=Filter.AND(
                    Filter.p("rank", Op.GTE, 1),
                    Filter.OR(
                        Filter.p("kind", Op.EQ, "keep"),
                        Filter.p("kind", Op.IN, ["fallback"]),
                    ),
                ),
                include_vectors=True,
            ),
        )
    )

    assert [match.id for match in matches] == ["near", "far"]
    assert matches[0].score == 1.0
    assert matches[0].vector == [0.0, 0.0]

    removed = asyncio.run(provider.delete_by_filter(scope, spec, Filter.p("rank", Op.GT, 1)))
    assert removed == 1
    assert asyncio.run(provider.delete_ids(scope, spec, [])) == 0
    assert asyncio.run(provider.delete_ids(scope, spec, ["near"])) == 1
    assert asyncio.run(provider.query(scope, spec, Query(vector=[0.0, 0.0], top_k=5))) == []

    asyncio.run(provider.rebuild(spec))
    asyncio.run(provider.drop_index(spec))


def test_sqlite_vec_index_table_name_uses_index_prefix():
    spec = IndexSpec(tenant_id="t1", app_id="a1", name="docs", dim=2, metric=Metric.COSINE)

    default_name = _index_table_name(spec)
    prefixed_name = _index_table_name(spec, "custom")

    assert default_name != prefixed_name
    assert default_name.startswith("vec")
    assert prefixed_name.startswith("vec")
