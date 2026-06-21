import asyncio
import sys
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.storage.errors import MigrationError
import democrai.core.infrastructure.storage.observability.migrations_handler as obs_migrations_mod
from democrai.core.infrastructure.storage.vector.base import Capability
from democrai.core.infrastructure.storage.vector.base import IndexSpec
from democrai.core.infrastructure.storage.vector.base import Match
from democrai.core.infrastructure.storage.vector.base import Metric
from democrai.core.infrastructure.storage.vector.base import ProviderInfo
from democrai.core.infrastructure.storage.vector.base import Query
from democrai.core.infrastructure.storage.vector.base import UserScope
from democrai.core.infrastructure.storage.vector.base import VectorDoc
from democrai.core.infrastructure.storage.vector.base import VectorStoreError
from democrai.core.infrastructure.storage.vector.composite import CompositeVectorStore
from democrai.core.infrastructure.storage.vector.composite import ReadPolicy
from democrai.core.infrastructure.storage.vector.composite import WritePolicy
import democrai.core.infrastructure.storage.vector.migrations_handler as vector_migrations_mod


class _Provider:
    def __init__(
        self,
        *,
        name="demo",
        fail_upsert=False,
        fail_query=False,
        fail_delete=False,
    ):
        self.name = name
        self.fail_upsert = fail_upsert
        self.fail_query = fail_query
        self.fail_delete = fail_delete
        self.calls = []

    async def info(self):
        self.calls.append("info")
        return ProviderInfo(name=self.name, version="1", capabilities=Capability.USER_SCOPED)

    async def ensure_index(self, spec):
        self.calls.append(("ensure", spec.name))

    async def drop_index(self, spec):
        self.calls.append(("drop", spec.name))

    async def upsert(self, scope, spec, docs):
        self.calls.append(("upsert", len(docs)))
        if self.fail_upsert:
            raise RuntimeError("upsert failed")

    async def delete_ids(self, scope, spec, ids):
        self.calls.append(("delete_ids", tuple(ids)))
        if self.fail_delete:
            raise RuntimeError("delete ids failed")
        return len(ids)

    async def delete_by_filter(self, scope, spec, flt):
        self.calls.append(("delete_filter", flt))
        if self.fail_delete:
            raise RuntimeError("delete filter failed")
        return 3

    async def query(self, scope, spec, q):
        self.calls.append(("query", q.top_k))
        if self.fail_query:
            raise RuntimeError("query failed")
        return [Match(id="m1", score=0.9)]

    async def rebuild(self, spec):
        self.calls.append(("rebuild", spec.name))


