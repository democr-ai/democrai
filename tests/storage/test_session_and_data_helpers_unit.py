from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine as sa_create_engine

sys.modules.setdefault("redis", types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=lambda *args, **kwargs: None)))

import democrai.core.infrastructure.session.providers.redis as session_redis_mod
import democrai.core.infrastructure.session.providers.sql_url as sql_url_mod
import democrai.core.infrastructure.session.providers.sqlalchemy_store as sqlalchemy_store_mod
import democrai.core.infrastructure.storage.data.database as data_db_mod
import democrai.core.infrastructure.storage.data.migrations_handler as data_migrations_mod
import democrai.core.infrastructure.storage.data.providers.base as data_base_mod
import democrai.core.infrastructure.storage.data.providers.postgres as data_postgres_mod
import democrai.core.infrastructure.storage.data.providers.sqlite as data_sqlite_mod
import democrai.core.infrastructure.storage.data.store as data_store_mod


class _Logger:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.warnings = []

    def info(self, message, *args, **kwargs):
        self.infos.append(message)

    def error(self, message, *args, **kwargs):
        self.errors.append(message)

    def warning(self, message, *args, **kwargs):
        self.warnings.append((message, args, kwargs))


class _FakeRedis:
    def __init__(self):
        self.values = {}
        self.deleted = []
        self.last_set = None
        self.last_setex = None

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.last_set = (key, value)
        self.values[key] = value

    def setex(self, key, ttl, value):
        self.last_setex = (key, ttl, value)
        self.values[key] = value

    def delete(self, key):
        self.deleted.append(key)

    def keys(self, pattern):
        return [k for k in self.values if k.startswith(pattern[:-1])]


class _Query:
    def __init__(self, row=None):
        self.row = row
        self.deleted = False

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.row

    def all(self):
        return [] if self.row is None else [self.row]

    def delete(self):
        self.deleted = True


class _Db:
    def __init__(self, row=None, fail_commit=False):
        self.row = row
        self.fail_commit = fail_commit
        self.closed = False
        self.added = []
        self.rolled_back = False
        self.committed = 0
        self.refreshed = []
        self.deleted = []

    def query(self, model):
        return _Query(self.row)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.committed += 1
        if self.fail_commit:
            raise RuntimeError("commit fail")

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def refresh(self, row):
        self.refreshed.append(row)

    def delete(self, row):
        self.deleted.append(row)


class _Model:
    session_key = "session_key"

    def __init__(self, session_key=None, data=None, id=None):
        self.session_key = session_key
        self.data = data
        self.id = id


def test_redis_json_store_load_save_delete(monkeypatch):
    fake = _FakeRedis()
    sys.modules["redis"].Redis = SimpleNamespace(
        from_url=lambda url, decode_responses=True: fake
    )
    store = session_redis_mod.RedisJsonStore("redis://main", "sess")
    assert store._key("abc") == "sess:abc"
    assert store.load("missing") is None

    fake.values["sess:abc"] = json.dumps({"ok": 1})
    assert store.load("abc") == {"ok": 1}
    fake.values["sess:scalar"] = json.dumps("x")
    assert store.load("scalar") is None

    store.save("abc", {"value": 1})
    assert fake.last_set[0] == "sess:abc"
    ttl_store = session_redis_mod.RedisJsonStore("redis://main", "sess", ttl_seconds=30)
    ttl_store.save("abc", {"value": 2})
    assert fake.last_setex[1] == 30
    ttl_store.delete("abc")
    assert fake.deleted == ["sess:abc"]
    fake.values["sess:k1"] = "{}"
    fake.values["sess:k2"] = "{}"
    assert sorted(ttl_store.keys()) == ["abc", "k1", "k2", "scalar"]


