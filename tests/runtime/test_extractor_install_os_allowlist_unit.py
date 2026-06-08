from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject


class _FakeStdout:
    def __init__(self, lines: list[bytes], events: list[str]) -> None:
        self._lines = list(lines)
        self._events = events

    async def readline(self) -> bytes:
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

    async def wait(self) -> int:
        return int(self.returncode)

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
    assert [(endpoint.host, endpoint.port) for endpoint in started[0][0].endpoints] == [
        ("example.invalid", 443)
    ]


@pytest.mark.asyncio
async def test_extractor_install_process_applies_os_allowlist_to_child_pid(monkeypatch):
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

    async def _create_subprocess_exec(*_args, **_kwargs):
        events.append("spawn")
        assert mod.INSTALL_NETWORK_READY_FILE_ENV in _kwargs["env"]
        assert not Path(_kwargs["env"][mod.INSTALL_NETWORK_READY_FILE_ENV]).exists()
        return fake_process

    async def _apply(pid, *, env, extractor_id):
        events.append(f"apply:{pid}")
        assert isinstance(env, dict)
        assert extractor_id == "docling"

    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", _create_subprocess_exec)
    monkeypatch.setattr(mod, "_apply_os_network_allowlist_to_install_process", _apply)
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
    assert events[:3] == ["spawn", "apply:12345", "read"]
