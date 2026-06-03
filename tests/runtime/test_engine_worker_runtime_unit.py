from __future__ import annotations

from contextlib import contextmanager
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.ai.engine import worker as worker_mod
from democrai.core.application.ai.engine.runtime import worker as subject_mod
from democrai.core.runtime.dependencies import engine_env as engine_env_mod


class _Config:
    def get(self, key, default=None):
        values = {
            "logging.provider": "http",
            "logging.url": "https://logs.example.test/ingest",
            "logging.method": "POST",
            "database.url": "sqlite:///secret.db",
            "sandbox.os.landlock.enabled": True,
        }
        return values.get(key, default)


def test_engine_worker_logging_config_contains_only_logger_keys(monkeypatch):
    monkeypatch.setattr(subject_mod, "app_ctx", lambda: SimpleNamespace(config=_Config()))

    assert subject_mod.worker_logging_config() == {
        "logging.provider": "http",
        "logging.url": "https://logs.example.test/ingest",
        "logging.method": "POST",
    }
    assert subject_mod.worker_landlock_enabled() is True


def test_engine_worker_runtime_access_adds_logger_access(monkeypatch, tmp_path: Path):
    timezone_path = "/var/db/timezone/zoneinfo"
    engine_access = (
        AccessManifestRule(
            subject=AccessSubject.create("engine", "demo"),
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="read",
                target=str(tmp_path / "engine-cache"),
            ),
        ),
    )
    monkeypatch.setattr(subject_mod, "get_engine_access", lambda *_a, **_k: engine_access)
    monkeypatch.setattr(subject_mod, "system_read_paths", lambda: (timezone_path,))
    monkeypatch.setattr(subject_mod.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(subject_mod, "logs_dir", lambda: tmp_path / "logs")

    access = subject_mod.worker_runtime_access(
        engine_id="demo",
        config={},
        logging_config={
            "logging.provider": "http",
            "logging.url": "https://logs.example.test/ingest",
        },
    )

    resources = [
        (
            str(rule.resource.resource_type),
            str(rule.resource.operation),
            rule.resource.target,
        )
        for rule in access
    ]
    assert ("filesystem", "read", timezone_path) in resources
    assert ("filesystem", "read", str(tmp_path / "engine-cache")) in resources
    assert ("filesystem", "modify", str((tmp_path / "logs").resolve())) in resources
    assert (
        "network",
        "send",
        "https://logs.example.test/ingest",
    ) in resources


def test_engine_worker_init_uses_in_memory_config_and_explicit_guard(monkeypatch, tmp_path: Path):
    calls = []

    class _Engine:
        def __init__(self, config):
            self.config = config

    class _Logger:
        def __init__(self, *, log_dir, config):
            calls.append(("logger", log_dir, config))

    @contextmanager
    def _guard(**kwargs):
        calls.append(("guard", kwargs))
        yield

    @contextmanager
    def _env(engine_id, env=None):
        calls.append(("env", engine_id, env))
        yield

    monkeypatch.setattr(worker_mod, "LoggerManager", _Logger)
    monkeypatch.setattr(worker_mod, "logs_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(worker_mod, "process_guard_context", _guard)
    monkeypatch.setattr(worker_mod, "engine_env_context", _env)
    monkeypatch.setattr(worker_mod, "isolate_engine_imports", lambda engine_id: None)
    monkeypatch.setattr(worker_mod, "load_engine_class", lambda engine_id: _Engine)
    timezone_path = "/var/db/timezone/zoneinfo"
    monkeypatch.setattr(
        worker_mod,
        "runtime_system_read_paths",
        lambda: [str(tmp_path / "system"), timezone_path],
    )
    monkeypatch.setattr(worker_mod, "_configure_engine_path_overrides", lambda engine_id: calls.append(("paths", engine_id)))
    monkeypatch.setattr(worker_mod, "_apply_worker_landlock", lambda **kwargs: calls.append(("landlock", kwargs)))

    worker = worker_mod._Worker.__new__(worker_mod._Worker)
    worker._stack = ExitStack()
    worker._engine = None
    worker._engine_id = ""
    worker._tasks = {}

    try:
        worker._init(
            {
                "engine_id": "demo",
                "config": {"model": "tiny"},
                "logging_config": {
                    "logging.provider": "local",
                    "database.url": "must-not-be-used",
                },
                "landlock_enabled": True,
                "env": {"XDG_CACHE_HOME": str(tmp_path / "cache")},
                "access": [],
                "allowed_imports": [],
                "allowed_subprocess_commands": [],
            }
        )
    finally:
        worker._stack.close()

    logger_call = next(item for item in calls if item[0] == "logger")
    assert logger_call[2].get("logging.provider") == "local"
    assert logger_call[2].get("database.url") is None
    logger_call[2].set("database.url", "still-must-not-be-used")
    assert logger_call[2].get("database.url") is None
    guard_call = next(item for item in calls if item[0] == "guard")
    assert guard_call[1]["include_runtime_access"] is False
    assert guard_call[1]["inherit_parent_access"] is False
    guard_access = [
        (
            str(rule.resource.resource_type),
            str(rule.resource.operation),
            rule.resource.target,
        )
        for rule in guard_call[1]["access"]
    ]
    assert ("filesystem", "read", str(tmp_path / "system")) in guard_access
    assert ("filesystem", "read", timezone_path) in guard_access
    assert not any(item[2] == str(tmp_path) for item in guard_access)
    assert isinstance(worker._engine, _Engine)


def test_engine_worker_landlock_paths_use_access_rules_without_global_config(tmp_path: Path):
    engine_env = tmp_path / "engine_env_cache" / "demo"
    engine_cache = engine_env / "cache"
    app_config = tmp_path / "config.yaml"
    engine_cache.mkdir(parents=True)
    app_config.write_text("secret: true\n", encoding="utf-8")
    access = (
        AccessManifestRule(
            subject=AccessSubject.create("engine", "demo"),
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="modify",
                target=str(engine_cache),
            ),
        ),
    )

    read_only, read_write = worker_mod._worker_landlock_access_paths(access)

    assert str(engine_cache.resolve()) in read_write
    assert str(app_config.resolve()) not in read_only
    assert str(app_config.resolve()) not in read_write


def test_engine_env_uses_worker_path_overrides(monkeypatch, tmp_path: Path):
    def _fail_data_dir():
        raise AssertionError("data_dir_must_not_be_read")

    engine_env_mod.set_engine_local_path_overrides(
        "ollama",
        env_path=str(tmp_path / "env"),
        cache_path=str(tmp_path / "cache"),
        config_path=str(tmp_path / "config"),
        tmp_path=str(tmp_path / "tmp"),
    )
    monkeypatch.setattr(engine_env_mod, "data_dir", _fail_data_dir)

    assert engine_env_mod.get_engine_local_env_path("ollama") == tmp_path / "env"
    assert engine_env_mod.get_engine_local_cache_path("ollama") == tmp_path / "cache"
    assert engine_env_mod.get_engine_local_config_path("ollama") == tmp_path / "config"
    assert engine_env_mod.get_engine_local_tmp_path("ollama") == tmp_path / "tmp"


def test_engine_env_without_overrides_uses_data_dir(monkeypatch, tmp_path: Path):
    engine_env_mod._ENGINE_LOCAL_PATH_OVERRIDES.pop("install_demo", None)
    monkeypatch.setattr(engine_env_mod, "_ENGINE_ENV_ROOT", tmp_path / "engine_env_cache")

    assert (
        engine_env_mod.get_engine_local_env_path("install_demo")
        == tmp_path / "engine_env_cache" / "install_demo"
    )
    assert (
        engine_env_mod.get_engine_local_cache_path("install_demo")
        == tmp_path / "engine_env_cache" / "install_demo" / "cache"
    )
    assert (
        engine_env_mod.get_engine_local_config_path("install_demo")
        == tmp_path / "engine_env_cache" / "install_demo" / "config"
    )
    assert (
        engine_env_mod.get_engine_local_tmp_path("install_demo")
        == tmp_path / "engine_env_cache" / "install_demo" / "tmp"
    )
