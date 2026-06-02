from __future__ import annotations

from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.storage.errors import (
    MigrationError,
    ProviderConfigError,
    ProviderNotAvailableError,
    StorageError,
)


def test_error_hierarchy():
    assert issubclass(ProviderConfigError, StorageError)
    assert issubclass(ProviderNotAvailableError, StorageError)
    assert issubclass(MigrationError, StorageError)


def test_data_factory_all_branches(monkeypatch: pytest.MonkeyPatch):
    from democrai.core.infrastructure.storage.data import factory as mod

    monkeypatch.setattr(mod, "SqliteDataStorage", lambda db_path=None: ("sqlite", db_path))
    monkeypatch.setattr(mod, "PostgresDataStorage", lambda db_url: ("postgres", db_url))
    monkeypatch.setattr(mod, "SupabaseDataStorage", lambda db_url: ("supabase", db_url))

    assert mod.DataStorageProviderFactory.get_provider("sqlite", db_path="x.db") == (
        "sqlite",
        "x.db",
    )
    assert mod.DataStorageProviderFactory.get_provider(
        "postgres", db_url="postgresql://u:p@h/db"
    ) == ("postgres", "postgresql://u:p@h/db")
    assert mod.DataStorageProviderFactory.get_provider(
        "supabase", db_url="postgresql://postgres.ref:pw@pooler.supabase.com:6543/postgres"
    ) == ("supabase", "postgresql://postgres.ref:pw@pooler.supabase.com:6543/postgres")

    with pytest.raises(ProviderConfigError):
        mod.DataStorageProviderFactory.get_provider("postgres")
    with pytest.raises(ProviderConfigError):
        mod.DataStorageProviderFactory.get_provider("supabase")
    with pytest.raises(ProviderConfigError):
        mod.DataStorageProviderFactory.get_provider("unknown")


def test_observability_factory_all_branches(monkeypatch: pytest.MonkeyPatch):
    from democrai.core.infrastructure.storage.observability import factory as mod

    monkeypatch.setattr(mod, "SqliteObsStorage", lambda db_path=None: ("sqlite", db_path))
    monkeypatch.setattr(mod, "PostgresObsStorage", lambda url: ("postgres", url))
    monkeypatch.setattr(mod, "ClickHouseObsStorage", lambda url: ("clickhouse", url))
    monkeypatch.setattr(
        mod,
        "ObservabilityStore",
        lambda provider=None, exporters=None: ("store", provider, exporters or []),
    )
    monkeypatch.setattr(
        mod,
        "OtlpObsExporter",
        lambda endpoint, insecure=False, service_name="democrai": (
            "otlp",
            endpoint,
            insecure,
            service_name,
        ),
    )

    assert mod.ObservabilityFactory.get_provider("sqlite", db_path="obs.db") == (
        "store",
        ("sqlite", "obs.db"),
        [],
    )
    assert mod.ObservabilityFactory.get_provider(
        "postgres", connection_url="postgresql://u:p@h/db"
    ) == ("store", ("postgres", "postgresql://u:p@h/db"), [])
    assert mod.ObservabilityFactory.get_provider(
        "clickhouse", connection_url="clickhouse://default@localhost:8123/obs"
    ) == (
        "store",
        ("clickhouse", "clickhouse://default@localhost:8123/obs"),
        [],
    )
    assert mod.ObservabilityFactory.get_provider(
        "sqlite",
        db_path="obs.db",
        otlp_enabled=True,
        otlp_endpoint="http://collector:4318/v1/traces",
        otlp_insecure=True,
        otlp_service_name="democrai-test",
    ) == (
        "store",
        ("sqlite", "obs.db"),
        [("otlp", "http://collector:4318/v1/traces", True, "democrai-test")],
    )

    with pytest.raises(ProviderConfigError):
        mod.ObservabilityFactory.get_provider("postgres")
    with pytest.raises(ProviderConfigError):
        mod.ObservabilityFactory.get_provider("clickhouse")
    with pytest.raises(ProviderConfigError):
        mod.ObservabilityFactory.get_provider("sqlite", otlp_enabled=True)
    with pytest.raises(ProviderConfigError):
        mod.ObservabilityFactory.get_provider("unknown")
    assert mod.ObservabilityFactory.get_provider(
        "sqlite",
        db_path="obs.db",
        otlp_enabled="YES",
        otlp_endpoint="http://collector:4318/v1/traces",
        otlp_insecure="off",
    ) == (
        "store",
        ("sqlite", "obs.db"),
        [("otlp", "http://collector:4318/v1/traces", False, "democrai")],
    )
    assert mod.ObservabilityFactory.get_provider(
        "sqlite",
        db_path="obs.db",
        otlp_enabled="off",
        otlp_endpoint="http://collector:4318/v1/traces",
    ) == (
        "store",
        ("sqlite", "obs.db"),
        [],
    )


