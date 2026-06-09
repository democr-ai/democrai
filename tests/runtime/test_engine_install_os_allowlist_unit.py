from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from democrai.core.infrastructure.database.models import (
    Base,
    EngineNodeInstallRegistry,
)
from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject


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
        self.cleaned = False

    def wait(self, timeout: float | None = None) -> int:
        return int(self.returncode)

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True

    def cleanup(self) -> None:
        self.cleaned = True


class _StreamManager:
    def __init__(self) -> None:
        self.broadcasts: list[tuple[str, dict]] = []

    async def broadcast(self, stream_id: str, payload: dict) -> None:
        self.broadcasts.append((stream_id, payload))


@pytest.fixture()
def engine_install_session(monkeypatch):
    import democrai.core.application.ai.engine.install_events as mod

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(mod, "SessionLocal", SessionLocal)
    monkeypatch.setattr(mod, "get_engine_manifest", lambda _engine_id: {})
    monkeypatch.setattr(mod, "get_runtime_node_id", lambda: "node-1")
    yield SessionLocal
    Base.metadata.drop_all(engine)
    engine.dispose()


def _engine_install_app(stream_manager: _StreamManager) -> SimpleNamespace:
    return SimpleNamespace(
        network=SimpleNamespace(stream_manager=stream_manager, _loop=None),
        logger=None,
        config=None,
        node_id="node-1",
    )


def _seed_node_status(SessionLocal, *, status: str, event_id: str | None) -> None:
    with SessionLocal() as session:
        session.add(
            EngineNodeInstallRegistry(
                engine_id="demo",
                node_id="node-1",
                status=status,
                last_event_id=event_id,
                manifest_version="1",
            )
        )
        session.commit()


def _node_event_id(SessionLocal) -> str:
    with SessionLocal() as session:
        row = (
            session.query(EngineNodeInstallRegistry)
            .filter(
                EngineNodeInstallRegistry.engine_id == "demo",
                EngineNodeInstallRegistry.node_id == "node-1",
            )
            .first()
        )
        return str(row.last_event_id or "") if row is not None else ""


@pytest.mark.asyncio
async def test_engine_install_apply_uses_proxy_loopback_only(monkeypatch):
    import democrai.core.application.ai.engine.install_events as mod

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
        engine_id="rebel",
    )

    hosts = [endpoint.host for endpoint in applied[0][0].endpoints]
    assert hosts == ["127.0.0.1"]
    assert applied[0][1]["pid"] == 123


