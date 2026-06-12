from __future__ import annotations

import asyncio
import importlib
import json
import os
import subprocess
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pytest


def _allowlist():
    return SimpleNamespace(
        endpoints=[
            SimpleNamespace(
                host="api.local",
                port=443,
                protocol="tcp",
                source="cfg",
                purpose="test",
            )
        ]
    )


def _import_helper_module(monkeypatch, tmp_path: Path):
    # Isolate helper imports from heavy runtime chains by stubbing direct deps.
    sandbox_pkg = ModuleType("democrai.core.infrastructure.sandbox")
    sandbox_pkg.__path__ = [str((Path(__file__).resolve().parents[2] / "democrai" / "core" / "infrastructure" / "sandbox").resolve())]
    os_pkg = ModuleType("democrai.core.infrastructure.sandbox.os")
    os_pkg.__path__ = [str((Path(__file__).resolve().parents[2] / "democrai" / "core" / "infrastructure" / "sandbox" / "os").resolve())]

    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.sandbox", sandbox_pkg)
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.sandbox.os", os_pkg)
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.platform.utils.debug",
        SimpleNamespace(debug_os_sandbox_flow=lambda *a, **k: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.foundation.app",
        SimpleNamespace(app_ctx=lambda: SimpleNamespace(config=None, runtime_mode="server", os_sandbox_helper_process=None, os_sandbox_helper_token="test-token")),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.foundation.paths",
        SimpleNamespace(
            data_dir=lambda: tmp_path,
            get_base_dir=lambda: str(tmp_path),
            is_frozen=lambda: False,
            logs_dir=lambda: tmp_path,
            runtime_ipc_dir=lambda: tmp_path,
            runtime_unix_socket_path=lambda filename: tmp_path / filename,
            state_dir=lambda: tmp_path,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.lifecycle.process_supervisor",
        SimpleNamespace(process_supervisor=SimpleNamespace(register=lambda *a, **k: None, unregister=lambda *a, **k: None, terminate=lambda *a, **k: None)),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.linux",
        SimpleNamespace(ensure_linux_network_enforcement_ready=lambda: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.os.models",
        SimpleNamespace(ApplicationNetworkAllowlist=object),
    )
    sys.modules.pop("democrai.core.infrastructure.sandbox.os.helper", None)
    return importlib.import_module("democrai.core.infrastructure.sandbox.os.helper")


@pytest.mark.posix_only
def test_helper_paths_and_payload(monkeypatch, tmp_path: Path):
    mod = _import_helper_module(monkeypatch, tmp_path)
    ctx = SimpleNamespace(config=None)
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(mod, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)
    monkeypatch.delenv(mod.OS_SANDBOX_HELPER_SOCKET_ENV, raising=False)
    monkeypatch.delenv(mod.OS_SANDBOX_POLICY_FILE_ENV, raising=False)
    monkeypatch.delenv(mod.OS_SANDBOX_HELPER_TOKEN_ENV, raising=False)

    def _assert_default_socket_path(path: str) -> None:
        if sys.platform == "darwin":
            assert path.endswith(f"dc-os-helper-{os.getpid()}.sock")
        else:
            assert path.endswith(f"os_sandbox_helper_{os.getpid()}.sock")

    socket_path = mod.get_os_sandbox_helper_socket_path()
    _assert_default_socket_path(socket_path)
    assert mod.get_os_sandbox_policy_file_path().endswith(
        f"os_sandbox_allowlist_{os.getpid()}.json"
    )
    assert mod.get_os_sandbox_helper_token() == ""
    assert mod.ensure_os_sandbox_helper_token()
    assert mod.get_os_sandbox_helper_token()
    assert mod.get_os_sandbox_refresh_seconds() == 60
    assert (
        mod.get_os_sandbox_refresh_seconds(
            config=SimpleNamespace(get=lambda *_a, **_k: "bad")
        )
        == 60
    )
    assert (
        mod.get_os_sandbox_refresh_seconds(
            config=SimpleNamespace(get=lambda *_a, **_k: 5)
        )
        == 5
    )

    cfg = SimpleNamespace(
        get=lambda key, default=None: {
            "sandbox.os.helper_socket": str(tmp_path / "x.sock"),
            "sandbox.os.policy_file": str(tmp_path / "x.json"),
        }.get(key, default)
    )
    assert mod.get_os_sandbox_helper_socket_path(cfg).endswith(
        f"x_{os.getpid()}.sock"
    )
    assert mod.get_os_sandbox_policy_file_path(cfg).endswith(
        f"x_{os.getpid()}.json"
    )
    cfg_template = SimpleNamespace(
        get=lambda key, default=None: {
            "sandbox.os.helper_socket": str(tmp_path / "x_{pid}.sock"),
            "sandbox.os.policy_file": str(tmp_path / "x_{pid}.json"),
        }.get(key, default)
    )
    assert mod.get_os_sandbox_helper_socket_path(cfg_template).endswith(
        f"x_{os.getpid()}.sock"
    )
    assert mod.get_os_sandbox_policy_file_path(cfg_template).endswith(
        f"x_{os.getpid()}.json"
    )
    cfg_empty = SimpleNamespace(
        get=lambda key, default=None: {
            "sandbox.os.helper_socket": "  ",
            "sandbox.os.policy_file": "",
        }.get(key, default)
    )
    _assert_default_socket_path(mod.get_os_sandbox_helper_socket_path(cfg_empty))
    assert mod.get_os_sandbox_policy_file_path(cfg_empty).endswith(
        f"os_sandbox_allowlist_{os.getpid()}.json"
    )

    monkeypatch.setenv(mod.OS_SANDBOX_HELPER_SOCKET_ENV, str(tmp_path / "inherited.sock"))
    monkeypatch.setenv(mod.OS_SANDBOX_POLICY_FILE_ENV, str(tmp_path / "inherited.json"))
    monkeypatch.setenv(mod.OS_SANDBOX_HELPER_TOKEN_ENV, "inherited-token")
    assert mod.get_os_sandbox_helper_socket_path(cfg_empty).endswith("inherited.sock")
    assert mod.get_os_sandbox_policy_file_path(cfg_empty).endswith("inherited.json")
    assert mod.get_os_sandbox_helper_token(cfg_empty) == "inherited-token"
    assert mod.get_os_sandbox_helper_socket_path(cfg).endswith("inherited.sock")
    assert mod.get_os_sandbox_policy_file_path(cfg).endswith("inherited.json")

    payload = mod._allowlist_to_payload(_allowlist())
    assert payload["endpoints"][0]["host"] == "api.local"

    with pytest.raises(RuntimeError, match="os_sandbox_policy_write_denied"):
        mod.write_os_sandbox_policy_file(_allowlist(), config=cfg)
    with mod._allow_os_sandbox_policy_write():
        policy_path = mod.write_os_sandbox_policy_file(_allowlist(), config=cfg)
    loaded = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    assert loaded["version"] == 1 and loaded["endpoints"][0]["host"] == "api.local"
    assert (Path(policy_path).stat().st_mode & 0o777) == 0o600


def test_helper_paths_are_per_process_but_inherited_by_children(tmp_path: Path):
    app_root = Path(__file__).resolve().parents[2]
    socket_config = str(tmp_path / "shared.sock")
    policy_config = str(tmp_path / "shared.json")
    code = f"""
import json
import os
from types import SimpleNamespace

from democrai.core.infrastructure.sandbox.os.helper import (
    OS_SANDBOX_HELPER_SOCKET_ENV,
    OS_SANDBOX_POLICY_FILE_ENV,
    get_os_sandbox_helper_socket_path,
    get_os_sandbox_policy_file_path,
)

config = SimpleNamespace(
    get=lambda key, default=None: {{
        "sandbox.os.helper_socket": {socket_config!r},
        "sandbox.os.policy_file": {policy_config!r},
    }}.get(key, default)
)
print(json.dumps({{
    "pid": os.getpid(),
    "socket": get_os_sandbox_helper_socket_path(config),
    "policy": get_os_sandbox_policy_file_path(config),
    "socket_env": os.environ.get(OS_SANDBOX_HELPER_SOCKET_ENV),
    "policy_env": os.environ.get(OS_SANDBOX_POLICY_FILE_ENV),
}}))
"""

    env = os.environ.copy()
    env.pop("DEMOCRAI_OS_SANDBOX_HELPER_SOCKET", None)
    env.pop("DEMOCRAI_OS_SANDBOX_POLICY_FILE", None)

    first = json.loads(
        subprocess.check_output(
            [sys.executable, "-c", code],
            cwd=app_root,
            env=env,
            text=True,
        )
    )
    second = json.loads(
        subprocess.check_output(
            [sys.executable, "-c", code],
            cwd=app_root,
            env=env,
            text=True,
        )
    )

    assert first["pid"] != second["pid"]
    assert first["socket"] != second["socket"]
    assert first["policy"] != second["policy"]
    assert first["socket"].endswith(f"shared_{first['pid']}.sock")
    assert first["policy"].endswith(f"shared_{first['pid']}.json")
    assert second["socket"].endswith(f"shared_{second['pid']}.sock")
    assert second["policy"].endswith(f"shared_{second['pid']}.json")

    inherited_env = env.copy()
    inherited_env["DEMOCRAI_OS_SANDBOX_HELPER_SOCKET"] = first["socket"]
    inherited_env["DEMOCRAI_OS_SANDBOX_POLICY_FILE"] = first["policy"]
    child = json.loads(
        subprocess.check_output(
            [sys.executable, "-c", code],
            cwd=app_root,
            env=inherited_env,
            text=True,
        )
    )

    assert child["pid"] != first["pid"]
    assert child["socket"] == first["socket"]
    assert child["policy"] == first["policy"]


@pytest.mark.posix_only
@pytest.mark.asyncio
async def test_request_helper_and_wait(monkeypatch):
    mod = _import_helper_module(monkeypatch, Path("/tmp"))
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    class _Reader:
        def __init__(self, raw: bytes):
            self.raw = raw

        async def readline(self):
            return self.raw

    class _Writer:
        def __init__(self):
            self.buffer = []
            self.closed = False

        def write(self, data):
            self.buffer.append(data)

        async def drain(self):
            return None

        def close(self):
            self.closed = True

        async def wait_closed(self):
            return None

    writer = _Writer()
    async def _open_conn_ok(_path):
        return _Reader(b'{"ok": true, "result": 1}\n'), writer

    monkeypatch.setattr(mod.asyncio, "open_unix_connection", _open_conn_ok)
    response = await mod._request_helper(socket_path="/tmp/x.sock", payload={"action": "ping"})
    assert response["ok"] is True and writer.closed is True

    async def _open_conn_empty(_path):
        return _Reader(b""), _Writer()

    monkeypatch.setattr(mod.asyncio, "open_unix_connection", _open_conn_empty)
    with pytest.raises(RuntimeError):
        await mod._request_helper(socket_path="/tmp/x.sock", payload={"action": "ping"})

    async def _open_conn_not_dict(_path):
        return _Reader(b"[]\n"), _Writer()

    monkeypatch.setattr(mod.asyncio, "open_unix_connection", _open_conn_not_dict)
    with pytest.raises(RuntimeError):
        await mod._request_helper(socket_path="/tmp/x.sock", payload={"action": "ping"})

    async def _open_conn_not_ok(_path):
        return _Reader(b'{"ok": false, "error": "no"}\n'), _Writer()

    monkeypatch.setattr(mod.asyncio, "open_unix_connection", _open_conn_not_ok)
    with pytest.raises(RuntimeError):
        await mod._request_helper(socket_path="/tmp/x.sock", payload={"action": "ping"})

    ctx = SimpleNamespace(os_sandbox_helper_process=SimpleNamespace(poll=lambda: 5))
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)
    with pytest.raises(RuntimeError):
        await mod._wait_for_helper_async("/tmp/x.sock")

    ctx2 = SimpleNamespace(os_sandbox_helper_process=None)
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx2)
    calls = {"n": 0}

    async def _request(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("retry")
        return {"ok": True}

    monkeypatch.setattr(mod, "_request_helper", _request)
    async def _sleep_fast(*_a, **_k):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _sleep_fast)
    await mod._wait_for_helper_async("/tmp/x.sock", timeout_seconds=1.0)


