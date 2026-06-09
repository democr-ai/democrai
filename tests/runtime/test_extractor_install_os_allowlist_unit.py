from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.runtime.foundation.paths import logs_dir


class _FakeStdout:
    def __init__(self, lines: list[bytes], events: list[str]) -> None:
        self._lines = list(lines)
        self._events = events

    def readline(self) -> bytes:
        self._events.append("read")
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeProcess:
    def __init__(self, stdout: _FakeStdout) -> None:
        self.pid = 12345
        self.stdout = stdout
        self.returncode = 0
        self.terminated = False

    def wait(self) -> int:
        return int(self.returncode)

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


@pytest.mark.asyncio
async def test_extractor_install_apply_uses_proxy_loopback_only(monkeypatch):
    import democrai.core.application.knowledge.extractor.install_events as mod

    applied = []
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=SimpleNamespace(get=lambda *_a, **_k: True),
        ),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.helper.apply_application_network_allowlist_with_helper",
        lambda allowlist, **kwargs: applied.append((allowlist, kwargs)),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.factory.get_helper_backend",
        lambda: SimpleNamespace(supports_pid_enforcement=True),
    )

    await mod._apply_os_network_allowlist_to_install_process(
        123,
        env={"ALL_PROXY": "http://127.0.0.1:4123"},
        extractor_id="docling",
    )

    hosts = [endpoint.host for endpoint in applied[0][0].endpoints]
    assert hosts == ["127.0.0.1"]
    assert applied[0][1]["pid"] == 123


@pytest.mark.asyncio
async def test_extractor_install_proxy_session_uses_extractor_network_access(monkeypatch):
    import democrai.core.application.knowledge.extractor.install_events as mod

    subject = AccessSubject.create("extractor", "docling")
    started = []
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=SimpleNamespace(get=lambda *_a, **_k: True),
        ),
    )
    monkeypatch.setattr(
        "democrai.core.application.knowledge.extractor.runtime.get_extractor_access",
        lambda *_a, **_k: (
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="network",
                    operation="receive",
                    target="https://example.invalid",
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.helper.start_application_network_proxy_session_with_helper",
        lambda allowlist, **kwargs: started.append((allowlist, kwargs))
        or {"session_id": "session-1", "proxy_url": "http://127.0.0.1:4123"},
    )

    env = {}
    session_id = await mod._start_os_network_proxy_for_install(env, extractor_id="docling")

    assert session_id == "session-1"
    assert env["ALL_PROXY"] == "http://127.0.0.1:4123"
    assert env["WSS_PROXY"] == "http://127.0.0.1:4123"
    assert env["wss_proxy"] == "http://127.0.0.1:4123"
    assert [(endpoint.host, endpoint.port) for endpoint in started[0][0].endpoints] == [
        ("example.invalid", 443)
    ]


def test_extractor_install_access_includes_logs_dir():
    from democrai.core.application.knowledge.extractor.runtime import get_extractor_access

    log_path = str(logs_dir().resolve())

    targets = {
        (rule.resource.operation.value, rule.resource.normalized_target)
        for rule in get_extractor_access("docling", "install")
        if rule.resource.resource_type.value == "filesystem"
    }

    assert ("read", log_path) in targets
    assert ("create", log_path) in targets
    assert ("modify", log_path) in targets
    assert ("delete", log_path) in targets


def test_extractor_install_launch_state_covers_nested_proxy_access():
    import democrai.core.application.knowledge.extractor.install_events as mod
    from democrai.core.application.knowledge.extractor.runtime import (
        _extractor_install_proxy_access,
        get_extractor_access,
    )
    from democrai.core.infrastructure.sandbox import spawn_broker
    from democrai.core.infrastructure.sandbox.os.launch_policy import build_launch_policy

    env = {mod.EXTRACTOR_INSTALL_PROXY_CONNECT_TARGET_ENV: "127.0.0.1:4123"}
    parent_state = mod._extractor_install_launch_state("docling", env=env)
    child_state = {
        **parent_state,
        "access": (
            *get_extractor_access("docling", "install"),
            *_extractor_install_proxy_access("docling", "127.0.0.1:4123"),
        ),
    }
    parent_policy = build_launch_policy(
        command=["python", "-m", "parent"],
        cwd=None,
        env=env,
        state=parent_state,
    )
    child_policy = build_launch_policy(
        command=["python", "-m", "child"],
        cwd=None,
        env=env,
        state=child_state,
    )

    spawn_broker._validate_child_policy(parent_policy, child_policy)


@pytest.mark.asyncio
async def test_extractor_install_process_uses_sandbox_launcher_state(monkeypatch):
    import democrai.core.application.knowledge.extractor.install_events as mod

    events: list[str] = []
    payload = json.dumps({"status": "installed"}, sort_keys=True)
    fake_process = _FakeProcess(
        _FakeStdout(
            [
                f"{mod.EXTRACTOR_INSTALL_PROCESS_RESULT_PREFIX}{payload}\n".encode(
                    "utf-8"
                ),
            ],
            events,
        )
    )

    def _popen(command, **kwargs):
        events.append("spawn")
        assert command[:2] == [mod.sys.executable, "-m"]
        env = kwargs["env"]
        assert mod.INSTALL_NETWORK_READY_FILE_ENV in env
        assert not Path(env[mod.INSTALL_NETWORK_READY_FILE_ENV]).exists()
        assert kwargs["stdin"] is mod.subprocess.DEVNULL
        assert kwargs["stdout"] is mod.subprocess.PIPE
        assert kwargs["stderr"] is mod.subprocess.STDOUT
        assert kwargs["text"] is False
        assert kwargs["state"]["subject_kind"] == "extractor"
        assert kwargs["state"]["subject"] == "docling"
        launch_access = tuple(kwargs["state"]["access"])
        for rule in mod.get_extractor_access("docling", "install"):
            assert rule in launch_access
        return fake_process

    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.launcher.popen",
        _popen,
    )
    monkeypatch.setattr(mod, "emit_extractor_install_output", lambda *_a, **_k: None)
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=SimpleNamespace(get=lambda *_a, **_k: False),
            runtime_module_paths=("modules",),
            runtime_engine_paths=("engines",),
            runtime_extractor_paths=("extractors",),
        ),
    )

    result = await mod._run_extractor_install_runtime_process(
        extractor_id="docling",
        force=False,
        node_id="node-1",
        event_id="event-1",
        source_node_id=None,
        install_config={"ocr_engine": "rapidocr"},
    )

    assert result == {"status": "installed"}
    assert events[:2] == ["spawn", "read"]
