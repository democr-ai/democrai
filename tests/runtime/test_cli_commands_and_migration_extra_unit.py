from types import SimpleNamespace

import pytest

import democrai.core.runtime.cli.commands as commands_mod
import democrai.core.runtime.cli.migration as migration_mod


def test_migration_internal_helpers(monkeypatch):
    monkeypatch.setattr(migration_mod, "app_ctx", lambda: SimpleNamespace(config=SimpleNamespace(get=lambda k, d=None: "clickhouse" if k == "storage.observability.type" else d)))
    monkeypatch.setattr(migration_mod, "YamlConfigProvider", lambda _p: SimpleNamespace(get=lambda *_a, **_k: "sqlite"))
    target = migration_mod.MigrationTarget(
        name="observability",
        label="OBS",
        ini_path="/tmp/a.ini",
        script_location="/tmp/migs",
        metadata_factory=lambda: "meta",
        url_factory=lambda: "sqlite:///x.db",
    )
    assert migration_mod._is_clickhouse_observability_target(target) is True

    class _Cfg:
        def __init__(self, _path):
            self.options = {}
            self.attributes = {}

        def set_main_option(self, key, value):
            self.options[key] = value

    monkeypatch.setattr(migration_mod, "Config", _Cfg)
    cfg = migration_mod._build_config(target)
    assert cfg.options["script_location"] == "/tmp/migs"

    monkeypatch.setattr(
        migration_mod,
        "_target_specs",
        lambda: {"db": target, "vector": target, "data": target, "observability": target},
    )
    assert migration_mod._resolve_targets("all")


def test_migration_metadata_and_url_helpers(monkeypatch, tmp_path):
    monkeypatch.setattr(migration_mod, "get_data_dir", lambda: str(tmp_path))
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.database.models",
        SimpleNamespace(Base=SimpleNamespace(metadata="dbmeta")),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.database",
        SimpleNamespace(get_database_url=lambda: "sqlite:///core.db"),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.storage.data.models",
        SimpleNamespace(Base=SimpleNamespace(metadata="datameta")),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.storage.data.database",
        SimpleNamespace(get_database_url=lambda: "sqlite:///data.db"),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.storage.observability.models",
        SimpleNamespace(Base=SimpleNamespace(metadata="obsmeta")),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.storage.vector.models",
        SimpleNamespace(Base=SimpleNamespace(metadata="vecmeta")),
    )

    modules_dir = tmp_path / "modules"
    (modules_dir / "m1").mkdir(parents=True)
    (modules_dir / "m2").mkdir()
    monkeypatch.setattr(migration_mod, "get_runtime_module_dirs", lambda: (str(modules_dir),))
    imported = []
    monkeypatch.setattr("importlib.import_module", lambda name: imported.append(name) or object())

    assert migration_mod._db_metadata() == "dbmeta"
    assert migration_mod._db_url() == "sqlite:///core.db"
    migration_mod._load_module_models()
    assert "modules.m1.models" in imported
    assert migration_mod._data_metadata() == "datameta"
    assert migration_mod._data_url() == "sqlite:///data.db"
    assert migration_mod._observability_metadata() == "obsmeta"
    assert migration_mod._vector_metadata() == "vecmeta"
    assert migration_mod._vector_url().endswith("vector.db")
    monkeypatch.setattr(migration_mod, "app_ctx", lambda: SimpleNamespace(config=SimpleNamespace(get=lambda _k, d=None: "sqlite")))
    assert migration_mod._observability_url().endswith("observability.db")
    monkeypatch.setattr(migration_mod, "get_base_dir", lambda: str(tmp_path))
    specs = migration_mod._target_specs()
    assert set(specs.keys()) == {"db", "vector", "data", "observability"}