def test_media_factory_all_branches(monkeypatch: pytest.MonkeyPatch):
    from democrai.core.infrastructure.storage.media import factory as mod

    monkeypatch.setattr(mod, "LocalMediaProvider", lambda base_dir=None: ("local", base_dir))
    monkeypatch.setattr(
        mod,
        "S3MediaProvider",
        lambda bucket, region, ak, sk, **kwargs: ("s3", bucket, region, ak, sk, kwargs),
    )

    assert mod.MediaProviderFactory.get_provider("local", base_dir="/tmp/media") == (
        "local",
        "/tmp/media",
    )
    assert mod.MediaProviderFactory.get_provider(
        "s3",
        bucket_name="bucket",
        region="eu-central-1",
        access_key="ak",
        secret_key="sk",
    ) == ("s3", "bucket", "eu-central-1", "ak", "sk", {
        "endpoint_url": None,
        "public_base_url": None,
        "key_prefix": None,
        "session_token": None,
        "use_path_style": False,
    })

    with pytest.raises(ProviderConfigError):
        mod.MediaProviderFactory.get_provider("s3")
    with pytest.raises(ProviderConfigError):
        mod.MediaProviderFactory.get_provider("unknown")


def test_kg_factory_all_paths(monkeypatch: pytest.MonkeyPatch):
    from democrai.core.infrastructure.storage.kg import factory

    monkeypatch.setattr(factory, "LadybugKGStorage", lambda db_path=None: ("ladybug", db_path))
    monkeypatch.setattr(factory, "Neo4jKGStorage", lambda uri, user, password: ("neo4j", uri, user, password))
    monkeypatch.setattr(factory, "get_data_dir", lambda: "/tmp")

    assert factory.KGStoreFactory.get_provider("ladybug", db_path="kg.lbug") == (
        "ladybug",
        "kg.lbug",
    )
    assert factory.KGStoreFactory.get_provider(
        "neo4j", uri="bolt://localhost:7687", user="neo4j", password="pw"
    ) == ("neo4j", "bolt://localhost:7687", "neo4j", "pw")

    with pytest.raises(ProviderConfigError):
        factory.KGStoreFactory.get_provider("neo4j", uri="bolt://localhost:7687")
    with pytest.raises(ProviderConfigError):
        factory.KGStoreFactory.get_provider("unknown")

    # Backward-compatible alias
    assert factory.KGStoreFactory.get_store("ladybug", db_path="kg.lbug") == (
        "ladybug",
        "kg.lbug",
    )

    monkeypatch.setattr(factory, "get_preference", lambda key, default=None: {"kg_storage_type": "ladybug", "kg_storage_params": '{"db_path":"kg_pref.lbug"}'}.get(key, default))
    assert factory.KGStoreFactory.create_default() == ("ladybug", "kg_pref.lbug")

    monkeypatch.setattr(factory, "get_preference", lambda key, default=None: {"kg_storage_type": "ladybug", "kg_storage_params": "not-json"}.get(key, default))
    assert factory.KGStoreFactory.create_default() == ("ladybug", "/tmp/kg.lbug")


