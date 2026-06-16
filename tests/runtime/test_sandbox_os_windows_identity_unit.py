from __future__ import annotations

import os
from types import SimpleNamespace

from democrai.core.infrastructure.sandbox.os import launch_policy as lp
from democrai.core.infrastructure.sandbox.os.windows import low_integrity as li
from democrai.core.infrastructure.sandbox.os.windows import sandbox_host as sh


def test_host_path_and_real_interpreter_roundtrip(tmp_path):
    interp = str(tmp_path / "python.exe")
    host = sh._host_path_for(interp)
    assert sh.is_sandbox_host(host)
    assert not sh.is_sandbox_host(interp)
    assert os.path.normcase(sh.real_interpreter(host)) == os.path.normcase(interp)
    assert sh.real_interpreter(interp) == interp  # idempotent for non-host


def test_ensure_reuses_env_published_host(monkeypatch, tmp_path):
    existing = tmp_path / "python-democrai-sandbox.exe"
    existing.write_text("x", encoding="ascii")
    monkeypatch.setenv(sh.SANDBOX_HOST_ENV, str(existing))
    sh._cache.clear()
    assert sh.ensure_sandbox_host_executable(r"C:\anywhere\python.exe") == str(existing)


def test_ensure_creates_host_in_same_dir(monkeypatch, tmp_path):
    monkeypatch.delenv(sh.SANDBOX_HOST_ENV, raising=False)
    sh._cache.clear()
    interp = tmp_path / "python.exe"
    interp.write_bytes(b"MZ-fake-exe")
    host = sh.ensure_sandbox_host_executable(str(interp))
    assert sh.is_sandbox_host(host)
    assert os.path.exists(host)
    assert os.path.dirname(host) == str(tmp_path)  # same directory → venv resolution intact


def test_effective_command_deny_rewrites_and_enforces(monkeypatch):
    monkeypatch.setattr(
        li, "ensure_sandbox_host_executable", lambda interp: r"C:\v\python-democrai-sandbox.exe"
    )
    env: dict[str, str] = {}
    policy = SimpleNamespace(
        command=[r"C:\v\python.exe", "-m", "worker"],
        network_mode=lp.NETWORK_DENY,
        env=None,
    )
    command, enforce = li._effective_command(policy, env)
    assert enforce is True
    assert command[0].endswith("python-democrai-sandbox.exe")
    assert command[1:] == ["-m", "worker"]
    assert env[sh.SANDBOX_HOST_ENV] == command[0]


def test_effective_command_allow_all_dehosts(monkeypatch):
    monkeypatch.delenv(sh.SANDBOX_HOST_ENV, raising=False)
    env: dict[str, str] = {}
    host = r"C:\v\python-democrai-sandbox.exe"
    policy = SimpleNamespace(
        command=[host, "-m", "worker"],
        network_mode=lp.NETWORK_ALLOW_ALL,
        env=None,
    )
    command, enforce = li._effective_command(policy, env)
    assert enforce is False
    assert not sh.is_sandbox_host(command[0])  # mapped back to the real interpreter


def test_enforcement_endpoints_proxy_and_deny():
    proxy = SimpleNamespace(
        network_mode=lp.NETWORK_PROXY, env={"ALL_PROXY": "http://127.0.0.1:8888"}
    )
    endpoints = li._enforcement_endpoints(proxy)
    assert len(endpoints) == 1
    assert endpoints[0].port == 8888

    deny = SimpleNamespace(network_mode=lp.NETWORK_DENY, env=None)
    assert li._enforcement_endpoints(deny) == []


def test_elevation_module_imports_and_wrapper():
    from democrai.core.infrastructure.sandbox.os.windows import elevation

    proc = elevation.ElevatedProcess(handle=0, pid=4321)
    assert proc.pid == 4321
    assert proc.returncode is None