@pytest.mark.posix_only
def test_sqlalchemy_json_store_and_data_db_helpers(monkeypatch):
    row = _Model("k1", json.dumps({"ok": True}))
    db = _Db(row=row)
    monkeypatch.setattr(sqlalchemy_store_mod, "app_ctx", lambda: SimpleNamespace(db=SimpleNamespace(get_session=lambda: db)))
    store = sqlalchemy_store_mod.SqlAlchemyJsonStore(_Model)
    assert store.load("k1") == {"ok": True}
    assert db.closed is True

    db = _Db(row=None)
    monkeypatch.setattr(sqlalchemy_store_mod, "app_ctx", lambda: SimpleNamespace(db=SimpleNamespace(get_session=lambda: db)))
    store = sqlalchemy_store_mod.SqlAlchemyJsonStore(_Model)
    store.save("k2", {"x": 1})
    assert db.added and db.committed == 1 and db.closed is True

    row2 = _Model("k2", json.dumps({"x": 1}))
    db = _Db(row=row2)
    monkeypatch.setattr(sqlalchemy_store_mod, "app_ctx", lambda: SimpleNamespace(db=SimpleNamespace(get_session=lambda: db)))
    store = sqlalchemy_store_mod.SqlAlchemyJsonStore(_Model)
    store.save("k2", {"x": 2})
    assert json.loads(row2.data) == {"x": 2}

    db = _Db(row=row2, fail_commit=True)
    monkeypatch.setattr(sqlalchemy_store_mod, "app_ctx", lambda: SimpleNamespace(db=SimpleNamespace(get_session=lambda: db)))
    with pytest.raises(RuntimeError):
        store.save("k2", {"x": 3})
    assert db.rolled_back is True

    db = _Db(row=row2, fail_commit=True)
    monkeypatch.setattr(sqlalchemy_store_mod, "app_ctx", lambda: SimpleNamespace(db=SimpleNamespace(get_session=lambda: db)))
    with pytest.raises(RuntimeError):
        store.delete("k2")
    assert db.rolled_back is True

    data_db_mod._engine = None
    data_db_mod._SessionLocal = None
    monkeypatch.setattr(data_db_mod, "app_ctx", lambda: SimpleNamespace(config=SimpleNamespace(get=lambda key: {"database.data_url": "postgresql://db"}.get(key))))
    assert data_db_mod.get_database_url() == "postgresql://db"

    monkeypatch.setattr(data_db_mod, "app_ctx", lambda: SimpleNamespace(config=None))
    monkeypatch.setattr(data_db_mod, "get_data_dir", lambda: "/tmp/data")
    monkeypatch.setenv("DEMOCRAI_DATA_URL", "sqlite:///env-data.db")
    assert data_db_mod.get_database_url() == "sqlite:///env-data.db"

    created = {}
    monkeypatch.delenv("DEMOCRAI_DATA_URL", raising=False)
    monkeypatch.setattr(
        data_db_mod,
        "create_engine",
        lambda url, connect_args=None: created.setdefault("engine", SimpleNamespace(url=url, connect_args=connect_args)),
    )
    monkeypatch.setattr(data_db_mod, "install_sqlite_engine_pragmas", lambda engine: created.setdefault("engine_pragmas", engine))
    monkeypatch.setattr(data_db_mod, "sessionmaker", lambda **kwargs: (lambda: _Db()))
    monkeypatch.setattr(data_db_mod, "scoped_session", lambda factory: factory)
    session_factory = data_db_mod._get_lazy_session()
    assert created["engine"].url == "sqlite:////tmp/data/data.db"
    assert created["engine"].connect_args == {"check_same_thread": False, "timeout": 5.0}
    assert created["engine_pragmas"] is created["engine"]
    db_session = session_factory()
    gen = data_db_mod.get_data_db()
    yielded = next(gen)
    assert isinstance(yielded, _Db)
    try:
        next(gen)
    except StopIteration:
        pass


