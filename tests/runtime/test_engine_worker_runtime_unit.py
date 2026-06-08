from __future__ import annotations

from contextlib import contextmanager
from contextlib import ExitStack
import io
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.ai.engine import worker as worker_mod
from democrai.core.application.ai.engine.runtime import worker as subject_mod
from democrai.core.infrastructure.sandbox import launcher as launcher_mod
from democrai.core.runtime.dependencies import engine_env as engine_env_mod


class _Config:
    def get(self, key, default=None):
        values = {
            "logging.provider": "http",
            "logging.url": "https://logs.example.test/ingest",
            "logging.method": "POST",
            "database.url": "sqlite:///secret.db",
            "sandbox.os.enabled": True,
        }
        return values.get(key, default)


def test_engine_worker_logging_config_contains_only_logger_keys(monkeypatch):
    monkeypatch.setattr(subject_mod, "app_ctx", lambda: SimpleNamespace(config=_Config()))

    assert subject_mod.worker_logging_config() == {
        "logging.provider": "http",
        "logging.url": "https://logs.example.test/ingest",
        "logging.method": "POST",
    }
    assert subject_mod.worker_os_sandbox_enabled() is True


def test_engine_worker_module_keeps_heavy_core_imports_lazy():
    source = Path(worker_mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        "from democrai.core.application.ai.engine.manifests",
        "from democrai.core.infrastructure.sandbox.process_guard",
        "from democrai.core.infrastructure.observability.logger",
        "from democrai.core.application.ai.engine.schemas",
        "from democrai.core.application.ai.security",
        "from democrai.core.application.ai.engine.runtime.serialization",
    )

    for item in forbidden:
        assert item not in "\n".join(
            line for line in source.splitlines() if line.startswith("from ")
        )


def test_engine_worker_bootstrap_prioritizes_application_pythonpath(monkeypatch, tmp_path: Path):
    app_root = str(tmp_path / "app")
    app_site = str(tmp_path / "app-site")
    system_site = str(tmp_path / "system-site")
    original_path = list(sys.path)
    calls = []

    def _run_module(module, *, run_name):
        calls.append((module, run_name, list(sys.path[:4])))

    monkeypatch.setattr(
        sys,
        "argv",
        ["python", "demo.module", os.pathsep.join((app_root, app_site))],
    )
    monkeypatch.setattr(sys, "path", [system_site, app_site, "tail"])
    monkeypatch.setitem(sys.modules, "runpy", SimpleNamespace(run_module=_run_module))
    try:
        exec(subject_mod._WORKER_BOOTSTRAP_CODE, {})
    finally:
        sys.path[:] = original_path

    assert calls == [("demo.module", "__main__", [app_root, app_site, system_site, "tail"])]


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


def test_engine_worker_init_payload_is_resolved_in_parent(monkeypatch, tmp_path: Path):
    access = (
        AccessManifestRule(
            subject=AccessSubject.create("engine", "demo"),
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="read",
                target=str(tmp_path / "model"),
            ),
        ),
    )
    monkeypatch.setattr(subject_mod, "worker_logging_config", lambda: {"logging.provider": "local"})
    monkeypatch.setattr(subject_mod, "worker_os_sandbox_enabled", lambda: True)
    monkeypatch.setattr(subject_mod, "worker_path_overrides", lambda _engine_id: {"env": "env", "cache": "cache", "config": "config", "tmp": "tmp"})
    monkeypatch.setattr(subject_mod, "worker_landlock_paths", lambda: {"read_only": ["ro"], "read_write": ["rw"]})
    monkeypatch.setattr(subject_mod, "get_engine_runtime_env", lambda _engine_id: {"PATH": "runtime"})
    monkeypatch.setattr(subject_mod, "worker_runtime_access", lambda **_kwargs: access)
    monkeypatch.setattr(subject_mod, "get_engine_allowed_imports", lambda *_args: ["numpy"])
    monkeypatch.setattr(subject_mod, "get_engine_allowed_subprocess_commands", lambda *_args: ["ffmpeg"])

    payload = subject_mod.build_engine_worker_init_payload(
        engine_id="demo",
        config={"model": "tiny"},
        class_only=False,
    )

    assert payload["logging_config"] == {"logging.provider": "local"}
    assert payload["log_dir"]
    assert payload["path_overrides"] == {"env": "env", "cache": "cache", "config": "config", "tmp": "tmp"}
    assert payload["landlock_enabled"] is False
    assert payload["landlock_read_only_paths"] == ["ro"]
    assert payload["landlock_read_write_paths"] == ["rw"]
    assert payload["env"] == {"PATH": "runtime"}
    assert payload["allowed_imports"] == ["numpy"]
    assert payload["allowed_subprocess_commands"] == ["ffmpeg"]
    assert payload["access"][0]["resource"]["target"] == str(tmp_path / "model")