def test_helper_sync_and_commands(monkeypatch, tmp_path: Path):
    mod = _import_helper_module(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "get_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(mod, "get_os_sandbox_policy_file_path", lambda *_a, **_k: "/tmp/policy.json")
    monkeypatch.setattr(mod, "get_os_sandbox_refresh_seconds", lambda *_a, **_k: 11)
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    monkeypatch.setattr(mod, "is_frozen", lambda: False)
    monkeypatch.setattr(mod, "_installed_helper_script", lambda: "")
    prefix = mod._helper_module_command_prefix()
    assert prefix[0] == mod.sys.executable
    assert prefix[1].endswith("helper_entrypoint.py")
    monkeypatch.setattr(mod, "is_frozen", lambda: True)
    assert mod._helper_module_command_prefix() == [
        os.path.abspath(mod.sys.executable),
        "--os-sandbox-helper-process",
    ]

    cmd = mod._helper_command("/tmp/s.sock")
    assert "--os-sandbox-helper-socket" in cmd and "/tmp/s.sock" in cmd
    assert "test-token" not in mod._debug_helper_command(cmd)
    assert "<redacted>" in mod._debug_helper_command(cmd)
    assert mod._helper_command("/tmp/s.sock", privilege_prefix=("pkexec",))[0] == "pkexec"
    assert mod._helper_command("/tmp/s.sock", privilege_prefix=("sudo",))[0] == "sudo"

    import democrai.core.infrastructure.sandbox.os.linux.helper as linux_helper_mod
    from democrai.core.infrastructure.sandbox.os.linux.helper import LinuxHelperBackend
    from democrai.core.infrastructure.sandbox.os.macos.helper import MacOSHelperBackend
    from democrai.core.infrastructure.sandbox.os.windows.helper import (
        WindowsHelperBackend,
    )

    monkeypatch.setattr(
        linux_helper_mod, "ensure_linux_network_enforcement_ready", lambda: None
    )
    assert LinuxHelperBackend().can_autostart_directly() is True
    monkeypatch.setattr(
        linux_helper_mod,
        "ensure_linux_network_enforcement_ready",
        lambda: (_ for _ in ()).throw(RuntimeError("x")),
    )
    assert LinuxHelperBackend().can_autostart_directly() is False
    assert MacOSHelperBackend().can_autostart_directly() is True
    assert WindowsHelperBackend().can_autostart_directly() is True

    monkeypatch.setattr(mod.shutil, "which", lambda x: "/bin/x" if x in {"pkexec", "sudo"} else None)
    assert mod._can_pkexec_autostart_helper() is True
    assert mod._can_sudo_autostart_helper() is True

    monkeypatch.setattr(mod, "_can_autostart_helper", lambda: True)
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(runtime_mode="desktop"))
    assert mod._helper_autostart_strategy() == "direct"
    monkeypatch.setattr(mod, "_can_autostart_helper", lambda: False)
    monkeypatch.setattr(mod, "_can_pkexec_autostart_helper", lambda: True)
    assert mod._helper_autostart_strategy() == "pkexec"
    assert mod._helper_autostart_strategy(runtime_mode="server") == "sudo"
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(runtime_mode="server"))
    monkeypatch.setattr(mod, "_can_sudo_autostart_helper", lambda: True)
    assert mod._helper_autostart_strategy() == "sudo"
    monkeypatch.setattr(mod, "_can_sudo_autostart_helper", lambda: False)
    assert mod._helper_autostart_strategy() is None

    # _run_async_in_thread and _run_helper_request_sync paths
    assert mod._run_async_in_thread(lambda: asyncio.sleep(0, result={"ok": 1})) == {"ok": 1}
    with pytest.raises(RuntimeError):
        mod._run_async_in_thread(lambda: (_ for _ in ()).throw(RuntimeError("x")))

    monkeypatch.setattr(mod.asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError("no-loop")))

    def _run_and_close(coro):
        coro.close()
        return {"ok": True}

    monkeypatch.setattr(mod.asyncio, "run", _run_and_close)
    assert mod._run_helper_request_sync(socket_path="/tmp/s.sock", payload={"a": 1}) == {"ok": True}

    monkeypatch.setattr(mod.asyncio, "get_running_loop", lambda: object())
    monkeypatch.setattr(mod, "_run_async_in_thread", lambda _factory: {"ok": 2})
    assert mod._run_helper_request_sync(socket_path="/tmp/s.sock", payload={"a": 1}) == {"ok": 2}
    monkeypatch.setattr(mod, "_run_async_in_thread", lambda _factory: None)
    with pytest.raises(RuntimeError):
        mod._run_helper_request_sync(socket_path="/tmp/s.sock", payload={"a": 1})


