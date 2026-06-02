from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_persistence_provider_base_abstract_contract():
    mod = importlib.import_module("democrai.core.infrastructure.database.providers.base")

    class _Impl(mod.PersistenceProvider):
        def get_session(self):
            return "s"

        def run_migrations(self) -> None:
            return None

        def get_url(self) -> str:
            return "u"

    impl = _Impl()
    assert impl.get_session() == "s"
    assert impl.get_url() == "u"

    class _Missing(mod.PersistenceProvider):
        pass

    with pytest.raises(TypeError):
        _Missing()

    class _Delegating(mod.PersistenceProvider):
        def get_session(self):
            return super().get_session()

        def run_migrations(self) -> None:
            return super().run_migrations()

        def get_url(self) -> str:
            return super().get_url()

    delegating = _Delegating()
    assert delegating.get_session() is None
    assert delegating.run_migrations() is None
    assert delegating.get_url() is None


def test_data_storage_provider_base_abstract_contract():
    mod = importlib.import_module("democrai.core.infrastructure.storage.data.providers.base")

    class _Impl(mod.DataStorageProvider):
        def get_session(self):
            return "s"

        def run_migrations(self) -> None:
            return None

    assert _Impl().get_session() == "s"

    class _Missing(mod.DataStorageProvider):
        pass

    with pytest.raises(TypeError):
        _Missing()

    class _Delegating(mod.DataStorageProvider):
        def get_session(self):
            return super().get_session()

        def run_migrations(self) -> None:
            return super().run_migrations()

    delegating = _Delegating()
    assert delegating.get_session() is None
    assert delegating.run_migrations() is None


def test_media_provider_base_abstract_contract():
    mod = importlib.import_module("democrai.core.infrastructure.storage.media.providers.base")

    class _Impl(mod.MediaProvider):
        def save(self, path: str, data: bytes) -> str:
            return path

        def load(self, path: str) -> bytes:
            return b"x"

        def get_path(self, path: str, *, destination_dir: str | None = None):
            return mod.MaterializedMedia(path=path)

        def delete(self, path: str) -> None:
            return None

        def exists(self, path: str) -> bool:
            return True

        def list(self, prefix: str = "") -> list[str]:
            return [prefix]

        def get_public_url(self, path: str) -> str:
            return "u:" + path

    impl = _Impl()
    assert impl.save("a", b"b") == "a"
    assert impl.exists("a") is True
    assert impl.get_public_url("a") == "u:a"

    class _Missing(mod.MediaProvider):
        pass

    with pytest.raises(TypeError):
        _Missing()

    class _Delegating(mod.MediaProvider):
        def save(self, path: str, data: bytes) -> str:
            return super().save(path, data)

        def load(self, path: str) -> bytes:
            return super().load(path)

        def get_path(self, path: str, *, destination_dir: str | None = None):
            return super().get_path(path, destination_dir=destination_dir)

        def delete(self, path: str) -> None:
            return super().delete(path)

        def exists(self, path: str) -> bool:
            return super().exists(path)

        def list(self, prefix: str = "") -> list[str]:
            return super().list(prefix)

        def get_public_url(self, path: str) -> str:
            return super().get_public_url(path)

    delegating = _Delegating()
    assert delegating.save("a", b"x") is None
    assert delegating.load("a") is None
    assert delegating.get_path("a") is None
    assert delegating.delete("a") is None
    assert delegating.exists("a") is None
    assert delegating.list("a") is None
    assert delegating.get_public_url("a") is None