def test_composite_vector_store_covers_read_write_policies(monkeypatch: pytest.MonkeyPatch):
    logger_calls = []
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.vector.composite.app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(debug=lambda message: logger_calls.append(message))),
    )

    scope = UserScope(user_id="u1", organization_id="org-1")
    spec = IndexSpec(tenant_id="t1", app_id="a1", name="docs", dim=3, metric=Metric.COSINE)
    docs = [VectorDoc(id="d1", vector=[0.1, 0.2, 0.3])]
    query = Query(vector=[0.1, 0.2, 0.3], top_k=2)

    primary = _Provider()
    secondary = _Provider()
    store = CompositeVectorStore(primary, secondary)

    assert asyncio.run(store.info()).name == "demo"
    asyncio.run(store.ensure_index(spec))
    asyncio.run(store.drop_index(spec))
    asyncio.run(store.upsert(scope, spec, docs))
    assert asyncio.run(store.delete_ids(scope, spec, ["a", "b"])) == 2
    assert asyncio.run(store.delete_by_filter(scope, spec, {"x": 1})) == 3
    assert asyncio.run(store.query(scope, spec, query))[0].id == "m1"
    asyncio.run(store.rebuild(spec))

    assert ("ensure", "docs") in primary.calls
    assert ("drop", "docs") in secondary.calls
    assert ("upsert", 1) in secondary.calls
    assert ("rebuild", "docs") in secondary.calls

    primary_only = CompositeVectorStore(primary, secondary, write_policy=WritePolicy.PRIMARY_ONLY)
    asyncio.run(primary_only.upsert(scope, spec, docs))
    secondary_only = CompositeVectorStore(primary, secondary, write_policy=WritePolicy.SECONDARY_ONLY)
    asyncio.run(secondary_only.upsert(scope, spec, docs))

    primary_policy = _Provider()
    secondary_policy = _Provider()
    primary_only = CompositeVectorStore(
        primary_policy,
        secondary_policy,
        write_policy=WritePolicy.PRIMARY_ONLY,
    )
    asyncio.run(primary_only.ensure_index(spec))
    asyncio.run(primary_only.drop_index(spec))
    assert asyncio.run(primary_only.delete_ids(scope, spec, ["p"])) == 1
    assert asyncio.run(primary_only.delete_by_filter(scope, spec, {"p": 1})) == 3
    assert primary_policy.calls == [
        ("ensure", "docs"),
        ("drop", "docs"),
        ("delete_ids", ("p",)),
        ("delete_filter", {"p": 1}),
    ]
    assert secondary_policy.calls == []

    primary_policy = _Provider()
    secondary_policy = _Provider()
    secondary_only = CompositeVectorStore(
        primary_policy,
        secondary_policy,
        write_policy=WritePolicy.SECONDARY_ONLY,
        read_policy=ReadPolicy.STRICT_SECONDARY,
    )
    secondary_policy.name = "secondary"
    assert asyncio.run(secondary_only.info()).name == "secondary"
    asyncio.run(secondary_only.ensure_index(spec))
    asyncio.run(secondary_only.drop_index(spec))
    assert asyncio.run(secondary_only.delete_ids(scope, spec, ["s"])) == 1
    assert asyncio.run(secondary_only.delete_by_filter(scope, spec, {"s": 1})) == 3
    assert primary_policy.calls == []
    assert secondary_policy.calls == [
        "info",
        ("ensure", "docs"),
        ("drop", "docs"),
        ("delete_ids", ("s",)),
        ("delete_filter", {"s": 1}),
    ]

    primary_policy = _Provider()
    secondary_policy = _Provider()
    secondary_rebuild = CompositeVectorStore(
        primary_policy,
        secondary_policy,
        write_policy=WritePolicy.SECONDARY_ONLY,
    )
    asyncio.run(secondary_rebuild.rebuild(spec))
    assert primary_policy.calls == []
    assert secondary_policy.calls == [("rebuild", "docs")]

    fail_primary = _Provider(fail_query=True)
    prefer_secondary = CompositeVectorStore(fail_primary, secondary, read_policy=ReadPolicy.PREFER_PRIMARY)
    assert asyncio.run(prefer_secondary.query(scope, spec, query))[0].id == "m1"

    fail_secondary = _Provider(fail_query=True)
    prefer_primary = CompositeVectorStore(primary, fail_secondary, read_policy=ReadPolicy.PREFER_SECONDARY)
    assert asyncio.run(prefer_primary.query(scope, spec, query))[0].id == "m1"

    with pytest.raises(RuntimeError):
        asyncio.run(
            CompositeVectorStore(_Provider(fail_query=True), secondary, read_policy=ReadPolicy.STRICT_PRIMARY).query(
                scope, spec, query
            )
        )
    with pytest.raises(RuntimeError):
        asyncio.run(
            CompositeVectorStore(primary, _Provider(fail_query=True), read_policy=ReadPolicy.STRICT_SECONDARY).query(
                scope, spec, query
            )
        )

    with pytest.raises(VectorStoreError, match="Dual-write upsert failed"):
        asyncio.run(
            CompositeVectorStore(_Provider(fail_upsert=True), _Provider(fail_upsert=True)).upsert(scope, spec, docs)
        )
    with pytest.raises(VectorStoreError, match="Primary failed"):
        asyncio.run(
            CompositeVectorStore(_Provider(fail_upsert=True), secondary).upsert(scope, spec, docs)
        )
    with pytest.raises(VectorStoreError, match="Secondary failed"):
        asyncio.run(
            CompositeVectorStore(primary, _Provider(fail_upsert=True)).upsert(scope, spec, docs)
        )

    with pytest.raises(VectorStoreError, match="Dual-write delete_ids failed"):
        asyncio.run(
            CompositeVectorStore(primary, _Provider(fail_delete=True)).delete_ids(
                scope,
                spec,
                ["x"],
            )
        )
    with pytest.raises(VectorStoreError, match="Primary failed"):
        asyncio.run(
            CompositeVectorStore(_Provider(fail_delete=True), secondary).delete_ids(
                scope,
                spec,
                ["x"],
            )
        )
    assert ("delete_ids", ("x",)) in secondary.calls
    with pytest.raises(VectorStoreError, match="Dual-write delete_by_filter failed"):
        asyncio.run(
            CompositeVectorStore(primary, _Provider(fail_delete=True)).delete_by_filter(
                scope,
                spec,
                {"x": 1},
            )
        )
    with pytest.raises(VectorStoreError, match="Primary failed"):
        asyncio.run(
            CompositeVectorStore(_Provider(fail_delete=True), secondary).delete_by_filter(
                scope,
                spec,
                {"x": 1},
            )
        )
    assert ("delete_filter", {"x": 1}) in secondary.calls
    assert logger_calls