def test_helper_process_tracking_and_start(monkeypatch, tmp_path: Path):
    mod = _import_helper_module(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(mod.process_supervisor, "terminate", lambda p: calls.append(("terminate", p)))
    monkeypatch.setattr(mod.process_supervisor, "unregister", lambda p: calls.append(("unregister", p)))
    monkeypatch.setattr(mod.process_supervisor, "register", lambda p, name=None: calls.append(("register", p, name)))

    ctx = SimpleNamespace(os_sandbox_helper_process=None, runtime_mode="server", config=None)
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)
    mod._stop_tracked_helper_process()

    proc = SimpleNamespace(poll=lambda: None, kill=lambda: calls.append(("kill",)))
    ctx.os_sandbox_helper_process = proc
    mod._stop_tracked_helper_process()
    assert any(c[0] == "terminate" for c in calls)
    assert ctx.os_sandbox_helper_process is None

    # terminate error -> kill fallback
    calls.clear()
    proc2 = SimpleNamespace(poll=lambda: None, kill=lambda: calls.append(("kill",)))
    ctx.os_sandbox_helper_process = proc2
    monkeypatch.setattr(
        mod.process_supervisor,
        "terminate",
        lambda _p: (_ for _ in ()).throw(RuntimeError("x")),
    )
    mod._stop_tracked_helper_process()
    assert ("kill",) in calls

    # cleanup socket branches
    path = tmp_path / "sock.sock"
    path.write_text("", encoding="utf-8")
    mod._cleanup_helper_socket(str(path))
    assert not path.exists()
    mod._cleanup_helper_socket("::bad::path::")

    # existing helper is reused.
    ctx.os_sandbox_helper_process = SimpleNamespace(poll=lambda: None)
    assert mod._start_os_sandbox_helper_process("/tmp/s.sock") is ctx.os_sandbox_helper_process

    ctx.os_sandbox_helper_process = None
    monkeypatch.setattr(mod, "_helper_autostart_strategy", lambda **_k: None)
    with pytest.raises(RuntimeError, match="os_sandbox_helper_autostart_unavailable"):
        mod._start_os_sandbox_helper_process("/tmp/s.sock")

    class _Popen:
        def __init__(self):
            self._poll = None

        def poll(self):
            return self._poll

    captured = {}

    def _popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _Popen()

    monkeypatch.setattr(mod.subprocess, "Popen", _popen)
    monkeypatch.setattr(mod, "_helper_autostart_strategy", lambda **_k: "direct")
    proc_started = mod._start_os_sandbox_helper_process("/tmp/s.sock")
    assert proc_started is ctx.os_sandbox_helper_process
    assert captured["kwargs"]["start_new_session"] is True

    ctx.os_sandbox_helper_process = None
    monkeypatch.setattr(mod, "_helper_autostart_strategy", lambda **_k: "pkexec")
    mod._start_os_sandbox_helper_process("/tmp/s.sock")
    assert "start_new_session" not in captured["kwargs"]
    assert captured["kwargs"]["stdin"] is mod.subprocess.DEVNULL

    ctx.os_sandbox_helper_process = None
    monkeypatch.setattr(mod, "_helper_autostart_strategy", lambda **_k: "sudo")
    monkeypatch.setattr(mod.sys, "platform", "linux")
    mod._start_os_sandbox_helper_process(
        "/tmp/s.sock",
        interactive=True,
        runtime_mode="server",
    )
    assert captured["kwargs"]["stdin"] is None

    monkeypatch.setattr(mod, "_stop_tracked_helper_process", lambda: calls.append(("stop",)))
    monkeypatch.setattr(mod, "_cleanup_helper_socket", lambda _p: calls.append(("cleanup",)))
    monkeypatch.setattr(mod, "_start_os_sandbox_helper_process", lambda _p, **_k: "started")
    assert mod._restart_os_sandbox_helper_process("/tmp/s.sock") == "started"
    assert ("stop",) in calls and ("cleanup",) in calls


