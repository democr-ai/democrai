from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

import democrai.core.infrastructure.database.preferences as pref_mod
import democrai.core.infrastructure.database.providers.sqlite as sqlite_mod
from democrai.core.infrastructure.database.providers.sqlite import SqlitePersistenceProvider


class _Query:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _Session:
    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def query(self, model):
        return _Query(self.row)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1


def session_scope(existing):
    session = _Session(existing)
    if hasattr(session, "__enter__") and hasattr(session, "__exit__"):
        return session


def test_preferences_get_and_set(monkeypatch):
    existing = SimpleNamespace(value="it")
    monkeypatch.setattr(pref_mod, "session_scope", lambda: session_scope(existing))
    assert pref_mod.get_preference("lang", "en") == "it"

    monkeypatch.setattr(pref_mod, "session_scope", lambda: session_scope(None))
    assert pref_mod.get_preference("missing", "en") == "en"

    update_session = session_scope(existing)
    monkeypatch.setattr(pref_mod, "session_scope", lambda: update_session)
    pref_mod.set_preference("lang", "fr")
    assert existing.value == "fr"
    assert update_session.commits == 1

    created_session = session_scope(None)

    class _PreferenceFactory:
        key = "field"

        def __call__(self, key, value):
            return SimpleNamespace(key=key, value=value)

    monkeypatch.setattr(pref_mod, "Preference", _PreferenceFactory())
    monkeypatch.setattr(pref_mod, "session_scope", lambda: created_session)
    pref_mod.set_preference("theme", "light")
    assert created_session.added[0].key == "theme"
    assert created_session.commits == 1


def test_preferences_get_and_set_handle_missing_table(monkeypatch):
    class _BrokenSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def query(self, *_args, **_kwargs):
            raise OperationalError("SELECT 1", {}, RuntimeError("missing"))

    def session_scope():
        session = _BrokenSession()
        if hasattr(session, "__enter__") and hasattr(session, "__exit__"):
            return session

    monkeypatch.setattr(pref_mod, "session_scope", lambda: session_scope())

    assert pref_mod.get_preference("lang", "en") == "en"
    pref_mod.set_preference("lang", "it")


@pytest.mark.posix_only
def test_sqlite_persistence_provider_init_and_migrations(monkeypatch, tmp_path):
    db_path = str(tmp_path / "democrai.db")
    engine_calls = []
    event_targets = []
    listener = {}

    class _Cursor:
        def __init__(self):
            self.executed = []
            self.closed = False

        def execute(self, sql):
            self.executed.append(sql)

        def close(self):
            self.closed = True

    cursor = _Cursor()

    monkeypatch.setattr(
        sqlite_mod,
        "create_engine",
        lambda url, connect_args=None: engine_calls.append((url, connect_args))
        or "engine",
    )
    monkeypatch.setattr(
        sqlite_mod, "sessionmaker", lambda **kwargs: ("sessionmaker", kwargs)
    )
    monkeypatch.setattr(
        sqlite_mod,
        "scoped_session",
        lambda maker: (lambda: ("scoped", maker)),
    )
    monkeypatch.setattr(
        "sqlalchemy.event.listens_for",
        lambda target, name: event_targets.append((target, name))
        or (lambda fn: listener.setdefault("fn", fn) or fn),
    )

    provider = SqlitePersistenceProvider(db_path)
    assert provider.get_url() == f"sqlite:///{db_path}"
    assert provider.get_session() == (
        "scoped",
        ("sessionmaker", {"autocommit": False, "autoflush": False, "bind": "engine"}),
    )
    assert engine_calls == [
        (
            f"sqlite:///{db_path}",
            {"check_same_thread": False, "timeout": 5.0},
        )
    ]
    assert event_targets == [("engine", "connect")]

    listener["fn"](SimpleNamespace(cursor=lambda: cursor), None)
    assert cursor.executed == [
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA wal_autocheckpoint=1000",
        "PRAGMA journal_size_limit=268435456",
        "PRAGMA busy_timeout=5000",
        "PRAGMA temp_store=MEMORY",
    ]
    assert cursor.closed is True

    logger = SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None)
    cfg = SimpleNamespace(options={})
    cfg.set_main_option = lambda key, value: cfg.options.__setitem__(key, value)
    monkeypatch.setattr(sqlite_mod, "get_base_dir", lambda: "/app")
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx", lambda: SimpleNamespace(logger=logger)
    )
    monkeypatch.setattr(sqlite_mod, "Config", lambda path: cfg)
    upgrade_calls = []
    monkeypatch.setattr(
        sqlite_mod.command,
        "upgrade",
        lambda alembic_cfg, rev: upgrade_calls.append((alembic_cfg, rev)),
    )

    provider.run_migrations()
    assert cfg.options["script_location"].endswith(
        "/core/infrastructure/database/migrations"
    )
    assert cfg.options["sqlalchemy.url"] == provider.url
    assert upgrade_calls and upgrade_calls[0][1] == "head"


def test_sqlite_persistence_provider_run_migrations_reraises(monkeypatch, tmp_path):
    provider = SqlitePersistenceProvider.__new__(SqlitePersistenceProvider)
    provider.url = f"sqlite:///{tmp_path / 'db.sqlite'}"
    logger = SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None)
    cfg = SimpleNamespace(options={})
    cfg.set_main_option = lambda key, value: cfg.options.__setitem__(key, value)
    monkeypatch.setattr(sqlite_mod, "get_base_dir", lambda: "/app")
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx", lambda: SimpleNamespace(logger=logger)
    )
    monkeypatch.setattr(sqlite_mod, "Config", lambda path: cfg)
    monkeypatch.setattr(
        sqlite_mod.command,
        "upgrade",
        lambda alembic_cfg, rev: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        provider.run_migrations()


@pytest.mark.posix_only
def test_sqlite_persistence_provider_uses_default_data_dir(monkeypatch):
    monkeypatch.setattr(sqlite_mod, "get_data_dir", lambda: "/data")
    monkeypatch.setattr(
        sqlite_mod, "create_engine", lambda url, connect_args=None: "engine"
    )
    monkeypatch.setattr(
        sqlite_mod, "sessionmaker", lambda **kwargs: lambda: ("session", kwargs)
    )
    monkeypatch.setattr(sqlite_mod, "scoped_session", lambda maker: maker)
    monkeypatch.setattr(
        "sqlalchemy.event.listens_for", lambda target, name: (lambda fn: fn)
    )

    provider = SqlitePersistenceProvider()
    assert provider.db_path == "/data/democrai.db"
    assert provider.get_url() == "sqlite:////data/democrai.db"