def test_database_factory_paths(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.database.factory")
    assert mod._sqlite_db_path_from_url(None) is None
    assert mod._sqlite_db_path_from_url("postgres://x") is None
    assert mod._sqlite_db_path_from_url("sqlite:///  ") is None
    assert mod._sqlite_db_path_from_url("sqlite:///tmp/a.db") == "tmp/a.db"

    sqlite_calls = []
    postgres_calls = []
    monkeypatch.setattr(mod, "SqlitePersistenceProvider", lambda db_path=None: sqlite_calls.append(db_path) or ("sqlite", db_path))
    monkeypatch.setattr(mod, "PostgresPersistenceProvider", lambda db_url: postgres_calls.append(db_url) or ("postgres", db_url))

    assert mod.PersistenceProviderFactory.get_provider("sqlite", db_path="x.db") == ("sqlite", "x.db")
    assert mod.PersistenceProviderFactory.get_provider("sqlite", db_url="sqlite:///y.db") == ("sqlite", "y.db")
    assert mod.PersistenceProviderFactory.get_provider("postgres", db_url="postgres://x") == ("postgres", "postgres://x")
    with pytest.raises(Exception):
        mod.PersistenceProviderFactory.get_provider("postgres")
    with pytest.raises(Exception):
        mod.PersistenceProviderFactory.get_provider("unknown")
    assert sqlite_calls and postgres_calls


def test_data_storage_factory_paths(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.storage.data.factory")
    assert mod._sqlite_db_path_from_url(None) is None
    assert mod._sqlite_db_path_from_url("redis://x") is None
    assert mod._sqlite_db_path_from_url("sqlite:///") is None
    assert mod._sqlite_db_path_from_url("sqlite:///tmp/d.db") == "tmp/d.db"

    monkeypatch.setattr(mod, "SqliteDataStorage", lambda db_path=None: ("sqlite", db_path))
    monkeypatch.setattr(mod, "PostgresDataStorage", lambda db_url: ("postgres", db_url))
    monkeypatch.setattr(mod, "SupabaseDataStorage", lambda db_url: ("supabase", db_url))

    assert mod.DataStorageProviderFactory.get_provider("sqlite", db_path="x.db") == ("sqlite", "x.db")
    assert mod.DataStorageProviderFactory.get_provider("sqlite", db_url="sqlite:///y.db") == ("sqlite", "y.db")
    assert mod.DataStorageProviderFactory.get_provider("postgres", db_url="postgres://x") == ("postgres", "postgres://x")
    assert mod.DataStorageProviderFactory.get_provider("supabase", db_url="postgres://s") == ("supabase", "postgres://s")
    with pytest.raises(Exception):
        mod.DataStorageProviderFactory.get_provider("postgres")
    with pytest.raises(Exception):
        mod.DataStorageProviderFactory.get_provider("supabase")
    with pytest.raises(Exception):
        mod.DataStorageProviderFactory.get_provider("unknown")


def test_media_factory_paths(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.storage.media.factory")
    monkeypatch.setattr(mod, "LocalMediaProvider", lambda base_dir=None: ("local", base_dir))
    monkeypatch.setattr(mod, "S3MediaProvider", lambda *a, **k: ("s3", a, k))

    assert mod.MediaProviderFactory.get_provider("local", base_dir="/tmp") == ("local", "/tmp")

    out = mod.MediaProviderFactory.get_provider(
        "s3",
        bucket_name="b",
        region="eu-west-1",
        access_key="ak",
        secret_key="sk",
        endpoint_url="http://e",
        public_base_url="http://p",
        key_prefix="k",
        session_token="t",
        use_path_style="1",
    )
    assert out[0] == "s3"
    assert out[2]["use_path_style"] is True
    with pytest.raises(Exception):
        mod.MediaProviderFactory.get_provider("s3")
    with pytest.raises(Exception):
        mod.MediaProviderFactory.get_provider("unknown")


def test_session_memory_provider_and_factory_branches(monkeypatch):
    mem_mod = importlib.import_module("democrai.core.infrastructure.session.providers.memory")
    store = mem_mod.MemoryJsonStore()
    assert store.load("k") is None
    store.save("k", {"x": 1})
    loaded = store.load("k")
    assert loaded == {"x": 1}
    loaded["x"] = 2
    assert store.load("k") == {"x": 1}
    store.delete("k")
    store.delete("missing")
    assert store.keys() == []

    mod = importlib.import_module("democrai.core.infrastructure.session.factory")

    # setup mode branch
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(setup_mode=True, config=None))
    providers = mod.SessionProviderFactory.create()
    assert isinstance(providers.identity, mem_mod.MemoryJsonStore)

    # normal config branches
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.database.models",
        SimpleNamespace(SessionIdentity=object, SessionUiState=object),
    )
    fake_cfg = SimpleNamespace(
        get=lambda key, default=None: {
            "session.identity.provider": "sqlite",
            "session.ui_state.provider": "postgres",
            "session.cache.provider": "redis",
            "session.redis.url": "redis://r",
            "session.cache.ttl_seconds": "30",
            "session.ui_state.url": "postgres://u",
            "session.identity.url": None,
        }.get(key, default)
    )
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False, config=fake_cfg))
    monkeypatch.setattr(mod, "SqlAlchemyJsonStore", lambda model: ("sqlite", model))
    monkeypatch.setattr(mod, "SqlUrlJsonStore", lambda url, table_name=None: ("sql", url, table_name))
    monkeypatch.setattr(mod, "RedisJsonStore", lambda url, prefix=None, ttl_seconds=None: ("redis", url, prefix, ttl_seconds))
    monkeypatch.setattr(mod, "MemoryJsonStore", lambda: ("memory",))

    providers2 = mod.SessionProviderFactory.create()
    assert providers2.identity[0] == "sqlite"
    assert providers2.ui_state[0] == "sql"
    assert providers2.cache[0] == "redis"

    # _build_provider branches
    assert mod.SessionProviderFactory._build_provider("memory", sqlite_model=None, sql_url=None, redis_url="r", redis_prefix="p")[0] == "memory"
    assert mod.SessionProviderFactory._build_provider("sqlite", sqlite_model=None, sql_url=None, redis_url="r", redis_prefix="p")[0] == "memory"
    assert mod.SessionProviderFactory._build_provider("sqlite", sqlite_model=object, sql_url=None, redis_url="r", redis_prefix="p")[0] == "sqlite"
    with pytest.raises(ValueError):
        mod.SessionProviderFactory._build_provider("postgres", sqlite_model=object, sql_url=None, redis_url="r", redis_prefix="p")
    assert mod.SessionProviderFactory._build_provider("postgres", sqlite_model=object, sql_url="postgres://x", redis_url="r", redis_prefix="p")[0] == "sql"
    assert mod.SessionProviderFactory._build_provider("redis", sqlite_model=object, sql_url=None, redis_url="redis://x", redis_prefix="p", ttl_seconds=11)[0] == "redis"
    with pytest.raises(ValueError):
        mod.SessionProviderFactory._build_provider("unknown", sqlite_model=object, sql_url=None, redis_url="r", redis_prefix="p")


def test_supabase_provider_init(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.storage.data.providers.supabase")
    calls = []
    monkeypatch.setattr(mod.PostgresDataStorage, "__init__", lambda self, connection_url: calls.append(connection_url))
    obj = mod.SupabaseDataStorage("postgres://x")
    assert isinstance(obj, mod.SupabaseDataStorage)
    assert calls == ["postgres://x"]