@pytest.mark.asyncio
async def test_helper_ready_and_wait_remaining_branches(monkeypatch, tmp_path: Path):
    mod = _import_helper_module(monkeypatch, tmp_path)
    original_wait_fn = mod._wait_for_helper_async
    original_time_fn = mod.time.time

    monkeypatch.setattr(mod, "get_os_sandbox_helper_socket_path", lambda _cfg=None: "/tmp/sock.sock")
    async def _ok_req(**_k):
        return {"ok": True}
    monkeypatch.setattr(mod, "_request_helper", _ok_req)
    await mod._request_helper_ready_async()
    monkeypatch.setattr(mod, "_request_helper", lambda **_k: (_ for _ in ()).throw(FileNotFoundError("missing")))
    called = {"restart": 0, "wait": 0}
    monkeypatch.setattr(mod, "_helper_autostart_strategy", lambda **_k: "pkexec")
    monkeypatch.setattr(
        mod,
        "_restart_os_sandbox_helper_process",
        lambda _s, **_k: called.__setitem__("restart", called["restart"] + 1),
    )
    async def _wait(*_a, **_k):
        called["wait"] += 1
        return None
    monkeypatch.setattr(mod, "_wait_for_helper_async", _wait)
    await mod._request_helper_ready_async()
    assert called == {"restart": 1, "wait": 1}

    monkeypatch.setenv(mod.OS_SANDBOX_HELPER_SOCKET_ENV, "/tmp/inherited.sock")
    monkeypatch.setenv(mod.OS_SANDBOX_HELPER_TOKEN_ENV, "test-token")
    with pytest.raises(RuntimeError, match="os_sandbox_helper_not_running"):
        await mod._request_helper_ready_async()
    monkeypatch.delenv(mod.OS_SANDBOX_HELPER_SOCKET_ENV, raising=False)
    monkeypatch.delenv(mod.OS_SANDBOX_HELPER_TOKEN_ENV, raising=False)

    monkeypatch.setattr(mod, "_request_helper", lambda **_k: (_ for _ in ()).throw(ConnectionRefusedError("no")))
    monkeypatch.setattr(mod, "_helper_autostart_strategy", lambda **_k: "direct")
    await mod._request_helper_ready_async()

    monkeypatch.setenv(mod.OS_SANDBOX_HELPER_SOCKET_ENV, "/tmp/inherited.sock")
    monkeypatch.setenv(mod.OS_SANDBOX_HELPER_TOKEN_ENV, "test-token")
    with pytest.raises(RuntimeError, match="os_sandbox_helper_unreachable"):
        await mod._request_helper_ready_async()
    monkeypatch.delenv(mod.OS_SANDBOX_HELPER_SOCKET_ENV, raising=False)
    monkeypatch.delenv(mod.OS_SANDBOX_HELPER_TOKEN_ENV, raising=False)

    # _wait_for_helper_async remaining paths
    monkeypatch.setattr(mod, "_wait_for_helper_async", original_wait_fn)
    class _Proc:
        def poll(self):
            raise RuntimeError("poll err")

    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(os_sandbox_helper_process=_Proc()))
    steps = {"n": 0}
    async def _request_then_timeout(**_k):
        steps["n"] += 1
        raise RuntimeError("still no")
    monkeypatch.setattr(mod, "_request_helper", _request_then_timeout)
    original_sleep = mod.asyncio.sleep
    async def _fast_sleep(*_a, **_k):
        await original_sleep(0)
    monkeypatch.setattr(mod.asyncio, "sleep", _fast_sleep)

    times = iter([0.0, 0.05, 0.2])
    monkeypatch.setattr(mod.time, "time", lambda: next(times))
    with pytest.raises(RuntimeError, match="still no"):
        await mod._wait_for_helper_async("/tmp/s.sock", timeout_seconds=0.1)

    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(os_sandbox_helper_process=None))
    monkeypatch.setattr(mod, "_request_helper", lambda **_k: (_ for _ in ()).throw(RuntimeError("nope")))
    times2 = iter([0.0, 0.05, 0.2])
    monkeypatch.setattr(mod.time, "time", lambda: next(times2))
    with pytest.raises(RuntimeError, match="nope"):
        await mod._wait_for_helper_async("/tmp/s.sock", timeout_seconds=0.1)

    # explicit timeout without last_error
    monkeypatch.setattr(mod, "_request_helper", lambda **_k: {"ok": True})
    monkeypatch.setattr(mod.time, "time", original_time_fn)
    with pytest.raises(RuntimeError, match="os_sandbox_helper_wait_timeout"):
        await mod._wait_for_helper_async("/tmp/s.sock", timeout_seconds=-1.0)