@pytest.mark.posix_only
def test_vector_and_observability_migrations_handlers(monkeypatch: pytest.MonkeyPatch, tmp_path):
    logger = SimpleNamespace(info=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)

    vector_ctx = SimpleNamespace(logger=logger)
    monkeypatch.setattr(vector_migrations_mod, "app_ctx", lambda: vector_ctx)
    monkeypatch.setattr(vector_migrations_mod, "get_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr("democrai.core.runtime.foundation.paths.get_data_dir", lambda: str(tmp_path / "data"))

    config_calls = {}

    class _Config:
        def __init__(self, path):
            config_calls["ini_path"] = path
            self.attributes = {}

        def set_main_option(self, key, value):
            config_calls.setdefault("options", {})[key] = value

    monkeypatch.setattr(vector_migrations_mod, "Config", _Config)
    monkeypatch.setattr(vector_migrations_mod.command, "upgrade", lambda cfg, target: config_calls.setdefault("upgrade", target))
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.vector.models.Base",
        SimpleNamespace(metadata="vector-metadata"),
    )

    vector_migrations_mod.run_vector_migrations()
    assert config_calls["options"]["script_location"].endswith("core/infrastructure/storage/vector/migrations")
    assert config_calls["options"]["sqlalchemy.url"].endswith("vector.db")
    assert config_calls["upgrade"] == "head"

    monkeypatch.setattr(
        vector_migrations_mod.command,
        "upgrade",
        lambda cfg, target: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(MigrationError, match="Vector migrations failed"):
        vector_migrations_mod.run_vector_migrations()

    obs_ctx = SimpleNamespace(
        logger=logger,
        config={
            "storage.observability.type": "sqlite",
            "storage.observability.url": None,
        },
    )
    monkeypatch.setattr(obs_migrations_mod, "app_ctx", lambda: obs_ctx)
    monkeypatch.setattr(obs_migrations_mod, "Config", _Config)
    monkeypatch.setattr(obs_migrations_mod.command, "upgrade", lambda cfg, target: config_calls.setdefault("obs_upgrade", target))
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.observability.models.Base",
        SimpleNamespace(metadata="obs-metadata"),
    )
    monkeypatch.setattr("democrai.core.runtime.foundation.paths.get_data_dir", lambda: str(tmp_path / "obs-data"))

    obs_migrations_mod.run_obs_migrations()
    assert config_calls["obs_upgrade"] == "head"

    class _ClickHouseStorage:
        def __init__(self, url):
            self.url = url

        def run_migrations(self):
            config_calls["clickhouse"] = self.url

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.storage.observability.providers.clickhouse",
        SimpleNamespace(ClickHouseObsStorage=_ClickHouseStorage),
    )
    obs_ctx.config["storage.observability.type"] = "clickhouse"
    obs_ctx.config["storage.observability.url"] = "clickhouse://demo"
    obs_migrations_mod.run_obs_migrations()
    assert config_calls["clickhouse"] == "clickhouse://demo"

    class _BrokenClickHouseStorage(_ClickHouseStorage):
        def run_migrations(self):
            raise RuntimeError("broken")

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.storage.observability.providers.clickhouse",
        SimpleNamespace(ClickHouseObsStorage=_BrokenClickHouseStorage),
    )
    with pytest.raises(MigrationError, match="Observability migrations failed"):
        obs_migrations_mod.run_obs_migrations()

    # non-clickhouse with explicit URL + upgrade failure branch
    obs_ctx.config["storage.observability.type"] = "sqlite"
    obs_ctx.config["storage.observability.url"] = "sqlite:////tmp/obs-explicit.db"
    monkeypatch.setattr(
        obs_migrations_mod.command,
        "upgrade",
        lambda cfg, target: (_ for _ in ()).throw(RuntimeError("obs-upgrade-fail")),
    )
    with pytest.raises(MigrationError, match="Observability migrations failed"):
        obs_migrations_mod.run_obs_migrations()