@pytest.mark.posix_only
def test_data_storage_providers_and_data_store_scopes(monkeypatch):
    with pytest.raises(TypeError):
        data_base_mod.DataStorageProvider()

    created = {}
    monkeypatch.setattr(data_postgres_mod, "create_engine", lambda url, pool_pre_ping=True: created.setdefault("pg_engine", url))
    monkeypatch.setattr(data_postgres_mod, "sessionmaker", lambda **kwargs: (lambda: "pg-session"))
    monkeypatch.setattr(data_postgres_mod, "scoped_session", lambda factory: factory)
    provider = data_postgres_mod.PostgresDataStorage("postgresql://db")
    assert provider.get_session() == "pg-session"
    monkeypatch.setattr("democrai.core.infrastructure.storage.data.mixins.Base", SimpleNamespace(metadata=SimpleNamespace(create_all=lambda bind: created.setdefault("pg_bind", bind))))
    provider.run_migrations()
    assert created["pg_bind"] == "postgresql://db"

    monkeypatch.setattr(data_sqlite_mod, "get_data_dir", lambda: "/tmp/data")
    monkeypatch.setattr(
        data_sqlite_mod,
        "create_engine",
        lambda url, connect_args=None: created.setdefault("sqlite_engine", SimpleNamespace(url=url, connect_args=connect_args)),
    )
    monkeypatch.setattr(data_sqlite_mod, "install_sqlite_engine_pragmas", lambda engine: created.setdefault("sqlite_pragmas", engine))
    monkeypatch.setattr(data_sqlite_mod, "sessionmaker", lambda **kwargs: (lambda: "sqlite-session"))
    monkeypatch.setattr(data_sqlite_mod, "scoped_session", lambda factory: factory)
    sqlite_provider = data_sqlite_mod.SqliteDataStorage()
    assert sqlite_provider.get_session() == "sqlite-session"
    sqlite_provider.run_migrations()
    assert created["sqlite_engine"].url == "sqlite:////tmp/data/data.db"
    assert created["sqlite_engine"].connect_args == {"check_same_thread": False, "timeout": 5.0}
    assert created["sqlite_pragmas"] is created["sqlite_engine"]
    sqlite_provider_custom = data_sqlite_mod.SqliteDataStorage("/tmp/custom-data.db")
    assert sqlite_provider_custom.url == "sqlite:////tmp/custom-data.db"

    class _ScopedModel:
        id = "id"
        user_id = "user_id"
        organization_id = "organization_id"

        def __init__(self, id="1"):
            self.id = id
            self.user_id = None
            self.organization_id = None

    row = _ScopedModel("1")
    row.user_id = 1
    row.organization_id = 1
    db = _Db(row=row)
    logger = _Logger()
    monkeypatch.setattr(
        data_store_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            data_store=SimpleNamespace(get_session=lambda: db),
            logger=logger,
        ),
    )
    store = data_store_mod.DataStore(1, organization_id=1)
    created_row = store.add(_ScopedModel("2"))
    assert created_row.user_id == 1
    assert created_row.organization_id == 1
    assert store.get(_ScopedModel, "1") is row
    assert store.list(_ScopedModel, missing="x") == [row]
    assert store.update(_ScopedModel, "1", user_id=2) is row
    assert row.user_id == 1
    assert logger.warnings
    assert store.delete(_ScopedModel, "1") is True

    # _get_session fallback + list filter branch + delete false branch
    fallback_db = _Db(row=None)
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.storage.data.database",
        SimpleNamespace(_get_lazy_session=lambda: lambda: fallback_db),
    )
    monkeypatch.setattr(data_store_mod, "app_ctx", lambda: SimpleNamespace(data_store=None))
    store_fallback = data_store_mod.DataStore(1, organization_id=1)
    assert store_fallback._get_session() is fallback_db
    assert store_fallback.list(_ScopedModel, id="1") == []
    assert store_fallback.delete(_ScopedModel, "missing") is False


def test_data_store_apply_scope_and_update_missing(monkeypatch):
    class _Expr:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return (self.name, other)

    class _ScopedModel:
        id = _Expr("id")
        user_id = _Expr("user_id")
        organization_id = _Expr("organization_id")

    class _QueryObj:
        def __init__(self):
            self.filters = []

        def filter(self, criterion):
            self.filters.append(criterion)
            return self

        def first(self):
            return None

        def all(self):
            return []

    q = _QueryObj()
    store_super = data_store_mod.DataStore(1, organization_id=10, access_level=1)
    assert store_super._apply_scope(q, _ScopedModel) is q

    q_org = _QueryObj()
    store_org = data_store_mod.DataStore(1, organization_id=10, access_level=2)
    scoped_org = store_org._apply_scope(q_org, _ScopedModel)
    assert scoped_org.filters == [("organization_id", 10)]

    class _NoScopeModel:
        id = _Expr("id")

    q_none = _QueryObj()
    store_user = data_store_mod.DataStore(1, organization_id=10, access_level=3)
    assert store_user._apply_scope(q_none, _NoScopeModel) is q_none

    session = _Db(row=None)
    monkeypatch.setattr(data_store_mod, "app_ctx", lambda: SimpleNamespace(data_store=SimpleNamespace(get_session=lambda: session)))
    assert store_user.update(_ScopedModel, "missing", user_id=9) is None