def test_migration_commands(monkeypatch):
    calls = []
    target = migration_mod.MigrationTarget(
        name="db",
        label="DB",
        ini_path="/tmp/a.ini",
        script_location="/tmp/migs",
        metadata_factory=lambda: "meta",
        url_factory=lambda: "sqlite:///x.db",
    )
    monkeypatch.setattr(migration_mod, "_init_cli_context", lambda: None)
    monkeypatch.setattr(migration_mod, "_resolve_targets", lambda _n: [target])
    monkeypatch.setattr(migration_mod, "_is_clickhouse_observability_target", lambda _t: False)
    monkeypatch.setattr(migration_mod, "_build_config", lambda _t: "cfg")
    monkeypatch.setattr(migration_mod.command, "upgrade", lambda cfg, rev: calls.append(("up", cfg, rev)))
    monkeypatch.setattr(migration_mod.command, "revision", lambda cfg, message, autogenerate=False: calls.append(("rev", cfg, message, autogenerate)))
    monkeypatch.setattr(migration_mod.command, "downgrade", lambda cfg, rev: calls.append(("down", cfg, rev)))
    monkeypatch.setattr(migration_mod, "_get_status", lambda _t: migration_mod.MigrationStatus(target="db", label="DB", current_revision="1", head_revision="2", up_to_date=False))

    assert migration_mod.migrate("db") == 0
    assert migration_mod.create_migration("db", "msg", autogenerate=True) == 0
    assert migration_mod.rollback("db", steps=1) == 0
    assert migration_mod.rollback("db", revision="abc") == 0
    with pytest.raises(ValueError):
        migration_mod.rollback("db")
    assert migration_mod.migration_status("db") == 0
    assert calls


def test_migration_status_with_engine(monkeypatch):
    target = migration_mod.MigrationTarget(
        name="db",
        label="DB",
        ini_path="/tmp/a.ini",
        script_location="/tmp/migs",
        metadata_factory=lambda: "meta",
        url_factory=lambda: "sqlite:///x.db",
    )
    monkeypatch.setattr(migration_mod, "_is_clickhouse_observability_target", lambda _t: False)
    monkeypatch.setattr(migration_mod, "_build_config", lambda _t: "cfg")
    monkeypatch.setattr(migration_mod.ScriptDirectory, "from_config", lambda _cfg: SimpleNamespace(get_current_head=lambda: "head"))

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Engine:
        def connect(self):
            return _Conn()

        def dispose(self):
            return None

    monkeypatch.setattr(migration_mod, "create_engine", lambda _url: _Engine())
    monkeypatch.setattr(migration_mod.MigrationContext, "configure", lambda _conn, opts=None: SimpleNamespace(get_current_revision=lambda: "head"))
    status = migration_mod._get_status(target)
    assert status.up_to_date is True


def test_commands_context_and_knowledge_rebuild(monkeypatch):
    logs = []
    class _Bootstrapper:
        def init_config(self, ctx):
            logs.append("cfg")
        def init_storage(self, ctx):
            logs.append("storage")
        def init_modules(self, ctx, args):
            logs.append("modules")
        def run_migrations(self, ctx):
            logs.append("migrations")
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.infrastructure.observability.logger.manager", SimpleNamespace(LoggerManager=lambda log_dir=None: "logger"))
    monkeypatch.setitem(__import__("sys").modules, "democrai.core.runtime.bootstrap.bootstrap_pipeline", SimpleNamespace(RuntimeBootstrapper=_Bootstrapper))
    ctx = SimpleNamespace(logger=None, config=None, setup_mode=False)
    monkeypatch.setattr(commands_mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(commands_mod, "logs_dir", lambda: "/tmp/logs")
    commands_mod.init_module_command_context(SimpleNamespace())
    commands_mod.init_knowledge_command_context(SimpleNamespace())
    assert "cfg" in logs and "storage" in logs

    source = SimpleNamespace(id="s1", user_id=1, organization_id=None, source_type="doc", status="ok")
    result_obj = SimpleNamespace(source_id="s1", user_id=1, organization_id=None, source_type="doc", outbox_ids=("o1",))
    repo = SimpleNamespace(list_sources=lambda **_k: [source])
    service = SimpleNamespace(repository=repo, admin_rebuild_sources=lambda **_k: [result_obj])
    monkeypatch.setattr(commands_mod, "init_knowledge_command_context", lambda _a: None)
    monkeypatch.setattr(commands_mod, "app_ctx", lambda: SimpleNamespace(knowledge_service=service))
    assert commands_mod.knowledge_rebuild(source_id="s1", args=SimpleNamespace()) == 0
    assert commands_mod.knowledge_rebuild(rebuild_all=True, dry_run=True, args=SimpleNamespace()) == 0
    with pytest.raises(ValueError):
        commands_mod.knowledge_rebuild(args=SimpleNamespace())