def test_helper_sync_async_wrappers_and_apply_clear(monkeypatch, tmp_path: Path):
    mod = _import_helper_module(monkeypatch, tmp_path)
    original_run = mod.asyncio.run

    # ensure_os_sandbox_helper_ready branches
    monkeypatch.setattr(mod.asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError("no loop")))
    monkeypatch.setattr(mod.asyncio, "run", lambda coro: (coro.close(), None)[1])
    mod.ensure_os_sandbox_helper_ready()

    monkeypatch.setattr(mod.asyncio, "get_running_loop", lambda: object())
    called = {"thread": 0}
    monkeypatch.setattr(mod, "_run_async_in_thread", lambda _factory: called.__setitem__("thread", called["thread"] + 1))
    mod.ensure_os_sandbox_helper_ready()
    assert called["thread"] == 1

    # explicit async passthrough
    monkeypatch.setattr(mod.asyncio, "run", original_run)
    ran = {"n": 0}
    async def _ready(_cfg=None, *, interactive=False, runtime_mode=None):
        ran["n"] += 1
    monkeypatch.setattr(mod, "_request_helper_ready_async", _ready)
    asyncio.run(mod.ensure_os_sandbox_helper_ready_async())
    assert ran["n"] == 1

    # apply sync + clear sync wrappers
    allowlist = _allowlist()
    monkeypatch.setattr(mod.asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError("no loop")))
    monkeypatch.setattr(mod.asyncio, "run", lambda coro: (coro.close(), None)[1])
    mod.apply_application_network_allowlist_with_helper(allowlist, pid=10)
    mod.clear_application_network_allowlist_with_helper(pid=11)

    monkeypatch.setattr(mod.asyncio, "get_running_loop", lambda: object())
    thread_calls = {"n": 0}
    monkeypatch.setattr(mod, "_run_async_in_thread", lambda _factory: thread_calls.__setitem__("n", thread_calls["n"] + 1))
    mod.apply_application_network_allowlist_with_helper(allowlist, pid=10)
    mod.clear_application_network_allowlist_with_helper(pid=11)
    assert thread_calls["n"] == 2

    # async apply/clear bodies
    monkeypatch.setattr(mod.asyncio, "run", original_run)
    reqs = []
    policy_write_allowed = []
    monkeypatch.setattr(mod, "get_os_sandbox_helper_socket_path", lambda _cfg=None: "/tmp/hsock")
    def _write_policy(*_a, **_k):
        policy_write_allowed.append(mod._POLICY_WRITE_ALLOWED.get())
        return "/tmp/policy"
    monkeypatch.setattr(mod, "write_os_sandbox_policy_file", _write_policy)
    async def _ensure(_cfg=None):
        return None
    async def _req(**kwargs):
        reqs.append(kwargs)
        if kwargs["payload"]["action"] == "update_proxy_session":
            return {
                "ok": True,
                "session_id": kwargs["payload"]["session_id"],
                "proxy_url": "http://127.0.0.1:4123",
            }
        return {"ok": True}
    monkeypatch.setattr(mod, "ensure_os_sandbox_helper_ready_async", _ensure)
    monkeypatch.setattr(mod, "_request_helper", _req)
    asyncio.run(mod.apply_application_network_allowlist_with_helper_async(allowlist, pid=12))
    update_result = asyncio.run(
        mod.update_application_network_proxy_session_with_helper_async(
            "session-1",
            allowlist,
        )
    )
    asyncio.run(mod.clear_application_network_allowlist_with_helper_async(pid=13))
    assert policy_write_allowed == [True]
    assert reqs[0]["payload"]["action"] == "apply"
    assert reqs[1]["payload"]["action"] == "update_proxy_session"
    assert reqs[1]["payload"]["session_id"] == "session-1"
    assert update_result["session_id"] == "session-1"
    assert reqs[2]["payload"]["action"] == "clear"