def test_engine_runtime_env_pins_parent_runtime_env(monkeypatch):
    from democrai.core.application.ai.engine.runtime import environment as env_mod
    from democrai.core.runtime.dependencies.installer_env import RUNTIME_ENV_JSON_ENV

    monkeypatch.setattr(env_mod, "_engine_phase_env", lambda *_args: {})
    monkeypatch.setattr(env_mod, "runtime_env", lambda: {"os": "linux", "gpu": {"has_nvidia": True}})
    monkeypatch.setattr(env_mod, "ensure_engine_runtime_driver_libs", lambda _engine_id: (None, ()))
    monkeypatch.setattr(env_mod, "ensure_engine_runtime_toolchain", lambda _engine_id: (None, ()))

    env = env_mod.get_engine_runtime_env("onnx")

    assert env[RUNTIME_ENV_JSON_ENV] == '{"gpu": {"has_nvidia": true}, "os": "linux"}'


def test_engine_worker_spawn_uses_os_sandbox_launcher_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(subject_mod, "worker_os_sandbox_enabled", lambda: True)
    monkeypatch.setattr(
        launcher_mod,
        "popen",
        lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(),
    )

    process = subject_mod._spawn_engine_worker_process(
        ["python", "-V"],
        env={"A": "B"},
        launch_state={
            "subject": "demo",
            "subject_kind": "engine",
            "access": (),
        },
    )

    assert process is not None
    assert calls[0][0] == ["python", "-V"]
    assert calls[0][1]["state"]["subject_kind"] == "engine"
    assert calls[0][1]["env"] == {"A": "B"}


