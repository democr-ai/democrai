from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.knowledge.extractor import queue_worker_runtime as mod
from democrai.core.application.knowledge.extractor import worker as worker_mod
from democrai.core.application.knowledge.extractor import worker_subject as subject_mod


class _Process:
    pid = 1234

    def poll(self):
        return None


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

    monkeypatch.setattr(worker_mod, "process_guard_context", _guard)
    monkeypatch.setattr(worker_mod, "extractor_env_context", _env)
    monkeypatch.setattr(worker_mod, "isolate_extractor_imports", lambda extractor_id: None)
    monkeypatch.setattr(worker_mod, "load_extractor_class", lambda extractor_id: _Extractor)

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
    assert isinstance(worker._extractor, _Extractor)


def test_extractor_worker_extract_requires_request_context():
    worker = worker_mod._Worker.__new__(worker_mod._Worker)

    with pytest.raises(RuntimeError, match="extractor_extract_request_context_required"):
        asyncio.run(worker._extract({"config": {}, "files": []}))


def test_extractor_worker_applies_os_allowlist_to_child_process(monkeypatch):
    state_mod = __import__(
        "democrai.core.infrastructure.sandbox.os.state",
        fromlist=["is_application_network_allowlist_enabled"],
    )
    helper_mod = __import__(
        "democrai.core.infrastructure.sandbox.os.helper",
        fromlist=["apply_application_network_endpoints_with_helper"],
    )
    guard_mod = __import__(
        "democrai.core.infrastructure.sandbox.process_guard",
        fromlist=["process_guard_bypass_context"],
    )
    config = object()
    access = (
        AccessManifestRule(
            subject=AccessSubject.create("extractor", "docling"),
            resource=AccessResource.create(
                resource_type="network",
                operation="receive",
                target="https://files.pythonhosted.org/*",
            ),
        ),
    )
    calls = []

    @contextmanager
    def _bypass():
        calls.append(("bypass_enter",))
        try:
            yield
        finally:
            calls.append(("bypass_exit",))

    monkeypatch.setattr(
        subject_mod,
        "app_ctx",
        lambda: SimpleNamespace(config=config, logger=None),
    )
    monkeypatch.setattr(
        state_mod,
        "is_application_network_allowlist_enabled",
        lambda current_config: current_config is config,
    )
    monkeypatch.setattr(state_mod, "is_application_network_allowlist_active", lambda: True)
    monkeypatch.setattr(guard_mod, "process_guard_bypass_context", _bypass)
    monkeypatch.setattr(
        helper_mod,
        "apply_application_network_endpoints_with_helper",
        lambda endpoints, *, pid, config: calls.append(
            ("apply", endpoints, pid, config)
        ),
    )

    subject_mod._apply_os_network_allowlist_to_worker_process(4321, access=access)

    assert calls == [
        ("bypass_enter",),
        (
            "apply",
            [
                {
                    "host": "files.pythonhosted.org",
                    "port": 443,
                    "protocol": "tcp",
                    "source": "extractor:docling",
                    "purpose": "extractor_receive",
                }
            ],
            4321,
            config,
        ),
        ("bypass_exit",),
    ]


def test_extractor_worker_subject_starts_with_local_ipc_without_inherited_fds(monkeypatch, tmp_path: Path):
    popen_calls = []
    listener_kinds = []
    accepted_prefixes = []

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

    class _Thread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    def _popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return _Process()

    def _listener(kind):
        listener_kinds.append(kind)
        return _Endpoint(kind)

    def _accept(endpoint, *, process, timeout_seconds):
        accepted_prefixes.append(endpoint.kind)
        return SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(subject_mod, "create_local_listener", _listener)
    monkeypatch.setattr(subject_mod, "accept_connection", _accept)
    monkeypatch.setattr(subject_mod.threading, "Thread", _Thread)
    monkeypatch.setattr(subject_mod.subprocess, "Popen", _popen)
    monkeypatch.setattr(subject_mod, "get_extractor_venv_python_path", lambda _extractor_id: tmp_path / "python")
    monkeypatch.setattr(subject_mod, "_application_pythonpath", lambda: str(tmp_path))
    monkeypatch.setattr(subject_mod, "_apply_os_network_allowlist_to_worker_process", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(subject_mod, "worker_runtime_config", lambda: {})
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

    subject = subject_mod.ExtractorWorkerSubject("demo", phase="runtime", config={})
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
    finally:
        subject.close()