def test_data_migrations_handler_rewriter_and_runner(monkeypatch, tmp_path):
    logger = _Logger()
    monkeypatch.setattr(data_migrations_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, data_store=SimpleNamespace(url="sqlite:///data.db"), config=SimpleNamespace()))
    monkeypatch.setattr(data_migrations_mod, "get_base_dir", lambda: "/base")
    monkeypatch.setattr(data_migrations_mod, "get_data_dir", lambda: "/data")

    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.data.database.get_database_url",
        lambda: "sqlite:///fallback.db",
    )
    monkeypatch.setattr(data_migrations_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    assert data_migrations_mod.get_current_db_url() == "sqlite:///fallback.db"
    monkeypatch.setattr(data_migrations_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, data_store=SimpleNamespace(url="sqlite:///data.db"), config=SimpleNamespace()))

    writer = data_migrations_mod.get_migration_rewriter("p_demo_")
    table_op = data_migrations_mod.ops.CreateTableOp("items", [])
    assert writer._traverse_for(None, None, table_op)[0].table_name == "p_demo_items"
    assert writer._traverse_for(None, None, data_migrations_mod.ops.DropTableOp("items"))[0].table_name == "p_demo_items"
    create_index = data_migrations_mod.ops.CreateIndexOp("idx_items_name", "items", ["name"])
    assert writer._traverse_for(None, None, create_index)[0].index_name == "p_demo_idx_items_name"
    drop_index = data_migrations_mod.ops.DropIndexOp("idx_items_name", "items")
    assert writer._traverse_for(None, None, drop_index)[0].index_name == "p_demo_idx_items_name"
    already_prefixed = data_migrations_mod.ops.DropIndexOp("p_demo_idx_items_name", "items")
    assert writer._traverse_for(None, None, already_prefixed)[0].index_name == "p_demo_idx_items_name"
    assert writer._traverse_for(None, None, data_migrations_mod.ops.AddColumnOp("items", object()))[0].table_name == "p_demo_items"
    assert writer._traverse_for(None, None, data_migrations_mod.ops.DropColumnOp("items", "name"))[0].table_name == "p_demo_items"
    assert writer._traverse_for(None, None, data_migrations_mod.ops.AlterColumnOp("items", "name"))[0].table_name == "p_demo_items"
    assert writer._traverse_for(None, None, data_migrations_mod.ops.AlterTableOp("items"))[0].table_name == "p_demo_items"
    fk_op = data_migrations_mod.ops.CreateForeignKeyOp("fk", "items", "users", [], [])
    prefixed = writer._traverse_for(None, None, fk_op)[0]
    assert prefixed.source_table == "p_demo_items"
    assert prefixed.referent_table == "p_demo_users"
    fk_core = data_migrations_mod.ops.CreateForeignKeyOp("fk", "items", "core_users", [], [])
    assert writer._traverse_for(None, None, fk_core)[0].referent_table == "core_users"
    fk_module = data_migrations_mod.ops.CreateForeignKeyOp("fk", "items", "p_other_users", [], [])
    assert writer._traverse_for(None, None, fk_module)[0].referent_table == "p_other_users"

    module_dir = tmp_path / "plugin1"
    migrations_dir = module_dir / "migrations"
    migrations_dir.mkdir(parents=True)
    (module_dir / "manifest.json").write_text(
        '{"name": "plug", "enabled": true}',
        encoding="utf-8",
    )
    module = SimpleNamespace(name="plug", path=str(module_dir))
    monkeypatch.setattr("democrai.core.infrastructure.modules.manager.module_manager", SimpleNamespace(get_all_modules=lambda: [module]))
    monkeypatch.setattr(data_migrations_mod, "get_runtime_module_dirs", lambda: (str(tmp_path),))
    monkeypatch.setattr(data_migrations_mod, "_module_metadata", lambda _module: "META")
    monkeypatch.setattr("democrai.core.infrastructure.storage.data.models.Base", SimpleNamespace(metadata="META"))

    configs = []

    class _Config:
        def __init__(self, path=None):
            self.path = path
            self.options = {}
            self.attributes = {}
            configs.append(self)

        def set_main_option(self, key, value):
            self.options[key] = value

    monkeypatch.setattr(data_migrations_mod, "Config", _Config)
    upgrades = []
    monkeypatch.setattr(data_migrations_mod.command, "upgrade", lambda cfg, target: upgrades.append((cfg.options.get("version_table"), target)))
    data_migrations_mod.run_data_migrations()
    assert ("alembic_version_data", "head") in upgrades
    assert ("alembic_version_p_plug", "head") in upgrades
    data_migrations_mod.run_module_migration("plug", str(module_dir))
    assert ("alembic_version_p_plug", "head") in upgrades

    no_migrations_module = tmp_path / "module-no-migrations"
    no_migrations_module.mkdir()
    assert data_migrations_mod.run_module_migration("skip", str(no_migrations_module)) is None

    monkeypatch.setattr(
        data_migrations_mod.command,
        "upgrade",
        lambda cfg, target: (_ for _ in ()).throw(RuntimeError("core fail"))
        if cfg.options.get("version_table") == "alembic_version_data"
        else upgrades.append((cfg.options.get("version_table"), target)),
    )
    with pytest.raises(data_migrations_mod.MigrationError, match="Data core migrations failed"):
        data_migrations_mod.run_data_migrations()


