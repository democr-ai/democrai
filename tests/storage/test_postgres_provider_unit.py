from types import SimpleNamespace

import pytest

import democrai.core.infrastructure.database.providers.postgres as mod


def test_postgres_provider_session_url_and_migrations(monkeypatch: pytest.MonkeyPatch):
    created = {}
    monkeypatch.setattr(mod, "create_engine", lambda url, pool_pre_ping=True: created.setdefault("engine", (url, pool_pre_ping)) or "engine")
    monkeypatch.setattr(mod, "sessionmaker", lambda **kwargs: (lambda: "session"))
    monkeypatch.setattr(mod, "scoped_session", lambda factory: factory)

    logger = SimpleNamespace(info=lambda *args, **kwargs: created.setdefault("info", []).append(args[0]), error=lambda *args, **kwargs: created.setdefault("error", []).append(args[0]))
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(mod, "get_base_dir", lambda: "/app")

    class _Config:
        def __init__(self, path):
            self.path = path
            self.options = {}
            self.attributes = {}

        def set_main_option(self, key, value):
            self.options[key] = value

    monkeypatch.setattr(mod, "Config", _Config)
    monkeypatch.setattr(mod.command, "upgrade", lambda cfg, target: created.setdefault("upgrade", (cfg.options, cfg.attributes, target)))
    monkeypatch.setattr("democrai.core.infrastructure.database.models.Base", SimpleNamespace(metadata="META"))

    provider = mod.PostgresPersistenceProvider("postgresql://u:p@localhost/db")
    assert created["engine"] == ("postgresql://u:p@localhost/db", True)
    assert provider.get_session() == "session"
    assert provider.get_url() == "postgresql://u:p@localhost/db"

    provider.run_migrations()
    options, attributes, target = created["upgrade"]
    assert options["script_location"] == "/app/core/infrastructure/database/migrations"
    assert options["sqlalchemy.url"] == "postgresql://u:p@localhost/db"
    assert attributes["target_metadata"] == "META"
    assert attributes["db_url"] == "postgresql://u:p@localhost/db"
    assert target == "head"


def test_postgres_provider_logs_errors_without_raising(monkeypatch: pytest.MonkeyPatch):
    errors = []
    monkeypatch.setattr(mod, "create_engine", lambda url, pool_pre_ping=True: "engine")
    monkeypatch.setattr(mod, "sessionmaker", lambda **kwargs: (lambda: "session"))
    monkeypatch.setattr(mod, "scoped_session", lambda factory: factory)
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=SimpleNamespace(info=lambda *a, **k: None, error=lambda message: errors.append(message))))
    monkeypatch.setattr(mod, "get_base_dir", lambda: "/app")
    monkeypatch.setattr(mod, "Config", lambda path: SimpleNamespace(set_main_option=lambda *args: None, attributes={}))
    monkeypatch.setattr(mod.command, "upgrade", lambda cfg, target: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr("democrai.core.infrastructure.database.models.Base", SimpleNamespace(metadata="META"))
    monkeypatch.setattr(mod, "traceback", SimpleNamespace(format_exc=lambda: "TRACEBACK"), raising=False)

    provider = mod.PostgresPersistenceProvider("postgresql://u:p@localhost/db")
    with pytest.raises(Exception, match="Database migration failed: boom"):
        provider.run_migrations()

    assert "Error during migrations: boom" in errors[0]