def test_engine_worker_launch_state_adds_framework_ipc_on_posix(monkeypatch, tmp_path: Path):
    worker_launch_mod = __import__(
        "democrai.core.infrastructure.sandbox.worker_launch",
        fromlist=["runtime_ipc_dir"],
    )
    ipc_root = tmp_path / "ipc"
    monkeypatch.setattr(worker_launch_mod, "runtime_ipc_dir", lambda: ipc_root)
    monkeypatch.setattr(worker_launch_mod.os, "name", "posix", raising=False)
    monkeypatch.setattr(worker_launch_mod.sys, "platform", "linux")
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.process_guard._state",
        lambda: {
            "subject_chain": [{"kind": "module", "name": "system"}],
            "user_id": 7,
        },
    )

    state = subject_mod._engine_worker_launch_state(engine_id="YOLO", access=())
    resources = [
        (
            rule.subject.subject_type,
            rule.subject.subject_name,
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in state["access"]
    ]

    assert state["subject"] == "yolo"
    assert state["subject_kind"] == "engine"
    assert state["subject_chain"] == [
        {"kind": "module", "name": "system"},
        {"kind": "engine", "name": "yolo"},
    ]
    assert {
        ("engine", "yolo", "read", worker_launch_mod._application_root()),
        ("engine", "yolo", "read", str(ipc_root.resolve())),
        ("engine", "yolo", "create", str(ipc_root.resolve())),
        ("engine", "yolo", "modify", str(ipc_root.resolve())),
        ("engine", "yolo", "delete", str(ipc_root.resolve())),
        ("engine", "yolo", "read", "/dev/shm"),
        ("engine", "yolo", "create", "/dev/shm"),
        ("engine", "yolo", "modify", "/dev/shm"),
        ("engine", "yolo", "delete", "/dev/shm"),
    }.issubset(set(resources))


def test_engine_worker_launch_state_does_not_add_named_pipe_filesystem_access(monkeypatch):
    worker_launch_mod = __import__(
        "democrai.core.infrastructure.sandbox.worker_launch",
        fromlist=["runtime_ipc_dir"],
    )
    monkeypatch.setattr(worker_launch_mod.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.process_guard._state",
        lambda: {"subject_chain": []},
    )

    state = subject_mod._engine_worker_launch_state(engine_id="demo", access=())

    resources = {
        (rule.resource.operation.value, rule.resource.normalized_target)
        for rule in state["access"]
    }
    assert ("read", worker_launch_mod._application_root()) in resources
    assert all(not target.endswith("/ipc") for _operation, target in resources)
    assert ("read", "/dev/shm") not in resources


def test_engine_worker_no_response_message_keeps_diagnostics():
    class _Process:
        def poll(self):
            return None

        def wait(self, timeout):  # noqa: ARG002
            raise subject_mod.subprocess.TimeoutExpired("worker", timeout)

    subject = subject_mod.EngineWorkerSubject.__new__(subject_mod.EngineWorkerSubject)
    subject._engine_id = "yolo"
    subject._process = _Process()
    subject._stderr_thread = None
    subject._stderr_tail = ["sandbox denied /dev/null"]
    subject._stderr_lock = threading.Lock()

    message = subject._log_worker_no_response(operation="invoke", return_code=None)

    assert "engine_worker_no_response:None" in message
    assert "engine_id=yolo" in message
    assert "operation=invoke" in message
    assert "status=still_running_after_pipe_close" in message
    assert "sandbox denied /dev/null" in message


def test_engine_worker_start_failure_message_keeps_stderr():
    class _Process:
        stderr = io.StringIO("landlock_add_rule_failed:/dev/null:13\n")

        def poll(self):
            return 126

    subject = subject_mod.EngineWorkerSubject.__new__(subject_mod.EngineWorkerSubject)
    subject._engine_id = "llamacpp"
    subject._process = _Process()
    subject._stderr_reader = subject._process.stderr
    subject._stderr_tail = []
    subject._stderr_lock = threading.Lock()

    message = subject._worker_start_failure_message(
        stage="control_connect",
        error=RuntimeError("local_connection_process_exited_before_connect:126"),
    )

    assert "engine_worker_start_failed" in message
    assert "engine_id=llamacpp" in message
    assert "stage=control_connect" in message
    assert "return_code=126" in message
    assert "landlock_add_rule_failed:/dev/null:13" in message


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

    monkeypatch.setattr(
        worker_mod,
        "_configure_worker_logging",
        lambda logging_config, log_dir: calls.append(("logger", log_dir, worker_mod._WorkerRuntimeConfig(logging_config))),
    )
    monkeypatch.setattr(
        worker_mod,
        "_configure_engine_path_overrides",
        lambda engine_id, path_overrides: calls.append(("paths", engine_id, path_overrides)),
    )
    monkeypatch.setattr(worker_mod, "_apply_worker_landlock", lambda **kwargs: calls.append(("landlock", kwargs)))
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.process_guard",
        SimpleNamespace(process_guard_context=_guard),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.dependencies.engine_env",
        SimpleNamespace(
            engine_env_context=_env,
            isolate_engine_imports=lambda engine_id: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.manifests",
        SimpleNamespace(load_engine_class=lambda engine_id: _Engine),
    )

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
                "log_dir": str(tmp_path / "logs"),
                "landlock_enabled": True,
                "env": {"XDG_CACHE_HOME": str(tmp_path / "cache")},
                "path_overrides": {
                    "env": str(tmp_path / "env"),
                    "cache": str(tmp_path / "cache"),
                    "config": str(tmp_path / "config"),
                    "tmp": str(tmp_path / "tmp"),
                },
                "landlock_read_only_paths": [str(tmp_path / "system")],
                "landlock_read_write_paths": [],
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
    assert guard_call[1]["include_network_access"] is False
    guard_access = [
        (
            str(rule.resource.resource_type),
            str(rule.resource.operation),
            rule.resource.target,
        )
        for rule in guard_call[1]["access"]
    ]
    assert not any(item[2] == str(tmp_path) for item in guard_access)
    assert isinstance(worker._engine, _Engine)


def test_engine_worker_init_requires_path_overrides():
    try:
        worker_mod._configure_engine_path_overrides("demo", {"env": "env"})
    except RuntimeError as exc:
        assert str(exc) == "engine_worker_path_overrides_required"
    else:
        raise AssertionError("engine_worker_path_overrides_required")


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


def test_engine_worker_env_uses_subject_tmp_before_spawn(tmp_path: Path):
    engine_id = "temp_env_demo"
    engine_env_mod.set_engine_local_path_overrides(
        engine_id,
        env_path=str(tmp_path / "env"),
        cache_path=str(tmp_path / "cache"),
        config_path=str(tmp_path / "config"),
        tmp_path=str(tmp_path / "tmp"),
    )

    try:
        env = subject_mod._with_engine_temp_env({"TMPDIR": "/tmp"}, engine_id)
    finally:
        engine_env_mod._ENGINE_LOCAL_PATH_OVERRIDES.pop(engine_id, None)

    assert env["TMPDIR"] == str(tmp_path / "tmp")
    assert env["TEMP"] == str(tmp_path / "tmp")
    assert env["TMP"] == str(tmp_path / "tmp")


def test_invoke_engine_class_method_loads_class_inside_engine_guard(monkeypatch):
    from democrai.core.application.ai.engine.runtime import methods as methods_mod

    events = []

    @contextmanager
    def _guard(**kwargs):
        events.append(("guard_enter", kwargs["subject"], kwargs["subject_kind"]))
        try:
            yield
        finally:
            events.append(("guard_exit", kwargs["subject"], kwargs["subject_kind"]))

    class _Engine:
        @staticmethod
        def support_status(env):
            events.append(("method", env))
            return {"ok": True}

    def _load(engine_id):
        events.append(("load", engine_id, events[-1][0] if events else "none"))
        return _Engine

    monkeypatch.setattr(methods_mod, "process_guard_context", _guard)
    monkeypatch.setattr(methods_mod, "get_engine_access", lambda *_a, **_k: ())
    monkeypatch.setattr(methods_mod, "get_engine_allowed_imports", lambda *_a: [])
    monkeypatch.setattr(
        methods_mod,
        "get_engine_allowed_subprocess_commands",
        lambda *_a: [],
    )
    monkeypatch.setattr(methods_mod, "get_engine_runtime_env", lambda *_a: {})
    monkeypatch.setattr(
        methods_mod,
        "engine_env_context",
        lambda *_a, **_k: _guard(subject="env", subject_kind="env"),
    )
    monkeypatch.setattr(methods_mod, "load_engine_class", _load)

    result = methods_mod.invoke_engine_class_method(
        engine_id="onnx",
        phase="runtime",
        method="support_status",
        payload={"env": {}},
    )

    assert result == {"ok": True}
    assert events[0] == ("guard_enter", "onnx", "engine")
    assert events[1] == ("load", "onnx", "guard_enter")


def test_check_engine_ready_runtime_checks_venv_inside_engine_guard(monkeypatch):
    from democrai.core.application.ai.engine.runtime import methods as methods_mod

    state = {"inside_guard": False}

    @contextmanager
    def _guard(**_kwargs):
        state["inside_guard"] = True
        try:
            yield
        finally:
            state["inside_guard"] = False

    class _PythonPath:
        def exists(self):
            assert state["inside_guard"] is True
            return False

    monkeypatch.setattr(methods_mod, "_engine_guard", lambda **_kwargs: _guard())
    monkeypatch.setattr(
        methods_mod,
        "get_engine_venv_python_path",
        lambda _engine_id: _PythonPath(),
    )

    result = methods_mod.check_engine_ready_runtime(engine_id="onnx", node_id="node")

    assert result["ready"] is False
    assert result["engine_id"] == "onnx"
    assert result["node_id"] == "node"


def test_get_engine_runtime_access_does_not_create_engine_env(monkeypatch, tmp_path: Path):
    from democrai.core.application.ai.engine.runtime import access as access_mod

    monkeypatch.setattr(engine_env_mod, "_ENGINE_ENV_ROOT", tmp_path / "engine_env_cache")
    monkeypatch.setattr(access_mod, "app_ctx", lambda: SimpleNamespace(config=None))

    access = access_mod.get_engine_access("onnx", "runtime", config={})

    assert access
    assert not (tmp_path / "engine_env_cache" / "onnx").exists()


def test_engine_runtime_access_uses_platform_dependency_matrix(monkeypatch, tmp_path: Path):
    from democrai.core.application.ai.engine.runtime import access as access_mod

    monkeypatch.setattr(engine_env_mod, "_ENGINE_ENV_ROOT", tmp_path / "engine_env_cache")
    monkeypatch.setattr(access_mod, "app_ctx", lambda: SimpleNamespace(config=None))
    monkeypatch.setattr(
        access_mod,
        "engine_runtime_dependency_read_paths",
        lambda: ("/opt/homebrew",),
    )
    monkeypatch.setattr(
        access_mod,
        "engine_runtime_c_compiler_candidate_paths",
        lambda: ("/opt/homebrew/bin/clang",),
    )
    monkeypatch.setattr(
        access_mod,
        "engine_runtime_toolchain_program_candidate_paths",
        lambda: {"ld": ("/opt/homebrew/bin/ld",)},
    )

    access = access_mod.get_engine_access("onnx", "runtime", config={})
    resources = {
        (
            rule.resource.resource_type.value,
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in access
    }

    assert ("filesystem", "read", "/opt/homebrew") in resources
    assert ("filesystem", "execute", "/opt/homebrew/bin/clang") in resources
    assert ("filesystem", "execute", "/opt/homebrew/bin/ld") in resources
    assert ("filesystem", "modify", "/opt/homebrew") not in resources
    assert ("filesystem", "delete", "/opt/homebrew") not in resources


def test_engine_runtime_access_preserves_trusted_read_alias_and_realpath(monkeypatch, tmp_path: Path):
    from democrai.core.application.ai.engine.runtime import access as access_mod
    from democrai.core.application.ai.engine import access_constants as constants_mod
    from democrai.core.infrastructure.sandbox import platform_policy

    monkeypatch.setattr(engine_env_mod, "_ENGINE_ENV_ROOT", tmp_path / "engine_env_cache")
    monkeypatch.setattr(access_mod, "app_ctx", lambda: SimpleNamespace(config=None))
    monkeypatch.setattr(constants_mod, "os_key", lambda: "linux")
    monkeypatch.setattr(
        platform_policy,
        "LINUX_SYSTEM_PROBE_READ_PATHS",
        ("/etc/os-release",),
    )
    monkeypatch.setattr(platform_policy, "LINUX_RUNTIME_DEPENDENCY_READ_PATHS", ())
    monkeypatch.setattr(
        platform_policy.os.path,
        "exists",
        lambda path: str(path) in {"/etc/os-release", "/usr/lib/os-release"},
    )
    monkeypatch.setattr(
        platform_policy.os.path,
        "realpath",
        lambda path, *args, **kwargs: "/usr/lib/os-release" if str(path) == "/etc/os-release" else str(path),
    )

    access = access_mod.get_engine_access("yolo", "runtime", config={})
    resources = {
        (
            rule.resource.resource_type.value,
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in access
    }

    assert ("filesystem", "read", "/etc/os-release") in resources
    assert ("filesystem", "read", "/usr/lib/os-release") in resources
    assert ("filesystem", "modify", "/etc/os-release") not in resources
    assert ("filesystem", "create", "/etc/os-release") not in resources


def test_worker_runtime_access_preserves_system_read_alias_and_realpath(monkeypatch, tmp_path: Path):
    from democrai.core.infrastructure.sandbox import platform_policy

    monkeypatch.setattr(subject_mod, "get_engine_access", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(subject_mod, "get_runtime_module_dirs", lambda: ())
    monkeypatch.setattr(subject_mod, "get_runtime_engine_dirs", lambda: ())
    monkeypatch.setattr(subject_mod, "get_base_dir", lambda: tmp_path / "app")
    monkeypatch.setattr(subject_mod.sys, "path", [])
    monkeypatch.setattr(subject_mod.sysconfig, "get_paths", lambda: {})
    monkeypatch.setattr(subject_mod.sys, "prefix", "")
    monkeypatch.setattr(subject_mod.sys, "exec_prefix", "")
    monkeypatch.setattr(platform_policy.sys, "platform", "linux")
    monkeypatch.setattr(
        platform_policy,
        "LINUX_SYSTEM_PROBE_READ_PATHS",
        ("/etc/os-release",),
    )
    monkeypatch.setattr(platform_policy, "LINUX_RUNTIME_DEPENDENCY_READ_PATHS", ())
    monkeypatch.setattr(
        platform_policy.os.path,
        "exists",
        lambda path: str(path) in {"/etc/os-release", "/usr/lib/os-release"},
    )
    monkeypatch.setattr(
        platform_policy.os.path,
        "realpath",
        lambda path, *args, **kwargs: "/usr/lib/os-release" if str(path) == "/etc/os-release" else str(path),
    )
    access = subject_mod.worker_runtime_access(
        engine_id="yolo",
        config={},
        logging_config={},
    )
    resources = {
        (
            rule.resource.resource_type.value,
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in access
    }

    assert ("filesystem", "read", "/etc/os-release") in resources
    assert ("filesystem", "read", "/usr/lib/os-release") in resources
    assert ("filesystem", "modify", "/etc/os-release") not in resources


def test_engine_runtime_access_includes_windows_venv_read_roots(monkeypatch, tmp_path: Path):
    from democrai.core.application.ai.engine.runtime import access as access_mod

    monkeypatch.setattr(engine_env_mod, "_ENGINE_ENV_ROOT", tmp_path / "engine_env_cache")
    monkeypatch.setattr(access_mod, "app_ctx", lambda: SimpleNamespace(config=None))
    monkeypatch.setattr(access_mod, "engine_runtime_dependency_read_paths", lambda: ())

    access = access_mod.get_engine_access("onnx", "runtime", config={})
    read_targets = {
        rule.resource.normalized_target
        for rule in access
        if rule.resource.resource_type.value == "filesystem"
        and rule.resource.operation.value == "read"
    }
    venv_root = tmp_path / "engine_env_cache" / "onnx" / ".venv"

    assert str((venv_root / "Scripts").resolve()) in read_targets
    assert str((venv_root / "DLLs").resolve()) in read_targets
    assert str((venv_root / "Lib").resolve()) in read_targets
    assert str((venv_root / "Lib" / "site-packages").resolve()) in read_targets
    assert not (tmp_path / "engine_env_cache" / "onnx").exists()


def test_engine_worker_subject_starts_with_local_ipc_without_inherited_fds(monkeypatch, tmp_path: Path):
    popen_calls = []
    listener_kinds = []
    accepted_prefixes = []
    bypass_state = {"active": False}
    bypass_observations = []

    class _Endpoint:
        def __init__(self, kind: str) -> None:
            self.kind = kind
            self.address = f"{kind}-address"

        def env(self, prefix: str) -> dict[str, str]:
            return {
                f"{prefix}_ADDRESS": self.address,
                f"{prefix}_AUTHKEY": f"{self.kind}-auth",
            }

        def close(self) -> None:
            pass

    class _Process:
        stderr = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    @contextmanager
    def _bypass():
        previous = bypass_state["active"]
        bypass_state["active"] = True
        try:
            yield
        finally:
            bypass_state["active"] = previous

    class _Thread:
        def __init__(self, *, target, args=(), **kwargs):
            self._target = target
            self._args = args

        def start(self):
            if self._args and getattr(self._args[0], "kind", "") == "engine-worker-parent":
                self._target(*self._args)

    def _popen(command, **kwargs):
        bypass_observations.append(("popen", bypass_state["active"]))
        popen_calls.append((command, kwargs))
        return _Process()

    def _listener(kind):
        listener_kinds.append(kind)
        return _Endpoint(kind)

    def _accept(endpoint, *, process, timeout_seconds):
        bypass_observations.append((f"accept:{endpoint.kind}", bypass_state["active"]))
        accepted_prefixes.append(endpoint.kind)
        return SimpleNamespace(close=lambda: None)

    def _request(self, operation, payload):
        bypass_observations.append((f"request:{operation}", bypass_state["active"]))
        return None

    monkeypatch.setattr(subject_mod, "create_local_listener", _listener)
    monkeypatch.setattr(subject_mod, "accept_connection", _accept)
    monkeypatch.setattr(subject_mod.threading, "Thread", _Thread)
    monkeypatch.setattr(subject_mod.subprocess, "Popen", _popen)
    monkeypatch.setattr(subject_mod, "process_guard_bypass_context", _bypass)
    monkeypatch.setattr(subject_mod, "application_pythonpath", lambda: str(tmp_path))
    monkeypatch.setattr(subject_mod, "get_engine_venv_python_path", lambda _engine_id: tmp_path / "python")
    monkeypatch.setattr(subject_mod, "get_engine_local_tmp_path", lambda _engine_id: tmp_path / "tmp")
    monkeypatch.setattr(subject_mod, "worker_logging_config", lambda: {})
    monkeypatch.setattr(subject_mod, "worker_os_sandbox_enabled", lambda: False)
    monkeypatch.setattr(subject_mod, "worker_path_overrides", lambda _engine_id: {})
    monkeypatch.setattr(subject_mod, "worker_landlock_paths", lambda: {"read_only": [], "read_write": []})
    monkeypatch.setattr(subject_mod, "get_engine_runtime_env", lambda _engine_id: {})
    monkeypatch.setattr(subject_mod, "worker_runtime_access", lambda **_kwargs: ())
    monkeypatch.setattr(subject_mod, "get_engine_allowed_imports", lambda *_args: [])
    monkeypatch.setattr(subject_mod, "get_engine_allowed_subprocess_commands", lambda *_args: [])
    monkeypatch.setattr(
        subject_mod.EngineWorkerSubject,
        "_request",
        _request,
    )

    subject = subject_mod.EngineWorkerSubject(engine_id="demo", config={"model": "tiny"})
    try:
        env = popen_calls[0][1]["env"]
        assert "pass" + "_fds" not in popen_calls[0][1]
        assert env["DEMOCRAI_ENGINE_WORKER_CONTROL_ADDRESS"] == "engine-worker-control-address"
        assert env["DEMOCRAI_ENGINE_WORKER_CONTROL_AUTHKEY"] == "engine-worker-control-auth"
        assert env["DEMOCRAI_ENGINE_WORKER_PARENT_ADDRESS"] == "engine-worker-parent-address"
        assert env["DEMOCRAI_ENGINE_WORKER_PARENT_AUTHKEY"] == "engine-worker-parent-auth"
        legacy_prefix = "DEMOCRAI_ENGINE" + "_WORKER"
        assert legacy_prefix + "_READ_FD" not in env
        assert legacy_prefix + "_WRITE_FD" not in env
        assert listener_kinds == ["engine-worker-control", "engine-worker-parent"]
        assert accepted_prefixes == ["engine-worker-control", "engine-worker-parent"]
        assert bypass_observations
        assert all(active for _name, active in bypass_observations)
    finally:
        subject.close()