def test_helper_cleanup_stop_start_remaining_branches(monkeypatch, tmp_path: Path):
    mod = _import_helper_module(monkeypatch, tmp_path)

    # cleanup resolve failure + unlink failure
    with monkeypatch.context() as m:
        m.setattr(mod.Path, "resolve", lambda self: (_ for _ in ()).throw(RuntimeError("resolve fail")))
        mod._cleanup_helper_socket("bad")

    p = tmp_path / "sock2.sock"
    p.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod.Path, "unlink", lambda self: (_ for _ in ()).throw(RuntimeError("unlink fail")))
    mod._cleanup_helper_socket(str(p))

    # stop tracked process kill failure branch
    class _P:
        def poll(self):
            return None

        def kill(self):
            raise RuntimeError("kill fail")

    ctx = SimpleNamespace(os_sandbox_helper_process=_P(), runtime_mode="server", config=None)
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(mod.process_supervisor, "terminate", lambda _p: (_ for _ in ()).throw(RuntimeError("term fail")))
    monkeypatch.setattr(mod.process_supervisor, "unregister", lambda _p: None)
    mod._stop_tracked_helper_process()
    assert ctx.os_sandbox_helper_process is None

    class _Proc:
        def poll(self):
            return None

    ctx.os_sandbox_helper_process = None
    monkeypatch.setattr(mod, "_helper_autostart_strategy", lambda **_k: "sudo")
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *_a, **_k: _Proc())
    out = mod._start_os_sandbox_helper_process("/tmp/s.sock")
    assert out is ctx.os_sandbox_helper_process