@pytest.mark.asyncio
async def test_engine_install_proxy_session_uses_engine_network_access(monkeypatch):
    import democrai.core.application.ai.engine.install_events as mod

    subject = AccessSubject.create("engine", "rebel")
    started = []
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=SimpleNamespace(get=lambda *_a, **_k: True),
        ),
    )
    monkeypatch.setattr(
        "democrai.core.application.ai.engine.runtime.access.get_engine_network_access",
        lambda *_a, **_k: (
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="network",
                    operation="receive",
                    target="https://download.pytorch.org",
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
    session_id = await mod._start_os_network_proxy_for_install(env, engine_id="rebel")

    assert session_id == "session-1"
    assert env["ALL_PROXY"] == "http://127.0.0.1:4123"
    assert env["WSS_PROXY"] == "http://127.0.0.1:4123"
    assert env["wss_proxy"] == "http://127.0.0.1:4123"
    assert [(endpoint.host, endpoint.port) for endpoint in started[0][0].endpoints] == [
        ("download.pytorch.org", 443)
    ]


@pytest.mark.asyncio
async def test_engine_install_process_uses_sandbox_launcher_state(monkeypatch):
    import democrai.core.application.ai.engine.install_events as mod

    events: list[str] = []
    payload = json.dumps({"config_updates": {"ok": True}}, sort_keys=True)
    fake_process = _FakeProcess(
        _FakeStdout(
            [
                f"{mod.ENGINE_INSTALL_PROCESS_RESULT_PREFIX}{payload}\n".encode("utf-8"),
            ],
            events,
        )
    )

    def _popen(command, **kwargs):
        events.append("spawn")
        assert command[:2] == [mod.sys.executable, "-m"]
        env = kwargs["env"]
        assert env["ALL_PROXY"] == "http://127.0.0.1:4123"
        assert env["WSS_PROXY"] == "http://127.0.0.1:4123"
        assert mod.INSTALL_NETWORK_READY_FILE_ENV in env
        assert not Path(env[mod.INSTALL_NETWORK_READY_FILE_ENV]).exists()
        assert kwargs["stdin"] is mod.subprocess.DEVNULL
        assert kwargs["stdout"] is mod.subprocess.PIPE
        assert kwargs["stderr"] is mod.subprocess.STDOUT
        assert kwargs["text"] is False
        assert kwargs["state"] == {"access": mod.get_engine_access("demo", "install", config={})}
        return fake_process

    states = []
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.launcher.popen",
        _popen,
    )
    async def _start_proxy(env, **_kwargs):
        events.append("proxy_start")
        env.update(
            {
                "ALL_PROXY": "http://127.0.0.1:4123",
                "WSS_PROXY": "http://127.0.0.1:4123",
            }
        )
        return "session-1"

    monkeypatch.setattr(mod, "_start_os_network_proxy_for_install", _start_proxy)
    async def _stop_proxy(session_id):
        events.append(f"proxy_stop:{session_id}")

    monkeypatch.setattr(mod, "_stop_os_network_proxy_for_install", _stop_proxy)
    monkeypatch.setattr(
        mod,
        "build_worker_launch_state",
        lambda **kwargs: states.append(kwargs) or {"access": kwargs["access"]},
    )
    monkeypatch.setattr(mod, "emit_engine_install_output", lambda *_a, **_k: None)
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

    result = await mod._run_engine_install_runtime_process(
        engine_id="demo",
        force=False,
        node_id="node-1",
        event_id="event-1",
        source_node_id=None,
    )

    assert result == {"config_updates": {"ok": True}}
    assert events[:3] == ["proxy_start", "spawn", "read"]
    assert events[-1] == "proxy_stop:session-1"
    assert fake_process.cleaned is True
    assert states == [
        {
            "subject_kind": "engine",
            "subject_name": "demo",
            "access": mod.get_engine_access("demo", "install", config={}),
        }
    ]


@pytest.mark.asyncio
async def test_engine_install_request_reuses_active_node_event_id(
    monkeypatch,
    engine_install_session,
):
    import democrai.core.application.ai.engine.install_events as mod

    stream_manager = _StreamManager()
    monkeypatch.setattr(mod, "app_ctx", lambda: _engine_install_app(stream_manager))
    _seed_node_status(
        engine_install_session,
        status="installing",
        event_id="active-event",
    )

    event = await mod.publish_engine_install_requested(engine_id="demo")

    assert event["event_id"] == "active-event"
    assert stream_manager.broadcasts[-1] == (mod.ENGINE_INSTALL_STREAM_ID, event)
    assert _node_event_id(engine_install_session) == "active-event"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["installed", "error"])
async def test_engine_install_request_generates_new_event_id_for_inactive_status(
    monkeypatch,
    engine_install_session,
    status,
):
    import democrai.core.application.ai.engine.install_events as mod

    stream_manager = _StreamManager()
    monkeypatch.setattr(mod, "app_ctx", lambda: _engine_install_app(stream_manager))
    _seed_node_status(
        engine_install_session,
        status=status,
        event_id="previous-event",
    )

    event = await mod.publish_engine_install_requested(engine_id="demo")

    assert event["event_id"] != "previous-event"
    assert _node_event_id(engine_install_session) == event["event_id"]
    assert stream_manager.broadcasts[-1] == (mod.ENGINE_INSTALL_STREAM_ID, event)


@pytest.mark.asyncio
async def test_engine_install_request_force_generates_new_event_id_when_installing(
    monkeypatch,
    engine_install_session,
):
    import democrai.core.application.ai.engine.install_events as mod

    stream_manager = _StreamManager()
    monkeypatch.setattr(mod, "app_ctx", lambda: _engine_install_app(stream_manager))
    _seed_node_status(
        engine_install_session,
        status="installing",
        event_id="active-event",
    )

    event = await mod.publish_engine_install_requested(engine_id="demo", force=True)

    assert event["event_id"] != "active-event"
    assert _node_event_id(engine_install_session) == event["event_id"]
    assert stream_manager.broadcasts[-1] == (mod.ENGINE_INSTALL_STREAM_ID, event)
