from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextlib import ExitStack
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.knowledge.extractor import queue_worker_runtime as mod
from democrai.core.application.knowledge.extractor import worker as worker_mod
from democrai.core.application.knowledge.extractor import worker_subject as subject_mod
from democrai.core.infrastructure.sandbox import launcher as launcher_mod
from democrai.core.runtime.dependencies import extractor_env as extractor_env_mod


class _Process:
    pid = 1234
    stdout = None

    def poll(self):
        return None

    def wait(self, timeout=None):  # noqa: ARG002
        return 0


def test_queue_worker_bootstrap_does_not_initialize_kg_store(monkeypatch):
    process_mod = __import__(
        "democrai.core.application.knowledge.extractor.queue_worker_process",
        fromlist=["_bootstrap_context"],
    )
    calls = []

    class _Config:
        def get(self, key, default=None):
            values = {
                "database.type": "sqlite",
                "database.url": "sqlite:////tmp/democrai-test.db",
                "storage.media.type": "local",
                "storage.media.path": "/tmp/democrai-media",
                "storage.kg.type": "ladybug",
            }
            return values.get(key, default)

    class _Bootstrapper:
        def init_config(self, ctx):
            ctx.setup_mode = False
            ctx.config = _Config()

        def init_storage(self, ctx):
            raise AssertionError("full_storage_bootstrap_must_not_run")

    ctx = SimpleNamespace()
    monkeypatch.setattr(process_mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(process_mod, "configure_temp_environment", lambda: None)
    monkeypatch.setattr(process_mod, "logs_dir", lambda: Path("/tmp"))
    monkeypatch.setattr(
        process_mod,
        "LoggerManager",
        lambda log_dir: SimpleNamespace(info=lambda message: calls.append(("log", message))),
    )
    monkeypatch.setattr(process_mod, "RuntimeBootstrapper", _Bootstrapper)
    monkeypatch.setattr(
        process_mod.PersistenceProviderFactory,
        "get_provider",
        lambda provider_type, **kwargs: calls.append(("db", provider_type, kwargs)) or object(),
    )
    monkeypatch.setattr(
        process_mod.MediaProviderFactory,
        "get_provider",
        lambda provider_type, **kwargs: calls.append(("media", provider_type, kwargs)) or object(),
    )

    process_mod._bootstrap_context()

    assert any(item[0] == "db" for item in calls)
    assert any(item[0] == "media" for item in calls)
    assert not hasattr(ctx, "kg_store")


def test_start_extraction_queue_worker_process_registers_child(monkeypatch):
    popen_calls = []
    register_calls = []

    def _popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return _Process()

    monkeypatch.setattr(mod.subprocess, "Popen", _popen)
    monkeypatch.setattr(
        mod.process_supervisor,
        "register",
        lambda process, name: register_calls.append((process, name)),
    )
    ctx = SimpleNamespace(
        setup_mode=False,
        knowledge_extraction_worker_process=None,
        logger=SimpleNamespace(info=lambda _message: None),
    )

    process = mod.start_extraction_queue_worker_process(ctx)

    assert process is ctx.knowledge_extraction_worker_process
    assert popen_calls[0][0][-1] == (
        "democrai.core.application.knowledge.extractor.queue_worker_process"
    )
    assert popen_calls[0][1]["stdin"] is mod.subprocess.DEVNULL
    assert register_calls == [(process, "knowledge-extraction-worker")]


def test_start_extraction_queue_worker_process_skips_setup_mode():
    ctx = SimpleNamespace(
        setup_mode=True,
        knowledge_extraction_worker_process=None,
    )

    assert mod.start_extraction_queue_worker_process(ctx) is None


def test_extractor_worker_module_keeps_heavy_core_imports_lazy():
    source = Path(worker_mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        "from democrai.core.application.knowledge.extractor.manifests",
        "from democrai.core.infrastructure.sandbox.process_guard",
        "from democrai.core.runtime.dependencies.extractor_env",
        "from democrai.core.runtime.foundation.app",
        "from democrai.core.application.ai.engine.runtime.serialization",
    )

    for item in forbidden:
        assert item not in "\n".join(
            line for line in source.splitlines() if line.startswith("from ")
        )


def test_extractor_worker_bootstrap_prioritizes_application_pythonpath(monkeypatch, tmp_path: Path):
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


def test_extractor_worker_init_payload_is_resolved_in_parent(monkeypatch, tmp_path: Path):
    access = (
        AccessManifestRule(
            subject=AccessSubject.create("extractor", "demo"),
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="read",
                target=str(tmp_path / "source"),
            ),
        ),
    )
    monkeypatch.setattr(subject_mod, "worker_runtime_config", lambda: {"auth.jwt_algorithm": "HS256"})
    monkeypatch.setattr(
        subject_mod,
        "worker_path_overrides",
        lambda _extractor_id: {
            "env": "env",
            "cache": "cache",
            "config": "config",
            "tmp": "tmp",
        },
    )

    payload = subject_mod.build_extractor_worker_init_payload(
        extractor_id="demo",
        phase="runtime",
        config={"chunk_size": 1000},
        access=access,
        allowed_imports=["docling"],
    )

    assert payload["runtime_config"] == {"auth.jwt_algorithm": "HS256"}
    assert payload["env"] == {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    assert payload["path_overrides"] == {
        "env": "env",
        "cache": "cache",
        "config": "config",
        "tmp": "tmp",
    }
    assert payload["allowed_imports"] == ["docling"]
    assert payload["access"][0]["resource"]["target"] == str(tmp_path / "source")


def test_extractor_worker_runtime_config_materializes_unix_orchestrator_socket(monkeypatch):
    class _Config:
        def get(self, key, default=None):
            values = {
                "ai.engine_orchestrator.transport": "unix",
                "ai.engine_orchestrator.socket_path": "",
            }
            return values.get(key, default)

    monkeypatch.setattr(subject_mod, "app_ctx", lambda: SimpleNamespace(config=_Config()))
    monkeypatch.setattr(
        subject_mod,
        "orchestrator_socket_path",
        lambda _config: "/tmp/democrai-test/engine-orchestrator.sock",
    )

    runtime_config = subject_mod.worker_runtime_config()

    assert runtime_config["ai.engine_orchestrator.transport"] == "unix"
    assert (
        runtime_config["ai.engine_orchestrator.socket_path"]
        == "/tmp/democrai-test/engine-orchestrator.sock"
    )


def test_extractor_worker_runtime_init_does_not_require_request_context(monkeypatch):
    calls = []

    class _Extractor:
        def __init__(self, config):
            self.config = config

    @contextmanager
    def _guard(**kwargs):
        calls.append(("guard", kwargs))
        yield

    @contextmanager
    def _env(extractor_id, env=None):
        calls.append(("env", extractor_id, env))
        yield

    def _set_paths(extractor_id, **kwargs):
        calls.append(("paths", extractor_id, kwargs))

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.process_guard",
        SimpleNamespace(process_guard_context=_guard),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.dependencies.extractor_env",
        SimpleNamespace(
            extractor_env_context=_env,
            isolate_extractor_imports=lambda extractor_id: None,
            set_extractor_local_path_overrides=_set_paths,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.knowledge.extractor.manifests",
        SimpleNamespace(load_extractor_class=lambda extractor_id: _Extractor),
    )

    worker = worker_mod._Worker.__new__(worker_mod._Worker)
    worker._stack = ExitStack()
    worker._extractor_cls = None
    worker._extractor = None
    worker._extractor_id = ""
    worker._phase = ""

    try:
        worker._init(
            {
                "extractor_id": "ai_audio",
                "phase": "runtime",
                "config": {"model_registry_id": 1},
                "env": {"HF_HUB_OFFLINE": "1"},
                "path_overrides": {
                    "env": "env",
                    "cache": "cache",
                    "config": "config",
                    "tmp": "tmp",
                },
                "access": [],
                "allowed_imports": [],
            }
        )
    finally:
        worker._stack.close()

    guard_call = next(item for item in calls if item[0] == "guard")
    assert "user_id" not in guard_call[1]
    assert "organization_id" not in guard_call[1]
    assert "session_key" not in guard_call[1]
    assert ("paths", "ai_audio", {
        "env_path": "env",
        "cache_path": "cache",
        "config_path": "config",
        "tmp_path": "tmp",
    }) in calls
    assert isinstance(worker._extractor, _Extractor)


def test_extractor_worker_init_requires_path_overrides():
    with pytest.raises(RuntimeError, match="extractor_worker_path_overrides_required"):
        worker_mod._configure_extractor_path_overrides("demo", {"env": "env"})


def test_extractor_worker_env_uses_subject_tmp_before_spawn(tmp_path: Path):
    extractor_id = "temp_env_docling"
    extractor_env_mod.set_extractor_local_path_overrides(
        extractor_id,
        env_path=str(tmp_path / "env"),
        cache_path=str(tmp_path / "cache"),
        config_path=str(tmp_path / "config"),
        tmp_path=str(tmp_path / "tmp"),
    )

    try:
        env = subject_mod._with_extractor_temp_env({"TMPDIR": "/tmp"}, extractor_id)
    finally:
        extractor_env_mod._EXTRACTOR_LOCAL_PATH_OVERRIDES.pop(extractor_id, None)

    assert env["TMPDIR"] == str(tmp_path / "tmp")
    assert env["TEMP"] == str(tmp_path / "tmp")
    assert env["TMP"] == str(tmp_path / "tmp")


def test_extractor_worker_extract_requires_request_context():
    worker = worker_mod._Worker.__new__(worker_mod._Worker)

    with pytest.raises(RuntimeError, match="extractor_extract_request_context_required"):
        asyncio.run(worker._extract({"config": {}, "files": []}))


def test_extractor_worker_subject_starts_with_local_ipc_without_inherited_fds(monkeypatch, tmp_path: Path):
    popen_calls = []
    listener_kinds = []
    accepted_prefixes = []
    bypass_state = {"active": False}
    bypass_observations = []

    @contextmanager
    def _bypass():
        bypass_state["active"] = True
        try:
            yield
        finally:
            bypass_state["active"] = False

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
        pid = 1234
        stdout = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    class _Thread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

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

    monkeypatch.setattr(subject_mod, "create_local_listener", _listener)
    monkeypatch.setattr(subject_mod, "accept_connection", _accept)
    monkeypatch.setattr(subject_mod.threading, "Thread", _Thread)
    monkeypatch.setattr(subject_mod.subprocess, "Popen", _popen)
    monkeypatch.setattr(subject_mod, "process_guard_bypass_context", _bypass)
    monkeypatch.setattr(subject_mod, "get_extractor_venv_python_path", lambda _extractor_id: tmp_path / "python")
    monkeypatch.setattr(subject_mod, "_application_pythonpath", lambda: str(tmp_path))
    monkeypatch.setattr(subject_mod, "worker_runtime_config", lambda: {})
    monkeypatch.setattr(
        subject_mod,
        "worker_path_overrides",
        lambda _extractor_id: {
            "env": "env",
            "cache": "cache",
            "config": "config",
            "tmp": "tmp",
        },
    )
    monkeypatch.setattr(
        subject_mod,
        "_clean_worker_env",
        lambda: {},
    )
    monkeypatch.setattr(
        subject_mod.ExtractorWorkerSubject,
        "_request",
        lambda self, operation, payload: None,
    )
    runtime_mod = __import__(
        "democrai.core.application.knowledge.extractor.runtime",
        fromlist=["get_extractor_access", "get_extractor_allowed_imports"],
    )
    monkeypatch.setattr(runtime_mod, "get_extractor_access", lambda *_args: ())
    monkeypatch.setattr(runtime_mod, "get_extractor_allowed_imports", lambda *_args: [])

    subject = subject_mod.ExtractorWorkerSubject(
        extractor_id="demo",
        phase="runtime",
        config={},
    )
    try:
        env = popen_calls[0][1]["env"]
        assert "pass" + "_fds" not in popen_calls[0][1]
        assert env["DEMOCRAI_EXTRACTOR_WORKER_CONTROL_ADDRESS"] == "extractor-worker-control-address"
        assert env["DEMOCRAI_EXTRACTOR_WORKER_CONTROL_AUTHKEY"] == "extractor-worker-control-auth"
        assert env["DEMOCRAI_EXTRACTOR_WORKER_PARENT_ADDRESS"] == "extractor-worker-parent-address"
        assert env["DEMOCRAI_EXTRACTOR_WORKER_PARENT_AUTHKEY"] == "extractor-worker-parent-auth"
        legacy_prefix = "DEMOCRAI_EXTRACTOR" + "_WORKER"
        assert legacy_prefix + "_READ_FD" not in env
        assert legacy_prefix + "_WRITE_FD" not in env
        assert listener_kinds == ["extractor-worker-control", "extractor-worker-parent"]
        assert accepted_prefixes == ["extractor-worker-control", "extractor-worker-parent"]
        assert bypass_observations
        assert all(active for _name, active in bypass_observations)
    finally:
        subject.close()


def test_extractor_worker_spawn_uses_os_sandbox_launcher_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(subject_mod, "worker_os_sandbox_enabled", lambda: True)
    monkeypatch.setattr(
        launcher_mod,
        "popen",
        lambda command, **kwargs: calls.append((command, kwargs)) or _Process(),
    )

    process = subject_mod._spawn_extractor_worker_process(
        ["python", "-V"],
        env={"A": "B"},
        launch_state={
            "subject": "docling",
            "subject_kind": "extractor",
            "access": (),
        },
    )

    assert process is not None
    assert calls[0][0] == ["python", "-V"]
    assert calls[0][1]["state"]["subject_kind"] == "extractor"
    assert calls[0][1]["env"] == {"A": "B"}


def test_extractor_worker_subject_os_sandbox_skips_pid_network_allowlist(monkeypatch, tmp_path: Path):
    popen_calls = []

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

    class _Thread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    def _accept(endpoint, *, process, timeout_seconds):  # noqa: ARG001
        return SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(subject_mod, "worker_os_sandbox_enabled", lambda: True)
    monkeypatch.setattr(subject_mod, "create_local_listener", lambda kind: _Endpoint(kind))
    monkeypatch.setattr(subject_mod, "accept_connection", _accept)
    monkeypatch.setattr(subject_mod.threading, "Thread", _Thread)
    monkeypatch.setattr(
        launcher_mod,
        "popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)) or _Process(),
    )
    monkeypatch.setattr(subject_mod, "get_extractor_venv_python_path", lambda _extractor_id: tmp_path / "python")
    monkeypatch.setattr(subject_mod, "_application_pythonpath", lambda: str(tmp_path))
    monkeypatch.setattr(subject_mod, "worker_runtime_config", lambda: {})
    monkeypatch.setattr(
        subject_mod,
        "worker_path_overrides",
        lambda _extractor_id: {
            "env": "env",
            "cache": "cache",
            "config": "config",
            "tmp": "tmp",
        },
    )
    monkeypatch.setattr(subject_mod, "_clean_worker_env", lambda: {})
    monkeypatch.setattr(
        subject_mod.ExtractorWorkerSubject,
        "_request",
        lambda self, operation, payload: None,
    )
    runtime_mod = __import__(
        "democrai.core.application.knowledge.extractor.runtime",
        fromlist=["get_extractor_access", "get_extractor_allowed_imports"],
    )
    monkeypatch.setattr(
        runtime_mod,
        "get_extractor_access",
        lambda *_args: (
            AccessManifestRule(
                subject=AccessSubject.create("extractor", "docling"),
                resource=AccessResource.create(
                    resource_type="network",
                    operation="connect",
                    target="https://example.test",
                ),
            ),
        ),
    )
    monkeypatch.setattr(runtime_mod, "get_extractor_allowed_imports", lambda *_args: [])

    subject = subject_mod.ExtractorWorkerSubject(
        extractor_id="docling",
        phase="runtime",
        config={},
    )
    try:
        assert popen_calls
        launch_state = popen_calls[0][1]["state"]
        assert launch_state["subject_kind"] == "extractor"
        assert launch_state["subject"] == "docling"
    finally:
        subject.close()


def test_extractor_worker_launch_state_adds_framework_ipc_on_linux(monkeypatch, tmp_path: Path):
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
        lambda: {"subject_chain": [{"kind": "module", "name": "system"}]},
    )

    state = subject_mod._extractor_worker_launch_state(extractor_id="Docling", access=())
    resources = {
        (
            rule.subject.subject_type,
            rule.subject.subject_name,
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in state["access"]
    }

    assert state["subject"] == "docling"
    assert state["subject_kind"] == "extractor"
    assert state["subject_chain"] == [
        {"kind": "module", "name": "system"},
        {"kind": "extractor", "name": "docling"},
    ]
    assert {
        ("extractor", "docling", "read", worker_launch_mod._application_root()),
        ("extractor", "docling", "read", str(ipc_root.resolve())),
        ("extractor", "docling", "modify", str(ipc_root.resolve())),
        ("extractor", "docling", "read", "/dev/shm"),
        ("extractor", "docling", "modify", "/dev/shm"),
    }.issubset(resources)


def test_extractor_worker_launch_state_does_not_add_windows_ipc_filesystem(monkeypatch):
    worker_launch_mod = __import__(
        "democrai.core.infrastructure.sandbox.worker_launch",
        fromlist=["runtime_ipc_dir"],
    )
    monkeypatch.setattr(worker_launch_mod.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.process_guard._state",
        lambda: {"subject_chain": []},
    )

    state = subject_mod._extractor_worker_launch_state(extractor_id="docling", access=())

    resources = {
        (rule.resource.operation.value, rule.resource.normalized_target)
        for rule in state["access"]
    }
    assert ("read", worker_launch_mod._application_root()) in resources
    assert all(not target.endswith("/ipc") for _operation, target in resources)
    assert ("read", "/dev/shm") not in resources