@pytest.mark.macos_only
def test_helper_backend_factory_and_platform_validation(monkeypatch):
    from democrai.core.infrastructure.sandbox.os import factory
    from democrai.core.infrastructure.sandbox.os.linux.helper import (
        LinuxHelperBackend,
    )
    from democrai.core.infrastructure.sandbox.os.macos.helper import (
        MacOSHelperBackend,
    )
    from democrai.core.infrastructure.sandbox.os.windows.helper import (
        WindowsHelperBackend,
    )

    assert isinstance(factory.get_helper_backend("linux"), LinuxHelperBackend)
    assert isinstance(factory.get_helper_backend("linux2"), LinuxHelperBackend)
    assert isinstance(factory.get_helper_backend("darwin"), MacOSHelperBackend)
    assert isinstance(factory.get_helper_backend("win32"), WindowsHelperBackend)
    assert factory.get_helper_backend("sunos").supports_pid_enforcement is False

    import democrai.core.infrastructure.sandbox.os.macos.helper as macos_helper_mod

    monkeypatch.setattr(macos_helper_mod.os, "getuid", lambda: 501)
    monkeypatch.setattr(macos_helper_mod.socket, "LOCAL_PEERCRED", 1, raising=False)

    class _MacOSSock:
        def __init__(self, uid: int):
            self.uid = uid
            self.calls = []

        def getsockopt(self, level, option, buflen):
            self.calls.append((level, option, buflen))
            return struct.pack("3i", 1, self.uid, 20)

    good_sock = _MacOSSock(501)
    writer = SimpleNamespace(
        get_extra_info=lambda name: good_sock if name == "socket" else None
    )
    backend = MacOSHelperBackend()
    assert backend.validate_client_and_target_pid(
        writer=writer,
        requested_pid=123,
        parent_pid=999,
    ) == 123
    assert good_sock.calls[0][1] == macos_helper_mod.socket.LOCAL_PEERCRED

    bad_writer = SimpleNamespace(
        get_extra_info=lambda name: _MacOSSock(999) if name == "socket" else None
    )
    with pytest.raises(RuntimeError, match="os_sandbox_helper_invalid_client_uid"):
        backend.validate_client_and_target_pid(
            writer=bad_writer,
            requested_pid=None,
            parent_pid=None,
        )

    portable = factory.get_helper_backend("other")
    assert portable.validate_client_and_target_pid(
        writer=SimpleNamespace(get_extra_info=lambda _name: None),
        requested_pid=77,
        parent_pid=1,
    ) == 77
    with pytest.raises(RuntimeError, match="network_enforcement_not_supported"):
        portable.apply([], pid=None)