def test_vector_factory_all_paths(monkeypatch: pytest.MonkeyPatch):
    from democrai.core.infrastructure.storage.vector import factory as mod

    monkeypatch.setattr(mod, "get_data_dir", lambda: "/tmp")
    monkeypatch.setattr(
        mod,
        "SQLiteVecVectorProvider",
        lambda db_path, index_prefix="democrai": ("sqlite-vec", db_path, index_prefix),
    )
    monkeypatch.setattr(
        mod,
        "MilvusVectorProvider",
        lambda host, port, user, password, index_prefix="democrai": (
            "milvus",
            host,
            port,
            user,
            password,
            index_prefix,
        ),
    )
    monkeypatch.setattr(
        mod,
        "PineconeVectorProvider",
        lambda api_key, cloud="aws", region="us-east-1", index_prefix="democrai": (
            "pinecone",
            api_key,
            cloud,
            region,
            index_prefix,
        ),
    )
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(info=lambda *_args, **_kwargs: None)),
    )

    # unavailable sqlite-vec
    monkeypatch.setattr(mod, "sqlite_vec_available", lambda: (False, "missing"))
    with pytest.raises(ProviderNotAvailableError):
        mod.VectorStoreFactory.get_provider("sqlite-vec")

    # available sqlite-vec
    monkeypatch.setattr(mod, "sqlite_vec_available", lambda: (True, None))
    assert mod.VectorStoreFactory.get_provider("sqlite-vec", db_path="vec.db") == (
        "sqlite-vec",
        "vec.db",
        "democrai",
    )
    assert mod.VectorStoreFactory.get_provider(
        "milvus", host="h", port=19530, user="u", password="p"
    ) == ("milvus", "h", 19530, "u", "p", "democrai")
    assert mod.VectorStoreFactory.get_provider(
        "pinecone",
        api_key="pc-key",
        cloud="aws",
        region="eu-west-1",
        index_prefix="demo",
    ) == ("pinecone", "pc-key", "aws", "eu-west-1", "demo")
    with pytest.raises(ProviderConfigError):
        mod.VectorStoreFactory.get_provider("pinecone")

    with pytest.raises(ProviderConfigError):
        mod.VectorStoreFactory.get_provider("unknown")

    # composite
    composite = mod.VectorStoreFactory.create_composite(
        {"type": "sqlite-vec", "params": {"db_path": "a.db"}},
        {"type": "milvus", "params": {"host": "mh", "port": 1, "user": "u", "password": "p"}},
    )
    assert isinstance(composite, mod.CompositeVectorStore)

    # create_default non-composite
    prefs = {
        "vector_storage_type": "sqlite-vec",
        "vector_storage_params": '{"db_path":"pref.db"}',
        "vector_storage_composite": "false",
    }
    monkeypatch.setattr(mod, "get_preference", lambda key, default=None: prefs.get(key, default))
    assert mod.VectorStoreFactory.create_default() == ("sqlite-vec", "pref.db", "democrai")

    # create_default composite
    prefs_comp = {
        "vector_storage_type": "sqlite-vec",
        "vector_storage_params": "{}",
        "vector_storage_composite": "true",
        "vector_storage_primary": '{"type":"sqlite-vec","params":{"db_path":"p.db"}}',
        "vector_storage_secondary": '{"type":"sqlite-vec","params":{"db_path":"s.db"}}',
    }
    monkeypatch.setattr(mod, "get_preference", lambda key, default=None: prefs_comp.get(key, default))
    comp = mod.VectorStoreFactory.create_default()
    assert isinstance(comp, mod.CompositeVectorStore)

    # invalid json params branch
    prefs_bad = {
        "vector_storage_type": "sqlite-vec",
        "vector_storage_params": "{bad",
        "vector_storage_composite": "false",
    }
    monkeypatch.setattr(mod, "get_preference", lambda key, default=None: prefs_bad.get(key, default))
    assert mod.VectorStoreFactory.create_default() == (
        "sqlite-vec",
        "/tmp/vector.db",
        "democrai",
    )