def test_data_migrations_module_metadata_loads_models_from_runtime_module_path(tmp_path):
    modules_root = tmp_path / "runtime_modules"
    module_name = "plug_meta"
    module_dir = modules_root / module_name
    module_dir.mkdir(parents=True)
    (modules_root / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "models.py").write_text(
        "\n".join(
            [
                "from sqlalchemy import Column, Integer, String",
                "from democrai.sdk.database import get_module_base",
                "",
                "Base = get_module_base()",
                "",
                "class ProbeRecord(Base):",
                "    id = Column(Integer, primary_key=True)",
                "    name = Column(String(80), nullable=False)",
            ]
        ),
        encoding="utf-8",
    )

    module = data_migrations_mod._ModuleMigrationTarget(
        module_name,
        str(module_dir),
        is_builtin=True,
    )

    metadata = data_migrations_mod._module_metadata(module)

    assert sorted(metadata.tables) == [f"p_{module_name}_probe_record"]


def test_sql_url_store_crud_and_non_sqlite_ctor_branch(monkeypatch, tmp_path):
    db_file = tmp_path / "sessions.db"
    store = sql_url_mod.SqlUrlJsonStore(f"sqlite:///{db_file}", "sessions")
    assert store.load("missing") is None
    store.save("k1", {"x": 1})
    assert store.load("k1") == {"x": 1}
    store.save("k1", {"x": 2})
    assert store.load("k1") == {"x": 2}
    assert "k1" in store.keys()
    store.delete("k1")
    assert store.load("k1") is None

    store.save("obj", {"when": object()})
    loaded = store.load("obj")
    assert isinstance(loaded, dict)
    with store._engine.begin() as conn:
        conn.execute(
            store._table.update()
            .where(store._table.c.session_key == "obj")
            .values(data=json.dumps("bad"))
        )
    assert store.load("obj") is None

    calls = {"pragmas": 0, "create_engine": None}

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            return SimpleNamespace(first=lambda: None, all=lambda: [])

        def commit(self):
            return None

    monkeypatch.setattr(sql_url_mod, "install_sqlite_engine_pragmas", lambda _engine: calls.__setitem__("pragmas", calls["pragmas"] + 1))
    monkeypatch.setattr(
        sql_url_mod,
        "create_engine",
        lambda url, connect_args=None: calls.__setitem__("create_engine", (url, connect_args))
        or sa_create_engine("sqlite:///:memory:"),
    )
    monkeypatch.setattr(sql_url_mod, "sessionmaker", lambda **kwargs: (lambda: _FakeSession()))

    store_pg = sql_url_mod.SqlUrlJsonStore("postgresql://db", "sessions")
    assert calls["create_engine"] == ("postgresql://db", {})
    assert calls["pragmas"] == 0
    assert store_pg.keys() == []


def test_sqlalchemy_json_store_fallback_session_and_keys(monkeypatch):
    class _QueryKeys:
        def all(self):
            return [("a",), ("b",)]

    class _FallbackDb:
        def __init__(self):
            self.closed = False

        def query(self, model):
            if model is _Model.session_key:
                return _QueryKeys()
            return _Query(row=None)

        def close(self):
            self.closed = True

    fallback_db = _FallbackDb()
    monkeypatch.setattr(sqlalchemy_store_mod, "app_ctx", lambda: SimpleNamespace(db=None))
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.database",
        SimpleNamespace(_default_SessionLocal=lambda: fallback_db),
    )
    store = sqlalchemy_store_mod.SqlAlchemyJsonStore(_Model)
    assert store._get_db_session() is fallback_db
    assert store.load("missing") is None
    assert store.keys() == ["a", "b"]

    row = _Model("k", json.dumps("not-dict"))
    db = _Db(row=row)
    monkeypatch.setattr(sqlalchemy_store_mod, "app_ctx", lambda: SimpleNamespace(db=SimpleNamespace(get_session=lambda: db)))
    assert store.load("k") is None