@pytest.mark.posix_only
@pytest.mark.asyncio
async def test_helper_process_dispatch_uses_non_linux_backend(monkeypatch, tmp_path: Path):
    import democrai.core.infrastructure.sandbox.os.helper_process as helper_process
    from democrai.core.infrastructure.sandbox.os.factory import get_helper_backend

    class _Reader:
        def __init__(self, line: bytes):
            self.line = line

        async def readline(self):
            return self.line

    class _Writer:
        def __init__(self):
            self.buf = b""

        def write(self, data):
            self.buf += data

        async def drain(self):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    class _Proxy:
        async def start(self):
            return None

        def create_session(self, *, endpoints):
            return {
                "session_id": "session-1",
                "proxy_url": "http://127.0.0.1:1",
            }

        def update_session(self, session_id, *, endpoints):
            return {
                "session_id": session_id,
                "proxy_url": "http://127.0.0.1:1",
            }

        def stop_session(self, _session_id):
            return None

    backend = get_helper_backend("sunos")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"endpoints": []}), encoding="utf-8")
    policy.chmod(0o600)

    monkeypatch.setattr(
        helper_process,
        "ensure_linux_network_enforcement_ready",
        lambda: (_ for _ in ()).throw(AssertionError("linux readiness called")),
    )

    writer = _Writer()
    await helper_process._handle_helper_client(
        _Reader(b'{"action":"ping","token":"test-token"}\n'),
        writer,
        policy_file=str(policy),
        parent_pid=None,
        applied_pids=set(),
        applied_pids_lock=__import__("threading").Lock(),
        proxy=_Proxy(),
        token="test-token",
        backend=backend,
    )
    assert json.loads(writer.buf.decode("utf-8"))["ok"] is True

    writer = _Writer()
    await helper_process._handle_helper_client(
        _Reader(b'{"action":"start_proxy_session","endpoints":[],"token":"test-token"}\n'),
        writer,
        policy_file=str(policy),
        parent_pid=None,
        applied_pids=set(),
        applied_pids_lock=__import__("threading").Lock(),
        proxy=_Proxy(),
        token="test-token",
        backend=backend,
    )
    proxy_response = json.loads(writer.buf.decode("utf-8"))
    assert proxy_response["ok"] is True
    assert proxy_response["session_id"] == "session-1"

    writer = _Writer()
    await helper_process._handle_helper_client(
        _Reader(b'{"action":"apply","token":"test-token"}\n'),
        writer,
        policy_file=str(policy),
        parent_pid=None,
        applied_pids=set(),
        applied_pids_lock=__import__("threading").Lock(),
        proxy=_Proxy(),
        token="test-token",
        backend=backend,
    )
    apply_response = json.loads(writer.buf.decode("utf-8"))
    assert apply_response["ok"] is False
    assert "network_enforcement_not_supported:sunos" in apply_response["error"]
