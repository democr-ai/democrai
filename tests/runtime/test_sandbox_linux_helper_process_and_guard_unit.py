from __future__ import annotations

import asyncio
import builtins
import concurrent.futures
import contextlib
import importlib
import io
import json
import os
import pathlib
import socket
import stat
import struct
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _reset_process_guard_between_tests():
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")

    def _reset():
        # These tests exercise the process guard patch/unpatch machinery directly.
        # Always restore process-wide monkeypatches before the next test, otherwise
        # pytest internals can be intercepted by a stale guard state.
        try:
            mod.disable_process_guard(None)
        except Exception:
            pass
        mod._ACTIVE = False
        mod._ACTIVE_COUNT = 0
        mod._STATE.set(None)
        mod._PATH_CHECK_DEPTH.set(0)
        mod._EXTERNAL_ACCESS_CACHE.set(None)
        mod._clear_path_resolution_caches()

    _reset()
    yield
    _reset()


def _access_rule(mod, subject_kind: str, subject: str, resource_type: str, operation: str, target: str):
    return mod.AccessManifestRule(
        subject=mod.AccessSubject.create(subject_kind, subject),
        resource=mod.AccessResource.create(
            resource_type=resource_type,
            operation=operation,
            target=target,
        ),
    )


def _guard_state(mod, rules, *, subject: str = "s", subject_kind: str = "module"):
    access = tuple(rules or ())
    filesystem_access = mod._filesystem_access_by_operation(access)
    return {
        "access": access,
        "filesystem_access": filesystem_access,
        "filesystem_access_fingerprint": mod._filesystem_access_fingerprint(filesystem_access),
        "filesystem_access_index": mod._filesystem_access_index(filesystem_access),
        "subject": subject,
        "subject_kind": subject_kind,
    }


@pytest.mark.linux_only
def test_sandbox_launcher_uses_wrapper_when_os_sandbox_enabled(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.launcher")
    guard_mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(config=SimpleNamespace(get=lambda key, default=None: key == "sandbox.os.enabled")),
    )

    token = guard_mod._STATE.set(
        {
            "access": (
                _access_rule(guard_mod, "module", "demo", "filesystem", "read", str(tmp_path)),
            )
        }
    )
    calls = []
    applied = []

    class _Proc:
        pid = 1234
        returncode = 0

        def communicate(self, input=None, timeout=None):
            return "ok", ""

        def poll(self):
            return 0

    def _popen(cmd, **kwargs):
        policy_path = Path(cmd[-1])
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
        calls.append((cmd, kwargs, payload))
        return _Proc()

    monkeypatch.setattr(mod.subprocess, "Popen", _popen)
    monkeypatch.setattr(mod, "_apply_launch_network_policy", lambda policy, pid: applied.append((policy, pid)))
    try:
        out = mod.run_subprocess(["echo", "ok"], env={"A": "B"})
    finally:
        guard_mod._STATE.reset(token)

    assert out.returncode == 0
    assert calls[0][0][:3] == [sys.executable, "-m", "democrai.core.infrastructure.sandbox.launcher"]
    assert calls[0][2]["command"] == ["echo", "ok"]
    assert calls[0][2]["filesystem_access"][0]["target"] == str(tmp_path)
    assert applied[0][1] == 1234
    assert "DEMOCRAI_OS_SANDBOX_HELPER_SOCKET" in calls[0][1]["env"]
    assert "DEMOCRAI_OS_SANDBOX_POLICY_FILE" in calls[0][1]["env"]
    assert "DEMOCRAI_OS_SANDBOX_HELPER_SOCKET" not in calls[0][2]["env"]
    assert "DEMOCRAI_OS_SANDBOX_POLICY_FILE" not in calls[0][2]["env"]


@pytest.mark.linux_only
def test_process_guard_popen_launcher_releases_ready_file_under_bypass(monkeypatch, tmp_path: Path):
    guard_mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    launcher_mod = importlib.import_module("democrai.core.infrastructure.sandbox.launcher")

    monkeypatch.setattr(launcher_mod, "_os_sandbox_enabled", lambda: True)
    monkeypatch.setattr(launcher_mod, "_with_os_sandbox_helper_env", lambda env: dict(env or {}))
    monkeypatch.setattr(launcher_mod, "_without_os_sandbox_helper_env", lambda env: dict(env or {}))
    monkeypatch.setattr(
        launcher_mod,
        "_prepare_policy_for_launch",
        lambda policy, env: (policy, "", ""),
    )
    ready_file = tmp_path / "launch.ready"
    monkeypatch.setattr(launcher_mod, "_new_launch_ready_file", lambda: ready_file)

    def _write_policy(policy):
        path = tmp_path / "policy.json"
        path.write_text(json.dumps(policy.to_dict()), encoding="utf-8")
        return path

    monkeypatch.setattr(launcher_mod, "_write_policy", _write_policy)
    checks = []

    def _apply_launch_network_policy(_policy, _pid):
        checks.append(("apply", guard_mod._bypass_enabled()))

    def _release_launch_ready_file(path):
        checks.append(("release", guard_mod._bypass_enabled()))
        path.write_text("ready\n", encoding="ascii")

    monkeypatch.setattr(launcher_mod, "_apply_launch_network_policy", _apply_launch_network_policy)
    monkeypatch.setattr(launcher_mod, "_release_launch_ready_file", _release_launch_ready_file)

    class _Proc:
        pid = 1234

    def _original(*args, **kwargs):
        checks.append(("original", args[0][1:3]))
        return _Proc()

    token = guard_mod._STATE.set(
        _guard_state(
            guard_mod,
            (
                _access_rule(
                    guard_mod,
                    "skill",
                    "demo",
                    "filesystem",
                    "execute",
                    sys.executable,
                ),
            ),
            subject="demo",
            subject_kind="skill",
        )
    )
    try:
        proc = guard_mod._run_subprocess_via_launcher(
            _original,
            ([sys.executable, "-c", "print('ok')"],),
            {"env": {}, "text": True},
            call_name="subprocess.Popen",
            cleanup_policy=False,
        )
    finally:
        guard_mod._STATE.reset(token)

    assert proc.pid == 1234
    assert ("apply", True) in checks
    assert ("release", True) in checks
    assert ready_file.read_text(encoding="ascii") == "ready\n"


def test_linux_helpers_and_apply_clear(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.linux.network")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    called = {}

    def _run(cmd, check=False, capture_output=True, text=True):
        called["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="-A OUTPUT -m cgroup --path a/b -j CHAIN\n", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", _run)
    out = mod._run_command(["echo", "x"])
    assert out.returncode == 0 and called["cmd"] == ["echo", "x"]

    monkeypatch.setattr(mod.shutil, "which", lambda x: "/usr/bin/" + x if x == "ok" else None)
    assert mod._require_command("ok").endswith("/ok")
    with pytest.raises(RuntimeError):
        mod._require_command("missing")

    cgroup_root = tmp_path / "cgroup"
    cgroup_root.mkdir()
    monkeypatch.setattr(mod, "_CGROUP_ROOT", cgroup_root)
    with pytest.raises(RuntimeError):
        mod._ensure_cgroup_root()
    (cgroup_root / "cgroup.controllers").write_text("x", encoding="utf-8")
    mod._ensure_cgroup_root()

    pstatus = tmp_path / "proc.txt"
    pstatus.write_text("0::/user.slice\n", encoding="utf-8")
    real_path_read_text = Path.read_text
    monkeypatch.setattr(
        mod.Path,
        "read_text",
        lambda self, encoding="utf-8": pstatus.read_text(encoding="utf-8")
        if str(self).endswith("/cgroup")
        else real_path_read_text(self, encoding=encoding),
    )
    assert mod._read_process_cgroup_relative_path(1) == "user.slice"
    monkeypatch.setattr(mod.Path, "read_text", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        mod._read_process_cgroup_relative_path(1)
    monkeypatch.setattr(mod.Path, "read_text", lambda *_a, **_k: "1:name:/x\n")
    with pytest.raises(RuntimeError):
        mod._read_process_cgroup_relative_path(1)
    monkeypatch.setattr(mod.Path, "read_text", real_path_read_text)

    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _pid: "")
    assert mod._cgroup_relative_path(10).endswith("democrai_os_sandbox_10")
    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _pid: "root")
    assert "root" in mod._cgroup_relative_path(10)

    base = cgroup_root / "root"
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _pid: "root")
    assert mod._process_cgroup_base_path(1) == base
    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _pid: "missing")
    with pytest.raises(RuntimeError):
        mod._process_cgroup_base_path(1)

    monkeypatch.setattr(mod, "_ensure_cgroup_root", lambda: None)
    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _pid: "x/democrai_os_sandbox_99")
    assert mod._ensure_process_cgroup(99) == "x/democrai_os_sandbox_99"
    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _pid: "x")
    root = cgroup_root / "x"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "_CGROUP_ROOT", cgroup_root)
    assert mod._ensure_process_cgroup(99).endswith("democrai_os_sandbox_99")

    class _BadMkdirPath(Path):
        _flavour = type(Path())._flavour

        def mkdir(self, *a, **k):
            raise PermissionError("denied")

    monkeypatch.setattr(mod, "_CGROUP_ROOT", _BadMkdirPath(str(cgroup_root)))
    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _pid: "")
    with pytest.raises(RuntimeError):
        mod._ensure_process_cgroup(99)

    monkeypatch.setattr(mod, "_CGROUP_ROOT", cgroup_root)
    real_write = Path.write_text

    def _write_fail(self, text, encoding="utf-8"):
        if str(self).endswith("cgroup.procs"):
            raise PermissionError("x")
        return real_write(self, text, encoding=encoding)

    monkeypatch.setattr(Path, "write_text", _write_fail)
    with pytest.raises(RuntimeError):
        mod._ensure_process_cgroup(100)
    monkeypatch.setattr(Path, "write_text", real_write)

    ep = SimpleNamespace(host="h", port=1, protocol="tcp")
    assert mod._resolve_endpoint_values(ep) == ("h", 1, "tcp")
    assert mod._resolve_endpoint_values({"host": "h2", "port": 2, "protocol": "udp"}) == (
        "h2",
        2,
        "udp",
    )

    with pytest.raises(RuntimeError):
        mod._resolve_endpoint_addresses({"host": "*.x", "port": 1, "protocol": "tcp"})
    monkeypatch.setattr(mod.socket, "getaddrinfo", lambda *_a, **_k: (_ for _ in ()).throw(socket.gaierror(1)))
    with pytest.raises(RuntimeError):
        mod._resolve_endpoint_addresses({"host": "x", "port": 1, "protocol": "tcp"})

    monkeypatch.setattr(
        mod.socket,
        "getaddrinfo",
        lambda *_a, **_k: [
            (socket.AF_INET, None, None, None, ("1.1.1.1", 1)),
            (socket.AF_INET6, None, None, None, ("::1", 1, 0, 0)),
        ],
    )
    v4, v6 = mod._resolve_endpoint_addresses({"host": "x", "port": 1, "protocol": "udp"})
    assert "1.1.1.1" in v4 and "::1" in v6

    monkeypatch.setattr(mod, "_run_command", lambda cmd: SimpleNamespace(returncode=1, stderr="err", stdout=""))
    with pytest.raises(RuntimeError):
        mod._run_iptables(["iptables", "-L"])
    mod._best_effort_iptables(["iptables", "-L"])

    calls = []
    monkeypatch.setattr(mod, "_best_effort_iptables", lambda cmd: calls.append(("best", cmd)))
    monkeypatch.setattr(mod, "_run_iptables", lambda cmd: calls.append(("run", cmd)))
    monkeypatch.setattr(mod, "_run_command", lambda cmd: SimpleNamespace(returncode=0, stderr="", stdout=""))
    mod._delete_output_jump("iptables", "c/p", "C")
    mod._create_chain("iptables", "C")
    mod._append_rule("iptables", ["C", "-j", "RETURN"])
    mod._insert_rule("iptables", ["OUTPUT", "1", "-j", "C"])
    assert calls
    assert mod._chain_names(7) == ("DEMOCRAI_OS_7_A", "DEMOCRAI_OS_7_B")

    monkeypatch.setattr(mod, "_run_command", lambda cmd: SimpleNamespace(returncode=0, stdout="-A OUTPUT -m cgroup --path a/b -j X", stderr=""))
    assert mod._list_output_rules("iptables") == ["-A OUTPUT -m cgroup --path a/b -j X"]
    monkeypatch.setattr(mod, "_run_command", lambda cmd: SimpleNamespace(returncode=1, stdout="", stderr="err"))
    with pytest.raises(RuntimeError):
        mod._list_output_rules("iptables")

    monkeypatch.setattr(mod, "_list_output_rules", lambda _cmd: ["-A OUTPUT -m cgroup --path grp -j DEMOCRAI_OS_1_A"])
    assert mod._find_active_chain("iptables", cgroup_path="grp", candidates=("DEMOCRAI_OS_1_A", "DEMOCRAI_OS_1_B")) == "DEMOCRAI_OS_1_A"
    monkeypatch.setattr(mod, "_list_output_rules", lambda _cmd: ["-A OUTPUT -j OTHER"])
    assert mod._find_active_chain("iptables", cgroup_path="grp", candidates=("A", "B")) is None

    calls.clear()
    monkeypatch.setattr(mod, "_find_active_chain", lambda *_a, **_k: "DEMOCRAI_OS_5_A")
    monkeypatch.setattr(mod, "_delete_output_jump", lambda *a, **k: calls.append(("del", a)))
    monkeypatch.setattr(mod, "_create_chain", lambda *a, **k: calls.append(("new", a)))
    monkeypatch.setattr(mod, "_append_rule", lambda *a, **k: calls.append(("app", a)))
    monkeypatch.setattr(mod, "_insert_rule", lambda *a, **k: calls.append(("ins", a)))
    monkeypatch.setattr(mod, "_best_effort_iptables", lambda cmd: calls.append(("best", cmd)))
    mod._install_chain(
        iptables_cmd="iptables",
        pid=5,
        cgroup_path="grp",
        loopback_destination="127.0.0.0/8",
        allowed_addresses={"tcp": {443: {"1.1.1.1"}}},
    )
    assert any(item[0] == "ins" for item in calls)

    resolv = tmp_path / "resolv.conf"
    resolv.write_text("nameserver 8.8.8.8\n#x\nnameserver ::1\n", encoding="utf-8")
    real_exists = Path.exists
    real_read = Path.read_text
    monkeypatch.setattr(
        mod.Path,
        "exists",
        lambda self: True if str(self) == "/etc/resolv.conf" else real_exists(self),
    )
    monkeypatch.setattr(
        mod.Path,
        "read_text",
        lambda self, encoding="utf-8": real_read(resolv, encoding=encoding)
        if str(self) == "/etc/resolv.conf"
        else real_read(self, encoding=encoding),
    )
    dns_eps = mod._system_dns_endpoints()
    assert len(dns_eps) == 4
    monkeypatch.setattr(
        mod.Path,
        "read_text",
        lambda self, encoding="utf-8": (_ for _ in ()).throw(RuntimeError("x"))
        if str(self) == "/etc/resolv.conf"
        else real_read(self, encoding=encoding),
    )
    assert mod._system_dns_endpoints() == []

    monkeypatch.setattr(mod, "_resolve_endpoint_addresses", lambda ep: ({"1.1.1.1"}, {"::1"}))
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)
    ipv4, ipv6 = mod._build_address_maps_from_endpoints(
        [
            {"host": "a", "port": 443, "protocol": "tcp"},
            {"host": "*.a", "port": 443, "protocol": "tcp"},
            {"host": "a", "port": 53, "protocol": "udp"},
            {"host": "a", "port": 1, "protocol": "other"},
        ]
    )
    assert 443 in ipv4["tcp"] and 53 in ipv6["udp"]
    monkeypatch.setattr(mod, "_system_dns_endpoints", lambda: [{"host": "dns", "port": 53, "protocol": "udp"}])
    monkeypatch.setattr(mod, "_resolve_endpoint_addresses", lambda ep: ({"2.2.2.2"}, set()))
    maps = mod._build_address_maps(SimpleNamespace(endpoints=[{"host": "a", "port": 443, "protocol": "tcp"}]))
    assert maps[0]["tcp"][443] == {"2.2.2.2"}

    calls.clear()
    monkeypatch.setattr(mod, "_run_iptables", lambda cmd: calls.append(("run", cmd)))
    monkeypatch.setattr(mod, "_delete_output_jump", lambda *a, **k: calls.append(("del", a)))
    monkeypatch.setattr(mod, "_best_effort_iptables", lambda cmd: calls.append(("best", cmd)))
    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _pid: "grp")
    mod._probe_cgroup_path_match("iptables", pid=9)
    assert calls

    monkeypatch.setattr(mod.sys, "platform", "darwin")
    assert mod.is_linux_network_enforcement_supported() is False
    monkeypatch.setattr(mod.sys, "platform", "linux")
    cgroup_root = tmp_path / "cg2"
    cgroup_root.mkdir()
    monkeypatch.setattr(mod, "_CGROUP_ROOT", cgroup_root)
    assert mod.is_linux_network_enforcement_supported() is False
    (cgroup_root / "cgroup.controllers").write_text("x", encoding="utf-8")
    monkeypatch.setattr(mod.shutil, "which", lambda x: "/bin/" + x)
    assert mod.is_linux_network_enforcement_supported() is True

    monkeypatch.setattr(mod, "is_linux_network_enforcement_supported", lambda: False)
    with pytest.raises(RuntimeError):
        mod.ensure_linux_network_enforcement_ready()
    monkeypatch.setattr(mod, "is_linux_network_enforcement_supported", lambda: True)
    monkeypatch.setattr(mod, "_require_command", lambda n: n)
    monkeypatch.setattr(mod, "_probe_cgroup_path_match", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        mod.ensure_linux_network_enforcement_ready()
    called_probe = {"n": 0}

    def _probe_ok(*_a, **_k):
        called_probe["n"] += 1
        if called_probe["n"] == 2:
            return None
        return None

    monkeypatch.setattr(mod, "_probe_cgroup_path_match", _probe_ok)
    mod.ensure_linux_network_enforcement_ready()

    monkeypatch.setattr(mod, "is_linux_network_enforcement_supported", lambda: False)
    with pytest.raises(RuntimeError):
        mod.apply_application_network_allowlist(SimpleNamespace(endpoints=[]), pid=1)
    with pytest.raises(RuntimeError):
        mod.apply_application_network_endpoints([], pid=1)
    with pytest.raises(RuntimeError):
        mod.clear_application_network_allowlist(pid=1)

    monkeypatch.setattr(mod, "is_linux_network_enforcement_supported", lambda: True)
    monkeypatch.setattr(mod, "_current_pid", lambda p: 77)
    monkeypatch.setattr(mod, "_require_command", lambda n: n)
    monkeypatch.setattr(mod, "_ensure_process_cgroup", lambda p: "grp")
    monkeypatch.setattr(mod, "_chain_name", lambda p: "CHAIN")
    monkeypatch.setattr(mod, "_build_address_maps", lambda a: ({"tcp": {443: {"1.1.1.1"}}}, {"tcp": {443: {"::1"}}}))
    calls.clear()
    monkeypatch.setattr(mod, "_install_chain", lambda **k: calls.append(k))
    mod.apply_application_network_allowlist(SimpleNamespace(endpoints=[1]), pid=1)
    assert len(calls) == 2

    monkeypatch.setattr(mod, "_build_address_maps_from_endpoints", lambda eps: ({"udp": {53: {"1.1.1.1"}}}, {}))
    mod.apply_application_network_endpoints([{"host": "x", "port": 53, "protocol": "udp"}], pid=1)

    calls.clear()
    monkeypatch.setattr(mod, "_chain_names", lambda _p: ("A", "B"))
    monkeypatch.setattr(mod, "_read_process_cgroup_relative_path", lambda _p: "grp")
    monkeypatch.setattr(mod, "_delete_output_jump", lambda *a, **k: calls.append(("del", a)))
    monkeypatch.setattr(mod, "_best_effort_iptables", lambda cmd: calls.append(("best", cmd)))
    mod.clear_application_network_allowlist(pid=1)
    assert calls


def test_linux_create_chain_tolerates_existing_chain(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.linux.network")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    calls = []

    def _run_command(cmd):
        calls.append(cmd)
        if cmd == ["iptables", "-N", "C"]:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="iptables: Chain already exists.",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mod, "_run_command", _run_command)

    mod._create_chain("iptables", "C")

    assert calls.count(["iptables", "-F", "C"]) == 2
    assert ["iptables", "-X", "C"] in calls
    assert ["iptables", "-N", "C"] in calls


def test_linux_create_chain_still_raises_other_create_errors(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.linux.network")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    def _run_command(cmd):
        if cmd == ["iptables", "-N", "C"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="permission denied")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mod, "_run_command", _run_command)

    with pytest.raises(RuntimeError, match="permission denied"):
        mod._create_chain("iptables", "C")


def test_linux_apply_network_allowlist_runs_under_apply_lock(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.linux.network")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    state = {"locked": False}

    class Lock:
        def __enter__(self):
            state["locked"] = True

        def __exit__(self, *_args):
            state["locked"] = False

    def _install_chain(**_kwargs):
        assert state["locked"] is True

    monkeypatch.setattr(mod, "_NETWORK_APPLY_LOCK", Lock())
    monkeypatch.setattr(mod, "is_linux_network_enforcement_supported", lambda: True)
    monkeypatch.setattr(mod, "_require_command", lambda name: name)
    monkeypatch.setattr(mod, "_ensure_process_cgroup", lambda _pid: "grp")
    monkeypatch.setattr(mod, "_build_address_maps", lambda _allowlist: ({}, {}))
    monkeypatch.setattr(mod, "_install_chain", _install_chain)

    mod.apply_application_network_allowlist(SimpleNamespace(endpoints=[]), pid=1)


@pytest.mark.asyncio
async def test_helper_process_all_paths(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.helper_process")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "1001")
    assert mod._socket_owner_ids() == (1000, 1001)
    monkeypatch.setenv("SUDO_UID", "")
    assert mod._socket_owner_ids() is None
    monkeypatch.setenv("SUDO_UID", "bad")
    assert mod._socket_owner_ids() is None

    monkeypatch.setenv("SUDO_UID", "1000")
    assert mod._expected_client_uid() == 1000
    monkeypatch.setenv("SUDO_UID", "bad")
    monkeypatch.setattr(mod.os, "getuid", lambda: 42)
    assert mod._expected_client_uid() == 42

    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"endpoints": [{"host": "x", "port": 1, "protocol": "tcp"}, "x"]}), encoding="utf-8")
    os.chmod(policy, 0o600)
    monkeypatch.setenv("SUDO_UID", "")
    monkeypatch.setattr(mod.os, "getuid", lambda: os.stat(policy).st_uid)
    loaded = mod._load_endpoints_from_policy_file(str(policy))
    assert loaded and loaded[0]["host"] == "x"

    with pytest.raises(RuntimeError):
        mod._load_endpoints_from_policy_file(str(tmp_path / "missing.json"))
    monkeypatch.setattr(mod, "_expected_client_uid", lambda: 999999)
    with pytest.raises(RuntimeError):
        mod._load_endpoints_from_policy_file(str(policy))
    monkeypatch.setattr(mod, "_expected_client_uid", lambda: os.stat(policy).st_uid)
    os.chmod(policy, 0o666)
    with pytest.raises(RuntimeError):
        mod._load_endpoints_from_policy_file(str(policy))
    os.chmod(policy, 0o600)
    policy.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError):
        mod._load_endpoints_from_policy_file(str(policy))
    policy.write_text(json.dumps({"x": 1}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        mod._load_endpoints_from_policy_file(str(policy))

    class _Sock:
        def getsockopt(self, *_a, **_k):
            return struct.pack("3i", 123, 1000, 1000)

    writer = SimpleNamespace(get_extra_info=lambda name: _Sock() if name == "socket" else None)
    assert mod._peer_credentials(writer) == (123, 1000, 1000)
    with pytest.raises(RuntimeError):
        mod._peer_credentials(SimpleNamespace(get_extra_info=lambda _n: None))

    status = tmp_path / "status"
    status.write_text("PPid:\t2\n", encoding="utf-8")
    real_path_read_text = Path.read_text
    monkeypatch.setattr(
        mod.Path,
        "read_text",
        lambda self, encoding="utf-8": real_path_read_text(status, encoding="utf-8")
        if str(self).endswith("/status")
        else real_path_read_text(self, encoding=encoding),
    )
    assert mod._parent_pid_of(10) == 2
    monkeypatch.setattr(mod.Path, "read_text", lambda *_a, **_k: "PPid: bad\n")
    assert mod._parent_pid_of(10) is None
    monkeypatch.setattr(mod.Path, "read_text", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    assert mod._parent_pid_of(10) is None

    parents = {5: 3, 3: 1}
    monkeypatch.setattr(mod, "_parent_pid_of", lambda pid: parents.get(pid))
    assert mod._is_same_or_descendant(5, 3) is True
    assert mod._is_same_or_descendant(5, 4) is False

    monkeypatch.setattr(mod, "_peer_credentials", lambda _w: (100, 2000, 1))
    monkeypatch.setattr(mod, "_expected_client_uid", lambda: 1000)
    with pytest.raises(RuntimeError):
        mod._validate_client_and_target_pid(writer=writer, requested_pid=None, parent_pid=None)
    monkeypatch.setattr(mod, "_peer_credentials", lambda _w: (100, 1000, 1))
    monkeypatch.setattr(mod, "_expected_client_uid", lambda: 1000)
    monkeypatch.setattr(mod, "_is_same_or_descendant", lambda p, r: False)
    with pytest.raises(RuntimeError):
        mod._validate_client_and_target_pid(writer=writer, requested_pid=None, parent_pid=50)
    monkeypatch.setattr(mod, "_is_same_or_descendant", lambda p, r: p == 100 and r == 50)
    with pytest.raises(RuntimeError):
        mod._validate_client_and_target_pid(writer=writer, requested_pid=12, parent_pid=50)
    monkeypatch.setattr(mod, "_is_same_or_descendant", lambda p, r: p in {12, 100} and r == 50)
    with pytest.raises(RuntimeError):
        mod._validate_client_and_target_pid(writer=writer, requested_pid=999, parent_pid=50)
    assert mod._validate_client_and_target_pid(writer=writer, requested_pid=12, parent_pid=50) == 12
    assert mod._validate_client_and_target_pid(writer=writer, requested_pid=None, parent_pid=None) is None

    monkeypatch.setattr(mod.os, "kill", lambda *_a, **_k: (_ for _ in ()).throw(ProcessLookupError()))
    assert mod._parent_pid_is_alive(1) is False
    monkeypatch.setattr(mod.os, "kill", lambda *_a, **_k: (_ for _ in ()).throw(PermissionError()))
    assert mod._parent_pid_is_alive(1) is True
    monkeypatch.setattr(mod.os, "kill", lambda *_a, **_k: None)
    assert mod._parent_pid_is_alive(1) is True

    assert mod._open_parent_pidfd(None) is None
    assert mod._open_parent_pidfd(1) is None
    monkeypatch.delattr(mod.os, "pidfd_open", raising=False)
    assert mod._open_parent_pidfd(10) is None
    monkeypatch.setattr(
        mod.os,
        "pidfd_open",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")),
        raising=False,
    )
    assert mod._open_parent_pidfd(10) is None
    monkeypatch.setattr(mod.os, "pidfd_open", lambda *_a, **_k: 9, raising=False)
    assert mod._open_parent_pidfd(10) == 9

    # parent watchdog with pidfd
    exits = []
    monkeypatch.setattr(mod, "_open_parent_pidfd", lambda _p: 7)

    class _Poll:
        def register(self, *_a, **_k):
            return None

        def poll(self):
            return [(7, 1)]

    monkeypatch.setattr(mod.select, "poll", lambda: _Poll())
    monkeypatch.setattr(mod.os, "close", lambda _fd: None)
    monkeypatch.setattr(mod.os, "_exit", lambda code: exits.append(code) or (_ for _ in ()).throw(SystemExit(code)))

    class _Thread:
        def __init__(self, target, **_k):
            self.target = target

        def start(self):
            try:
                self.target()
            except (SystemExit, RuntimeError):
                pass

    monkeypatch.setattr(mod.threading, "Thread", _Thread)
    mod._start_parent_watchdog(50)
    assert exits and exits[-1] == 0

    # parent watchdog without pidfd
    exits.clear()
    monkeypatch.setattr(mod, "_open_parent_pidfd", lambda _p: None)
    alive = {"n": 0}
    monkeypatch.setattr(mod, "_parent_pid_is_alive", lambda _p: False if alive.update(n=alive["n"] + 1) or alive["n"] > 0 else True)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    mod._start_parent_watchdog(50)
    assert exits and exits[-1] == 0
    mod._start_parent_watchdog(None)
    mod._start_parent_watchdog(1)

    # policy refresh watchdog
    applied_pids: set[int] = set()
    lock = threading.Lock()
    mod._start_policy_refresh_watchdog(
        policy_file=str(policy),
        refresh_seconds=0,
        applied_pids=applied_pids,
        applied_pids_lock=lock,
    )
    steps = {"n": 0}
    monkeypatch.setattr(mod, "_load_endpoints_from_policy_file", lambda _p: [{"host": "x", "port": 1, "protocol": "tcp"}])
    monkeypatch.setattr(mod, "apply_application_network_endpoints", lambda *_a, **_k: None)

    def _sleep_once(_s):
        steps["n"] += 1
        if steps["n"] > 1:
            raise RuntimeError("stop")
        return None

    monkeypatch.setattr(mod.time, "sleep", _sleep_once)
    applied_pids.add(5)
    mod._start_policy_refresh_watchdog(
        policy_file=str(policy),
        refresh_seconds=1,
        applied_pids=applied_pids,
        applied_pids_lock=lock,
    )

    # handle client flows
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
                "token": "token-1",
            }

        def update_session(self, session_id, *, endpoints):
            return {
                "session_id": session_id,
                "proxy_url": "http://127.0.0.1:1",
            }

        def stop_session(self, _session_id):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(mod, "_validate_client_and_target_pid", lambda **_k: 7)
    monkeypatch.setattr(mod, "ensure_linux_network_enforcement_ready", lambda: None)
    monkeypatch.setattr(mod, "_load_endpoints_from_policy_file", lambda _p: [{"host": "x", "port": 1, "protocol": "tcp"}])
    monkeypatch.setattr(mod, "apply_application_network_endpoints", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "clear_application_network_allowlist", lambda **_k: None)
    applied_pids.clear()
    lock = threading.Lock()
    proxy = _Proxy()

    w = _Writer()
    await mod._handle_helper_client(_Reader(b'{"action":"ping","token":"test-token"}\n'), w, policy_file=str(policy), parent_pid=None, applied_pids=applied_pids, applied_pids_lock=lock, proxy=proxy, token="test-token")
    assert json.loads(w.buf.decode("utf-8"))["ok"] is True

    w = _Writer()
    await mod._handle_helper_client(_Reader(b'{"action":"apply","pid":7}\n'), w, policy_file=str(policy), parent_pid=None, applied_pids=applied_pids, applied_pids_lock=lock, proxy=proxy, token="test-token")
    missing_token_response = json.loads(w.buf.decode("utf-8"))
    assert missing_token_response["ok"] is False
    assert "os_sandbox_helper_invalid_token" in missing_token_response["error"]
    assert applied_pids == set()

    w = _Writer()
    await mod._handle_helper_client(_Reader(b'{"action":"apply","pid":7,"token":"test-token"}\n'), w, policy_file=str(policy), parent_pid=None, applied_pids=applied_pids, applied_pids_lock=lock, proxy=proxy, token="test-token")
    assert applied_pids == {7}

    w = _Writer()
    await mod._handle_helper_client(_Reader(b'{"action":"clear","pid":7,"token":"test-token"}\n'), w, policy_file=str(policy), parent_pid=None, applied_pids=applied_pids, applied_pids_lock=lock, proxy=proxy, token="test-token")
    assert applied_pids == set()

    w = _Writer()
    await mod._handle_helper_client(_Reader(b'{"action":"update_proxy_session","session_id":"session-1","endpoints":[],"token":"test-token"}\n'), w, policy_file=str(policy), parent_pid=None, applied_pids=applied_pids, applied_pids_lock=lock, proxy=proxy, token="test-token")
    update_response = json.loads(w.buf.decode("utf-8"))
    assert update_response["ok"] is True
    assert update_response["session_id"] == "session-1"

    w = _Writer()
    await mod._handle_helper_client(_Reader(b'{"action":"weird","token":"test-token"}\n'), w, policy_file=str(policy), parent_pid=None, applied_pids=applied_pids, applied_pids_lock=lock, proxy=proxy, token="test-token")
    assert json.loads(w.buf.decode("utf-8"))["ok"] is False

    w = _Writer()
    await mod._handle_helper_client(_Reader(b"not-json\n"), w, policy_file=str(policy), parent_pid=None, applied_pids=applied_pids, applied_pids_lock=lock, proxy=proxy, token="test-token")
    assert json.loads(w.buf.decode("utf-8"))["ok"] is False
    w = _Writer()
    await mod._handle_helper_client(_Reader(b""), w, policy_file=str(policy), parent_pid=None, applied_pids=applied_pids, applied_pids_lock=lock, proxy=proxy, token="test-token")

    # run server lifecycle
    socket_path = tmp_path / "helper.sock"
    socket_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod, "_start_parent_watchdog", lambda _p: None)
    monkeypatch.setattr(mod, "_start_policy_refresh_watchdog", lambda **_k: None)

    class _Server:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def serve_forever(self):
            raise asyncio.CancelledError()

    async def _start_unix_server(*_a, **_k):
        return _Server()

    monkeypatch.setattr(mod.asyncio, "start_unix_server", _start_unix_server)
    monkeypatch.setattr(mod, "_socket_owner_ids", lambda: (1, 2))
    monkeypatch.setattr(mod.os, "chown", lambda *_a, **_k: None)
    monkeypatch.setattr(mod.os, "chmod", lambda *_a, **_k: None)
    rc = await mod.run_os_sandbox_helper_server(str(socket_path), policy_file=str(policy), refresh_seconds=1, parent_pid=10, token="test-token")
    assert rc == 0
    monkeypatch.setattr(mod, "_socket_owner_ids", lambda: None)
    rc = await mod.run_os_sandbox_helper_server(str(socket_path), policy_file=str(policy), refresh_seconds=1, parent_pid=None, token="test-token")
    assert rc == 0


def test_process_guard_all_paths(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")

    # baseline state helpers
    mod._STATE.set(None)
    assert mod._state() == {}
    assert mod._bypass_enabled() is False

    path = str(tmp_path / "a")
    normalized = mod._normalized_path_variants(path)
    assert normalized
    vals = mod._normalize_paths(["", "ro:" + path, path])
    assert vals

    monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "logs_dir", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    python_include = tmp_path / "python-include"
    python_data = tmp_path / "python-data"
    python_scripts = tmp_path / "python-scripts"
    monkeypatch.setattr(
        mod.sysconfig,
        "get_paths",
        lambda: {
            "stdlib": str(tmp_path),
            "platstdlib": "",
            "purelib": str(tmp_path),
            "platlib": str(tmp_path),
            "data": str(python_data),
            "include": str(python_include),
            "scripts": str(python_scripts),
        },
    )
    monkeypatch.setattr(mod.sys, "path", [str(tmp_path), ""])
    monkeypatch.setattr(mod, "system_read_paths", lambda: ("/system/base",))
    runtime_read_paths = mod._runtime_filesystem_read_paths()
    assert "/system/base" in runtime_read_paths
    assert str(python_data.resolve()) in runtime_read_paths
    assert str(python_include.resolve()) in runtime_read_paths
    assert str(python_scripts.resolve()) in runtime_read_paths
    assert runtime_read_paths
    runtime_rules = mod._runtime_access()
    log_delete_rule = _access_rule(
        mod,
        "core",
        "process_guard_runtime",
        "filesystem",
        "delete",
        str(tmp_path),
    )
    assert any(
        rule.resource.resource_type == log_delete_rule.resource.resource_type
        and rule.resource.operation == log_delete_rule.resource.operation
        and rule.resource.normalized_target == log_delete_rule.resource.normalized_target
        for rule in runtime_rules
    )

    token_bypass = mod._BYPASS.set(True)
    assert mod._path_allowed("/any", operation="read") is True
    mod._BYPASS.reset(token_bypass)
    assert mod._path_allowed("/any", operation="read") is True  # no state
    st_token = mod._STATE.set(_guard_state(mod, ()))
    assert mod._path_allowed("/any", operation="read") is False
    assert mod._path_allowed(1, operation="read") is False
    mod._STATE.reset(st_token)
    st_token = mod._STATE.set(
        _guard_state(
            mod,
            (
                _access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path)),
            ),
        )
    )
    assert mod._path_allowed(str(tmp_path / "x"), operation="read") is True
    assert mod._path_allowed("/outside", operation="read") is False
    mod._STATE.reset(st_token)

    st_token = mod._STATE.set(_guard_state(mod, ()))
    mod._check_path("", operation="read")
    mod._STATE.reset(st_token)

    depth_token = mod._PATH_CHECK_DEPTH.set(1)
    mod._check_path("/x", operation="read")
    mod._check_path_pair("/x", "/y", source_operation="read", target_operation="read")
    mod._PATH_CHECK_DEPTH.reset(depth_token)
    st_token = mod._STATE.set(
        {
            "access": (
                _access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path)),
            ),
            "subject": "s",
        }
    )
    external_calls = []
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx",
        lambda: SimpleNamespace(setup_mode=True),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.services.external_access",
        SimpleNamespace(check_external_access=lambda **_k: external_calls.append(_k)),
    )
    assert mod._external_filesystem_access_allowed("/outside", operation="read") is False
    assert external_calls == []

    monkeypatch.setattr(mod, "_external_filesystem_access_allowed", lambda *_a, **_k: False)
    assert mod._external_filesystem_access_allowed("/outside", operation="read") is False
    with pytest.raises(PermissionError):
        mod._check_path("/outside", operation="read")
    with pytest.raises(PermissionError):
        mod._check_path_pair("/outside", str(tmp_path), source_operation="read", target_operation="read")
    with pytest.raises(PermissionError):
        mod._check_path_pair(str(tmp_path), "/outside", source_operation="read", target_operation="read")
    mod._STATE.reset(st_token)

    with pytest.raises(PermissionError):
        mod._check_fd_kwargs({"dir_fd": 1})
    with pytest.raises(PermissionError):
        mod._check_fd_kwargs({"src_dir_fd": 1})
    with pytest.raises(PermissionError):
        mod._check_fd_kwargs({"dst_dir_fd": 1})
    mod._check_fd_kwargs({})

    # wrapper factories
    monkeypatch.setattr(mod, "_check_path", lambda _p, **_k: None)
    monkeypatch.setattr(mod, "_check_path_pair", lambda _a, _b, **_k: None)
    monkeypatch.setattr(mod, "_check_fd_kwargs", lambda _k: None)
    assert mod._wrap_open(lambda f, *a, **k: ("ok", f))("x")[0] == "ok"
    assert mod._wrap_os_open(lambda p, flags, *a, **k: ("ok", p, flags))("x", 1)[0] == "ok"
    assert mod._wrap_os_optional_path(lambda p=".", *a, **k: ("ok", p), "read")("x")[1] == "x"
    assert mod._wrap_os_default_path(lambda p=".", *a, **k: ("ok", p), ".", "read")("x")[1] == "x"
    assert mod._wrap_path_pair(lambda a, b, *x, **k: ("ok", a, b), "read", "read")("a", "b")[2] == "b"
    assert mod._wrap_path_method(lambda self, *a, **k: ("ok", self), "stat")("x")[1] == "x"
    assert mod._wrap_path_pair_method(lambda self, t, *a, **k: ("ok", self, t), "read", "read")("x", "y")[2] == "y"
    assert mod._wrap_shutil_unpack_archive(lambda f, d=None, *a, **k: ("ok", f, d))("a", "b")[2] == "b"
    assert mod._wrap_shutil_make_archive(lambda b, fmt, r=None, bd=None, *a, **k: ("ok", b, fmt, r, bd))("b", "zip", "r", "bd")[4] == "bd"
    assert mod._wrap_shutil_single_path(lambda p, *a, **k: ("ok", p), "read")("x")[1] == "x"
    assert mod._wrap_shutil_path_pair(lambda a, b, *x, **k: ("ok", a, b), "read", "read")("a", "b")[2] == "b"

    wrapped_import = mod._wrap_import(lambda name, g=None, l=None, fromlist=(), level=0: {"name": name})
    token = mod._BYPASS.set(True)
    assert wrapped_import("ctypes")["name"] == "ctypes"
    mod._BYPASS.reset(token)
    st = mod._STATE.set(None)
    assert wrapped_import("ctypes")["name"] == "ctypes"
    mod._STATE.reset(st)
    st = mod._STATE.set({"subject": "s"})
    with pytest.raises(PermissionError):
        wrapped_import("ctypes")
    mod._STATE.reset(st)


def test_process_guard_denies_sensitive_import_before_original_import(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    module_name = "cffi"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    calls = []

    def _original(name, g=None, l=None, fromlist=(), level=0):
        calls.append(name)
        sys.modules[name] = SimpleNamespace(name=name)
        return sys.modules[name]

    wrapped_import = mod._wrap_import(_original)
    st = mod._STATE.set({"subject": "s"})
    try:
        with pytest.raises(PermissionError, match="sandbox_module_denied:cffi"):
            wrapped_import(module_name)
    finally:
        mod._STATE.reset(st)

    assert calls == []
    assert module_name not in sys.modules


def test_process_guard_context_can_skip_network_policy(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    calls = []

    class _NetworkContext:
        def __enter__(self):
            calls.append("enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append("exit")
            return False

    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [])
    monkeypatch.setattr(mod, "network_policy_context", lambda **_kwargs: _NetworkContext())

    with mod.process_guard_context(
        subject="s",
        access=[],
        include_runtime_access=False,
        include_network_access=False,
    ):
        pass

    assert calls == []

    with mod.process_guard_context(
        subject="s",
        access=[],
        include_runtime_access=False,
    ):
        pass

    assert calls == ["enter", "exit"]


def test_process_guard_context_cleans_guard_when_network_enter_fails(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    calls = []

    class _NetworkContext:
        def __enter__(self):
            calls.append("network_enter")
            raise RuntimeError("network failed")

        def __exit__(self, exc_type, exc, tb):
            calls.append("network_exit")
            return False

    monkeypatch.setattr(mod, "network_policy_context", lambda **_kwargs: _NetworkContext())
    monkeypatch.setattr(mod, "enable_process_guard", lambda **_kwargs: "tok")
    monkeypatch.setattr(mod, "disable_process_guard", lambda token=None: calls.append(token))

    with pytest.raises(RuntimeError, match="network failed"):
        with mod.process_guard_context(
            subject="s",
            access=[],
            include_runtime_access=False,
        ):
            pass

    assert calls == ["network_enter", "tok"]


def test_process_guard_context_cleans_guard_when_network_exit_fails(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    calls = []

    class _NetworkContext:
        def __enter__(self):
            calls.append("network_enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append("network_exit")
            raise RuntimeError("network exit failed")

    monkeypatch.setattr(mod, "network_policy_context", lambda **_kwargs: _NetworkContext())
    monkeypatch.setattr(mod, "enable_process_guard", lambda **_kwargs: "tok")
    monkeypatch.setattr(mod, "disable_process_guard", lambda token=None: calls.append(token))

    with pytest.raises(RuntimeError, match="network exit failed"):
        with mod.process_guard_context(
            subject="s",
            access=[],
            include_runtime_access=False,
        ):
            pass

    assert calls == ["network_enter", "network_exit", "tok"]


def test_process_guard_bypass_skips_wrapper_path_checks(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(
        mod,
        "_check_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("checked")),
    )
    token = mod._BYPASS.set(True)
    try:
        assert mod._wrap_os_optional_path(lambda path=".", *a, **k: path, "read")("x") == "x"
        assert mod._wrap_path_method(lambda self, *a, **k: self, "stat")("y") == "y"
        assert mod._wrap_open(lambda file, *a, **k: file)("z") == "z"
    finally:
        mod._BYPASS.reset(token)


def test_process_guard_import_wrapper_profiles_only_sensitive_roots():
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    profiling_mod = importlib.import_module("democrai.core.runtime.observability.profiling")
    calls = []

    def _original(name, g=None, l=None, fromlist=(), level=0):
        calls.append(name)
        return SimpleNamespace(name=name)

    wrapped_import = mod._wrap_import(_original)
    profiler = profiling_mod.RequestProfiler("import-test", "sandbox", enabled=True)
    profile_token = profiling_mod._current_profiler.set(profiler)
    state_token = mod._STATE.set(
        {
            "subject": "s",
            "allowed_import_roots": {"ctypes"},
        }
    )
    try:
        assert wrapped_import("json").name == "json"
        assert not any(name.startswith("process_guard.wrapper.import") for name in profiler.spans_ms)
        assert wrapped_import("ctypes").name == "ctypes"
    finally:
        mod._STATE.reset(state_token)
        profiling_mod._current_profiler.reset(profile_token)

    assert calls == ["json", "ctypes"]
    assert "process_guard.wrapper.import.guard" in profiler.spans_ms
    assert profiler.metrics["process_guard.wrapper.import.calls"] == 1.0


def test_darwin_system_read_paths_include_zoneinfo_and_realpath(monkeypatch):
    access_constants = importlib.import_module("democrai.core.infrastructure.sandbox.access_constants")
    policy = importlib.import_module("democrai.core.infrastructure.sandbox.platform_policy")

    monkeypatch.setattr(policy.sys, "platform", "darwin")
    monkeypatch.setattr(policy.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(policy.os.path, "realpath", lambda path: str(path))

    paths = access_constants.system_read_paths()
    assert "/etc/zoneinfo" in paths
    assert "/usr/lib/zoneinfo" in paths
    assert "/usr/share/lib/zoneinfo" in paths
    assert "/usr/share/zoneinfo" in paths
    assert "/usr/share/zoneinfo.default" in paths
    assert "/var/db/timezone/zoneinfo" in paths


def test_platform_policy_covers_darwin_runtime_paths(monkeypatch):
    policy = importlib.import_module("democrai.core.infrastructure.sandbox.platform_policy")
    access_constants = importlib.import_module("democrai.core.infrastructure.sandbox.access_constants")

    monkeypatch.setattr(policy.sys, "platform", "darwin")
    monkeypatch.setattr(policy.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(policy.os.path, "realpath", lambda path: str(path))

    system_paths = access_constants.system_read_paths()
    assert "/System/Library" in system_paths
    assert "/Library" in system_paths
    assert "/usr/lib" in system_paths
    assert "/usr/bin" in system_paths
    assert "/private/etc" in system_paths
    assert "/var/db/timezone" in system_paths
    assert "/opt/homebrew" in system_paths
    assert "/opt/local" in system_paths
    assert "/opt/homebrew/bin/clang" in policy.toolchain_execute_paths()


def test_platform_policy_covers_windows_env_paths(monkeypatch):
    policy = importlib.import_module("democrai.core.infrastructure.sandbox.platform_policy")
    access_constants = importlib.import_module("democrai.core.infrastructure.sandbox.access_constants")

    monkeypatch.setattr(policy.sys, "platform", "win32")
    monkeypatch.setenv("SystemRoot", r"D:\Windows")
    monkeypatch.setenv("ProgramFiles", r"D:\Program Files")
    monkeypatch.setenv("ProgramFiles(x86)", r"D:\Program Files (x86)")
    monkeypatch.setenv("ProgramData", r"D:\ProgramData")
    monkeypatch.setenv("LOCALAPPDATA", r"D:\Users\me\AppData\Local")
    monkeypatch.setattr(policy.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(policy.os.path, "realpath", lambda path: str(path))

    system_paths = access_constants.system_read_paths()
    assert r"D:\Windows/System32" in system_paths
    assert r"D:\Windows/SysWOW64" in system_paths
    assert r"D:\ProgramData" in system_paths
    assert r"D:\Program Files" in system_paths
    assert r"D:\Program Files (x86)" in system_paths
    assert r"D:\Users\me\AppData\Local" in system_paths
    assert policy.toolchain_execute_paths() == ()
    assert not any(str(path).startswith(r"\\.\pipe") for path in system_paths)


def test_system_probe_read_paths_keep_optional_mime_type_probes(monkeypatch):
    policy = importlib.import_module("democrai.core.infrastructure.sandbox.platform_policy")
    access_constants = importlib.import_module("democrai.core.infrastructure.sandbox.access_constants")

    monkeypatch.setattr(policy.sys, "platform", "linux")
    monkeypatch.setattr(policy, "LINUX_SYSTEM_PROBE_READ_PATHS", ("/etc/httpd/mime.types",))
    monkeypatch.setattr(policy, "LINUX_RUNTIME_DEPENDENCY_READ_PATHS", ())
    monkeypatch.setattr(policy.os.path, "exists", lambda _path: False)

    assert "/etc/httpd/mime.types" in access_constants.system_read_paths()


def test_process_guard_runtime_access_allows_optional_mime_type_probe(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    policy = importlib.import_module("democrai.core.infrastructure.sandbox.platform_policy")
    access_constants = importlib.import_module("democrai.core.infrastructure.sandbox.access_constants")

    monkeypatch.setattr(policy.sys, "platform", "linux")
    monkeypatch.setattr(policy, "LINUX_SYSTEM_PROBE_READ_PATHS", ("/etc/httpd/mime.types",))
    monkeypatch.setattr(policy, "LINUX_RUNTIME_DEPENDENCY_READ_PATHS", ())
    monkeypatch.setattr(policy.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(mod, "system_read_paths", access_constants.system_read_paths)
    monkeypatch.setattr(mod.sys, "path", [])
    monkeypatch.setattr(
        mod.sysconfig,
        "get_paths",
        lambda: {"stdlib": "", "platstdlib": "", "purelib": "", "platlib": ""},
    )

    with mod.process_guard_context(subject="system", subject_kind="module"):
        assert mod._path_allowed("/etc/httpd/mime.types", operation="read")


def test_path_allowed_accepts_zoneinfo_symlink_and_realpath_variants(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    target = "/usr/share/zoneinfo/CEST"
    monkeypatch.setattr(
        mod,
        "_normalized_path_variants",
        lambda _path: [
            "/usr/share/zoneinfo/CEST",
            "/usr/share/zoneinfo.default/CEST",
        ],
    )
    st = mod._STATE.set(
        {
            "subject": "system",
            "filesystem_access": {
                "read": (
                    "/usr/lib/zoneinfo",
                    "/etc/zoneinfo",
                    "/usr/share/lib/zoneinfo",
                    "/usr/share/zoneinfo",
                    "/usr/share/zoneinfo.default",
                ),
            },
        }
    )
    try:
        assert mod._path_allowed(target, operation="read") is True
    finally:
        mod._STATE.reset(st)


def test_path_allowed_accepts_homebrew_python_zoneinfo_path(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    target = "/usr/share/lib/zoneinfo/CEST"
    monkeypatch.setattr(
        mod,
        "_normalized_path_variants",
        lambda _path: ["/usr/share/lib/zoneinfo/CEST"],
    )
    st = mod._STATE.set(
        {
            "subject": "system",
            "filesystem_access": {
                "read": ("/usr/share/lib/zoneinfo",),
            },
        }
    )
    try:
        assert mod._path_allowed(target, operation="read") is True
    finally:
        mod._STATE.reset(st)


def test_path_allowed_global_cache_survives_equivalent_contexts(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [])
    target = tmp_path / "allowed" / "file.txt"
    target.parent.mkdir()
    target.write_text("ok", encoding="utf-8")
    calls = []

    def _realpath(path):
        calls.append(path)
        return os.path.normpath(os.path.abspath(os.path.expanduser(os.fspath(path))))

    monkeypatch.setattr(mod.os.path, "realpath", _realpath)
    access = [
        _access_rule(mod, "module", "s", "filesystem", "read", str(target.parent)),
    ]

    token = mod.enable_process_guard(
        subject="s",
        access=access,
        include_runtime_access=False,
    )
    try:
        assert mod._path_allowed(target, operation="read") is True
    finally:
        mod.disable_process_guard(token)

    token = mod.enable_process_guard(
        subject="s",
        access=access,
        include_runtime_access=False,
    )
    try:
        assert mod._path_allowed(target, operation="read") is True
    finally:
        mod.disable_process_guard(token)

    assert len(calls) == 2


def test_path_allowed_global_cache_is_scoped_by_allowlist(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [])
    allowed_root = tmp_path / "allowed"
    other_root = tmp_path / "other"
    allowed_root.mkdir()
    other_root.mkdir()
    target = allowed_root / "file.txt"
    target.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(
        mod.os.path,
        "realpath",
        lambda path: os.path.normpath(os.path.abspath(os.path.expanduser(os.fspath(path)))),
    )

    token = mod.enable_process_guard(
        subject="s",
        access=[_access_rule(mod, "module", "s", "filesystem", "read", str(allowed_root))],
        include_runtime_access=False,
    )
    try:
        assert mod._path_allowed(target, operation="read") is True
    finally:
        mod.disable_process_guard(token)

    token = mod.enable_process_guard(
        subject="s",
        access=[_access_rule(mod, "module", "s", "filesystem", "read", str(other_root))],
        include_runtime_access=False,
    )
    try:
        assert mod._path_allowed(target, operation="read") is False
    finally:
        mod.disable_process_guard(token)


def test_path_allowed_global_cache_is_scoped_by_subject_chain(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [])
    target = tmp_path / "allowed" / "file.txt"
    outside = tmp_path / "outside" / "file.txt"
    target.parent.mkdir()
    outside.parent.mkdir()
    target.write_text("ok", encoding="utf-8")
    phase = {"escape": False}

    def _realpath(path):
        if phase["escape"] and os.fspath(path) == os.fspath(target):
            return str(outside)
        return os.path.normpath(os.path.abspath(os.path.expanduser(os.fspath(path))))

    monkeypatch.setattr(mod.os.path, "realpath", _realpath)
    access = [
        _access_rule(mod, "engine", "onnx", "filesystem", "read", str(target.parent)),
    ]

    parent = mod.enable_process_guard(
        subject="system",
        subject_kind="module",
        access=[],
        include_runtime_access=False,
    )
    child = mod.enable_process_guard(
        subject="onnx",
        subject_kind="engine",
        access=access,
        include_runtime_access=False,
    )
    try:
        assert mod._path_allowed(target, operation="read") is True
    finally:
        mod.disable_process_guard(child)
        mod.disable_process_guard(parent)

    with mod._REALPATH_CACHE_LOCK:
        mod._GLOBAL_REALPATH_CACHE.clear()
    phase["escape"] = True
    token = mod.enable_process_guard(
        subject="onnx",
        subject_kind="engine",
        access=access,
        include_runtime_access=False,
    )
    try:
        assert mod._path_allowed(target, operation="read") is False
    finally:
        mod.disable_process_guard(token)


def test_path_allowed_obvious_deny_skips_realpath(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    st = mod._STATE.set(
        {
            "subject": "system",
            "filesystem_access": {"read": (str(allowed_root),)},
        }
    )
    monkeypatch.setattr(
        mod.os.path,
        "realpath",
        lambda _path: (_ for _ in ()).throw(AssertionError("realpath called")),
    )
    try:
        assert mod._path_allowed(tmp_path / "outside.txt", operation="read") is False
    finally:
        mod._STATE.reset(st)


def test_path_allowed_accepts_symlinked_system_alias_after_cheap_miss(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    calls = []

    def _realpath(path):
        raw = os.fspath(path)
        calls.append(raw)
        if raw == "/private/etc":
            return "/private/etc"
        if raw == "/etc/hosts":
            return "/private/etc/hosts"
        return os.path.normpath(os.path.abspath(os.path.expanduser(raw)))

    monkeypatch.setattr(mod.os.path, "realpath", _realpath)
    st = mod._STATE.set(
        {
            "subject": "system",
            "filesystem_access": {"read": ("/private/etc",)},
        }
    )
    try:
        assert mod._path_allowed("/etc/hosts", operation="read") is True
    finally:
        mod._STATE.reset(st)

    assert "/etc/hosts" in calls


def test_path_allowed_under_root_uses_cached_realpath(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    target = allowed_root / "file.txt"
    calls = []

    def _realpath(path):
        calls.append(path)
        return os.path.normpath(os.path.abspath(os.path.expanduser(os.fspath(path))))

    monkeypatch.setattr(mod.os.path, "realpath", _realpath)
    st = mod._STATE.set(
        {
            "subject": "system",
            "filesystem_access": {"read": (str(allowed_root),)},
        }
    )
    try:
        assert mod._path_allowed(target, operation="read") is True
        assert mod._path_allowed(target, operation="read") is True
    finally:
        mod._STATE.reset(st)

    assert len(calls) == 2


def test_path_allowed_denies_symlink_escape_after_realpath(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    target = allowed_root / "link.txt"

    monkeypatch.setattr(
        mod.os.path,
        "realpath",
        lambda path: (
            str(outside_root / "file.txt")
            if os.fspath(path) == os.fspath(target)
            else os.path.normpath(os.path.abspath(os.path.expanduser(os.fspath(path))))
        ),
    )
    st = mod._STATE.set(
        {
            "subject": "system",
            "filesystem_access": {"read": (str(allowed_root),)},
        }
    )
    try:
        assert mod._path_allowed(target, operation="read") is False
    finally:
        mod._STATE.reset(st)


@pytest.mark.parametrize(
    "relative_data_root",
    [
        ("home", "user", ".local", "share", "democrai"),
        ("home", "user", "Library", "Application Support", "democrai"),
        ("Users", "user", "AppData", "Roaming", "democrai"),
    ],
)
def test_system_manifest_data_dir_token_allows_only_resolved_data_dir(
    monkeypatch,
    tmp_path: Path,
    relative_data_root: tuple[str, ...],
):
    from democrai.core.application.access_policy.manifest import parse_access_manifest_rules
    import democrai.core.application.access_policy.manifest as manifest_mod

    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    data_root = tmp_path.joinpath(*relative_data_root)
    data_root.mkdir(parents=True)
    system_manifest = json.loads(Path("modules/system/manifest.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(manifest_mod, "data_dir", lambda: data_root)

    access = parse_access_manifest_rules(
        system_manifest,
        subject_type="module",
        subject_name="system",
    )
    target = data_root / "config.yaml"
    outside = tmp_path / "outside" / "config.yaml"
    outside.parent.mkdir()

    with mod.process_guard_context(
        subject="system",
        subject_kind="module",
        access=access,
        include_runtime_access=False,
    ):
        target.write_text("ok", encoding="utf-8")
        with pytest.raises(PermissionError):
            outside.write_text("blocked", encoding="utf-8")

    with mod.process_guard_context(
        subject="generic",
        subject_kind="module",
        access=[],
        include_runtime_access=False,
    ):
        with pytest.raises(PermissionError):
            target.write_text("blocked", encoding="utf-8")


def test_os_makedirs_allows_authorized_data_dir_with_missing_parents(monkeypatch, tmp_path: Path):
    from democrai.core.application.access_policy.manifest import parse_access_manifest_rules
    import democrai.core.application.access_policy.manifest as manifest_mod

    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    data_root = tmp_path / "Users" / "fabio" / "Library" / "Application Support" / "democrai"
    system_manifest = json.loads(Path("modules/system/manifest.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(manifest_mod, "data_dir", lambda: data_root)
    access = parse_access_manifest_rules(
        system_manifest,
        subject_type="module",
        subject_name="system",
    )

    with mod.process_guard_context(
        subject="system",
        subject_kind="module",
        access=access,
        include_runtime_access=False,
    ):
        os.makedirs(data_root, exist_ok=True)
        (data_root / "config.yaml").write_text("ok: true\n", encoding="utf-8")
        with pytest.raises(PermissionError):
            os.mkdir(data_root.parent)
        with pytest.raises(PermissionError):
            os.makedirs(tmp_path / "Users" / "fabio" / "Library" / "Other App", exist_ok=True)

    assert data_root.is_dir()
    assert (data_root / "config.yaml").read_text(encoding="utf-8") == "ok: true\n"


def test_yaml_config_provider_save_allows_authorized_data_dir_with_missing_parents(monkeypatch, tmp_path: Path):
    from democrai.core.application.access_policy.manifest import parse_access_manifest_rules
    import democrai.core.application.access_policy.manifest as manifest_mod
    from democrai.core.platform.config.yaml_config import YamlConfigProvider

    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    data_root = tmp_path / "Users" / "fabio" / "Library" / "Application Support" / "democrai"
    system_manifest = json.loads(Path("modules/system/manifest.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(manifest_mod, "data_dir", lambda: data_root)
    access = parse_access_manifest_rules(
        system_manifest,
        subject_type="module",
        subject_name="system",
    )
    provider = YamlConfigProvider(str(data_root / "config.yaml"))
    provider.set("setup.completed", True)

    with mod.process_guard_context(
        subject="system",
        subject_kind="module",
        access=access,
        include_runtime_access=False,
    ):
        provider.save()

    assert (data_root / "config.yaml").exists()


def test_process_guard_runtime_access_allows_configured_http_logger(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    app_mod = importlib.import_module("democrai.core.runtime.foundation.app")

    config = SimpleNamespace(
        get=lambda key, default=None: {
            "logging.provider": "http",
            "logging.url": "https://logs.example.test/ingest",
        }.get(key, default)
    )
    monkeypatch.setattr(app_mod, "app_ctx", lambda: SimpleNamespace(config=config))

    rules = mod._runtime_access()
    logging_rules = [
        rule
        for rule in rules
        if rule.resource.resource_type.value == "network"
        and rule.resource.normalized_target == "https://logs.example.test/ingest"
    ]
    assert {rule.resource.operation.value for rule in logging_rules} == {
        "connect",
        "send",
        "receive",
    }


def test_process_guard_runtime_access_allows_ipc_socket_cleanup(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(mod, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(mod, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(mod, "state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(mod, "logs_dir", lambda: tmp_path / "state" / "logs")
    monkeypatch.setattr(mod, "runtime_ipc_dir", lambda: tmp_path / "state" / "ipc")

    rules = mod._runtime_access()
    delete_targets = {
        rule.resource.normalized_target
        for rule in rules
        if rule.resource.resource_type.value == "filesystem"
        and rule.resource.operation.value == "delete"
    }

    assert str((tmp_path / "state" / "ipc").resolve()) in delete_targets
    assert not any(str(target).startswith(r"\\.\pipe") for target in delete_targets)


def test_runtime_filesystem_read_paths_include_configured_local_media_path(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")

    media_path = tmp_path / "media"
    monkeypatch.setattr(mod, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(mod, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(mod, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(mod, "state_dir", lambda: tmp_path / "state")
    monkeypatch.setattr(mod, "logs_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(
        mod.sysconfig,
        "get_paths",
        lambda: {"stdlib": "", "platstdlib": "", "purelib": "", "platlib": ""},
    )
    monkeypatch.setattr(mod.sys, "path", [])

    class _Config:
        def get(self, key, default=None):
            values = {
                "storage.media.type": "local",
                "storage.media.path": str(media_path),
            }
            return values.get(key, default)

    monkeypatch.setattr(mod, "_configured_runtime_paths", lambda: [str(media_path)])
    allowed = mod._runtime_filesystem_read_paths()
    assert str(media_path.resolve()) in allowed
    wrapped_import = mod._wrap_import(lambda name, g=None, l=None, fromlist=(), level=0: {"name": name})
    st = mod._STATE.set({"subject": "s", "allowed_imports": ["json"]})
    assert wrapped_import("json")["name"] == "json"
    mod._STATE.reset(st)
    st = mod._STATE.set({"subject": "s", "allowed_imports": ["ctypes", "ctypes.util"]})
    assert wrapped_import("ctypes")["name"] == "ctypes"
    with pytest.raises(PermissionError):
        wrapped_import("cffi")
    mod._STATE.reset(st)

    class _Owner:
        __name__ = "owner"

    owner = SimpleNamespace(__name__="owner", fn=lambda: 1)
    mod._patch_attr(owner, "fn", lambda original: (lambda: original() + 1))
    assert owner.fn() == 2
    mod._patch_attr(owner, "missing", lambda original: original)
    mod._patch_attr(pathlib.Path, "exists", lambda original: original)

    denied = mod._blocked_process_call("x", lambda *a, **k: "ok")
    with pytest.raises(PermissionError):
        denied()
    token = mod._BYPASS.set(True)
    assert denied() == "ok"
    mod._BYPASS.reset(token)
    st = mod._STATE.set({"allow_subprocess": True})
    assert denied() == "ok"
    mod._STATE.reset(st)

    # enable/disable including nested activation
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [str(tmp_path)])
    token1 = mod.enable_process_guard(
        subject="s",
        access=[_access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path))],
        allow_subprocess=False,
    )
    token2 = mod.enable_process_guard(
        subject="s2",
        access=[_access_rule(mod, "module", "s2", "filesystem", "read", str(tmp_path))],
        allow_subprocess=True,
    )
    mod.disable_process_guard(token2)
    mod.disable_process_guard(token1)
    assert mod._ACTIVE is False

    # disable with invalid token branch
    mod._ACTIVE = True
    mod._ACTIVE_COUNT = 1
    mod._ORIGINALS["builtins.open"] = builtins.open
    mod._ORIGINALS["builtins.__import__"] = builtins.__import__
    mod._ORIGINALS["io.open"] = io.open
    mod.disable_process_guard(object())

    # process guard context + bypass + env
    class _NetCtx:
        def __init__(self):
            self.entered = False
            self.exited = False

        def __enter__(self):
            self.entered = True
            return self

        def __exit__(self, exc_type, exc, tb):
            self.exited = True
            return False

    net_ctx = _NetCtx()
    real_enable_process_guard = mod.enable_process_guard
    real_disable_process_guard = mod.disable_process_guard
    monkeypatch.setattr(mod, "network_policy_context", lambda **_k: net_ctx)
    monkeypatch.setattr(mod, "enable_process_guard", lambda **_k: "tok")
    calls = []
    monkeypatch.setattr(mod, "disable_process_guard", lambda tok=None: calls.append(tok))
    ctx = mod.process_guard_context(
        subject="sub",
        subject_kind="module",
        access=[
            _access_rule(mod, "module", "sub", "filesystem", "read", "/x"),
            _access_rule(mod, "module", "sub", "network", "receive", "a"),
        ],
        allowed_imports=["ctypes"],
    )
    with ctx:
        assert net_ctx.entered is True
    assert net_ctx.exited is True and calls == ["tok"]

    assert mod._bypass_enabled() is False
    with mod.process_guard_bypass_context():
        assert mod._bypass_enabled() is True
    assert mod._bypass_enabled() is False

    monkeypatch.delenv("DEMOCRAI_NETWORK_SUBJECT", raising=False)
    assert isinstance(mod.process_guard_context_from_env(), contextlib.AbstractContextManager)
    monkeypatch.setenv("DEMOCRAI_NETWORK_SUBJECT", "sub")
    monkeypatch.setenv("DEMOCRAI_NETWORK_SUBJECT_KIND", "engine")
    monkeypatch.setenv(
        "DEMOCRAI_ACCESS",
        json.dumps([
            _access_rule(mod, "engine", "sub", "filesystem", "read", "/x").to_dict(),
            _access_rule(mod, "engine", "sub", "network", "receive", "a").to_dict(),
        ]),
    )
    env_ctx = mod.process_guard_context_from_env()
    assert isinstance(env_ctx, mod.process_guard_context)
    assert env_ctx.subject_kind == "engine"
    monkeypatch.setenv("DEMOCRAI_ACCESS", "{bad")
    with pytest.raises(json.JSONDecodeError):
        mod.process_guard_context_from_env()

    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [str(tmp_path)])
    token1 = real_enable_process_guard(
        subject="s",
        access=[_access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path))],
        allowed_imports=["ctypes"],
        allow_subprocess=False,
    )
    assert mod._state()["allowed_imports"] == ["ctypes"]
    token2 = real_enable_process_guard(
        subject="s2",
        access=[_access_rule(mod, "module", "s2", "filesystem", "read", str(tmp_path))],
        allowed_imports=["ctypes.util", "cffi"],
        allow_subprocess=True,
    )
    assert mod._state()["allowed_imports"] == ["ctypes", "cffi"]
    real_disable_process_guard(token2)
    real_disable_process_guard(token1)
    mod._ACTIVE = False
    mod._ACTIVE_COUNT = 0
    mod._STATE.set(None)
    mod._ORIGINALS.clear()


@pytest.mark.linux_only
def test_linux_remaining_branches(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.linux.network")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    # read cgroup: malformed line and relative path without slash
    monkeypatch.setattr(mod.Path, "read_text", lambda *_a, **_k: "badline\n0::user.slice\n")
    assert mod._read_process_cgroup_relative_path(1) == "user.slice"
    assert str(mod._cgroup_absolute_path(1)).endswith("democrai_os_sandbox_1")

    # dns endpoints: file absent and parsing skips
    real_exists = Path.exists
    real_read = Path.read_text
    monkeypatch.setattr(mod.Path, "exists", lambda self: False if str(self) == "/etc/resolv.conf" else real_exists(self))
    assert mod._system_dns_endpoints() == []
    monkeypatch.setattr(mod.Path, "exists", lambda self: True if str(self) == "/etc/resolv.conf" else real_exists(self))
    monkeypatch.setattr(
        mod.Path,
        "read_text",
        lambda self, encoding="utf-8": "nameserver\nnameserver   \nfoo bar\n"
        if str(self) == "/etc/resolv.conf"
        else real_read(self, encoding=encoding),
    )
    assert mod._system_dns_endpoints() == []

    # support checks with missing commands
    monkeypatch.setattr(mod.sys, "platform", "linux")
    root = tmp_path / "cg"
    root.mkdir()
    (root / "cgroup.controllers").write_text("x", encoding="utf-8")
    monkeypatch.setattr(mod, "_CGROUP_ROOT", root)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None if name == mod._IPTABLES else "/bin/" + name)
    assert mod.is_linux_network_enforcement_supported() is False
    monkeypatch.setattr(mod.shutil, "which", lambda name: None if name == mod._IP6TABLES else "/bin/" + name)
    assert mod.is_linux_network_enforcement_supported() is False

    # second probe failure branch
    monkeypatch.setattr(mod, "is_linux_network_enforcement_supported", lambda: True)
    monkeypatch.setattr(mod, "_require_command", lambda n: n)
    calls = {"n": 0}

    def _probe(_cmd, pid):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("x")

    monkeypatch.setattr(mod, "_probe_cgroup_path_match", _probe)
    with pytest.raises(RuntimeError):
        mod.ensure_linux_network_enforcement_ready()


@pytest.mark.asyncio
async def test_helper_process_remaining_branches(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.helper_process")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    # parent traversal loop end current==root
    monkeypatch.setattr(mod, "_parent_pid_of", lambda _pid: 1)
    assert mod._is_same_or_descendant(1, 1) is True
    # parent None branch
    monkeypatch.setattr(mod, "_parent_pid_of", lambda _pid: None)
    assert mod._is_same_or_descendant(5, 2) is False

    # close failure branch in pidfd watchdog
    monkeypatch.setattr(mod, "_open_parent_pidfd", lambda _p: 9)
    monkeypatch.setattr(mod.select, "poll", lambda: SimpleNamespace(register=lambda *a, **k: None, poll=lambda: [(9, 1)]))
    monkeypatch.setattr(mod.os, "close", lambda _fd: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(mod.os, "_exit", lambda _c: (_ for _ in ()).throw(SystemExit(0)))

    class _Thread:
        def __init__(self, target, **_k):
            self.target = target

        def start(self):
            try:
                self.target()
            except (SystemExit, RuntimeError):
                pass

    monkeypatch.setattr(mod.threading, "Thread", _Thread)
    mod._start_parent_watchdog(9)

    # policy refresh: no pid continue and exception branch
    lock = threading.Lock()
    applied_pids: set[int] = set()
    count = {"n": 0}

    def _sleep(_s):
        count["n"] += 1
        if count["n"] == 1:
            return None
        raise RuntimeError("stop")

    monkeypatch.setattr(mod.time, "sleep", _sleep)
    monkeypatch.setattr(mod, "_load_endpoints_from_policy_file", lambda _p: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(mod, "apply_application_network_endpoints", lambda *_a, **_k: None)
    mod._start_policy_refresh_watchdog(
        policy_file=str(tmp_path / "p.json"),
        refresh_seconds=1,
        applied_pids=applied_pids,
        applied_pids_lock=lock,
    )
    applied_pids.add(7)
    mod._start_policy_refresh_watchdog(
        policy_file=str(tmp_path / "p.json"),
        refresh_seconds=1,
        applied_pids=applied_pids,
        applied_pids_lock=lock,
    )

    # helper client: payload not dict and apply with pid None
    class _Reader:
        def __init__(self, raw: bytes):
            self.raw = raw

        async def readline(self):
            return self.raw

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
                "token": "token-1",
            }

        def stop_session(self, _session_id):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(mod, "_validate_client_and_target_pid", lambda **_k: None)
    monkeypatch.setattr(mod, "_load_endpoints_from_policy_file", lambda _p: [{"host": "x", "port": 1, "protocol": "tcp"}])
    monkeypatch.setattr(mod, "apply_application_network_endpoints", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "clear_application_network_allowlist", lambda **_k: None)
    proxy = _Proxy()
    w = _Writer()
    await mod._handle_helper_client(
        _Reader(b"[]\n"),
        w,
        policy_file=str(tmp_path / "p.json"),
        parent_pid=None,
        applied_pids=set(),
        applied_pids_lock=threading.Lock(),
        proxy=proxy,
        token="test-token",
    )
    assert json.loads(w.buf.decode("utf-8"))["ok"] is False

    w2 = _Writer()
    applied_pids2 = {1}
    await mod._handle_helper_client(
        _Reader(b'{"action":"apply","token":"test-token"}\n'),
        w2,
        policy_file=str(tmp_path / "p.json"),
        parent_pid=None,
        applied_pids=applied_pids2,
        applied_pids_lock=threading.Lock(),
        proxy=proxy,
        token="test-token",
    )
    assert applied_pids2 == {1}

    # run server final unlink branch
    sock = tmp_path / "x.sock"
    sock.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod, "_start_parent_watchdog", lambda _p: None)
    monkeypatch.setattr(mod, "_start_policy_refresh_watchdog", lambda **_k: None)

    class _Server:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def serve_forever(self):
            raise asyncio.CancelledError()

    async def _start(*_a, **_k):
        return _Server()

    monkeypatch.setattr(mod.asyncio, "start_unix_server", _start)
    monkeypatch.setattr(mod, "_socket_owner_ids", lambda: None)
    monkeypatch.setattr(mod.os, "chmod", lambda *_a, **_k: None)
    await mod.run_os_sandbox_helper_server(str(sock), policy_file=str(tmp_path / "p.json"), token="test-token")


def test_process_guard_remaining_branches(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")

    # _check_path true branch
    t = mod._STATE.set(
        _guard_state(
            mod,
            (
                _access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path)),
            ),
        )
    )
    mod._check_path(str(tmp_path / "ok"), operation="read")
    mod._STATE.reset(t)

    # extract_dir/root_dir/base_dir None branches
    monkeypatch.setattr(mod, "_check_path", lambda _p, **_k: None)
    assert mod._wrap_shutil_unpack_archive(lambda f, d=None, *a, **k: ("ok", f, d))("a")[2] is None
    assert mod._wrap_shutil_make_archive(lambda b, fmt, r=None, bd=None, *a, **k: ("ok", b, fmt, r, bd))("b", "zip")[3] is None

    # subprocess patch branches with non-callable entries
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [str(tmp_path)])
    monkeypatch.setattr(mod.os, "system", None, raising=False)
    monkeypatch.setattr(mod.subprocess, "run", None, raising=False)
    tok = mod.enable_process_guard(
        subject="s",
        access=[_access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path))],
        allow_subprocess=False,
    )
    mod.disable_process_guard(tok)

    # disable branches: no token + inactive and active_count > 0
    mod._ACTIVE = False
    mod.disable_process_guard(None)
    mod._ACTIVE = True
    mod._ACTIVE_COUNT = 2
    mod.disable_process_guard(None)
    assert mod._ACTIVE_COUNT == 1
    mod._ACTIVE = False
    mod._ACTIVE_COUNT = 0
    mod._STATE.set(None)

    # env json non-list branches
    monkeypatch.setenv("DEMOCRAI_NETWORK_SUBJECT", "s")
    monkeypatch.setenv("DEMOCRAI_ACCESS", '"x"')
    with pytest.raises(RuntimeError):
        mod.process_guard_context_from_env()


def test_linux_branch_arcs_remaining(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.linux.network")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    # _run_iptables success path
    monkeypatch.setattr(mod, "_run_command", lambda _cmd: SimpleNamespace(returncode=0, stderr="", stdout=""))
    mod._run_iptables(["iptables", "-L"])

    # _find_active_chain prefixed but non-candidate branch
    monkeypatch.setattr(
        mod,
        "_list_output_rules",
        lambda _cmd: [
            "-A OUTPUT -m cgroup --path grp -j OTHER",
            "-A OUTPUT -m cgroup --path grp -j NOPE",
        ],
    )
    assert mod._find_active_chain("iptables", cgroup_path="grp", candidates=("A", "B")) is None

    # _resolve_endpoint_addresses with unknown family triggers elif false arc
    monkeypatch.setattr(
        mod.socket,
        "getaddrinfo",
        lambda *_a, **_k: [
            (9999, None, None, None, ("x", 1)),
            (mod.socket.AF_INET, None, None, None, ("1.1.1.1", 1)),
        ],
    )
    ipv4, ipv6 = mod._resolve_endpoint_addresses({"host": "h", "port": 1, "protocol": "tcp"})
    assert ipv4 == {"1.1.1.1"} and ipv6 == set()

    # line branches around nameserver parsing
    monkeypatch.setattr(mod.Path, "exists", lambda self: str(self) == "/etc/resolv.conf")
    monkeypatch.setattr(
        mod.Path,
        "read_text",
        lambda self, encoding="utf-8": "nameserver\nnameserver ''\n",
    )
    out = mod._system_dns_endpoints()
    assert len(out) == 2  # second line is accepted host "''"

    # branch 344->346 (ipv4 empty, ipv6 present)
    monkeypatch.setattr(mod, "_resolve_endpoint_addresses", lambda _ep: (set(), {"::1"}))
    ipv4, ipv6 = mod._build_address_maps_from_endpoints(
        [{"host": "h", "port": 443, "protocol": "tcp"}]
    )
    assert ipv4 == {} and ipv6["tcp"][443] == {"::1"}


def test_process_guard_filesystem_operation_classification(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    existing = tmp_path / "existing.txt"
    existing.write_text("x")
    missing = tmp_path / "missing.txt"

    path_operations: list[tuple[str, str]] = []
    pair_operations: list[tuple[str, str, str, str]] = []

    def _capture_path(path, *, operation):
        path_operations.append((str(path), operation))

    def _capture_pair(source, target, *, source_operation, target_operation):
        pair_operations.append(
            (str(source), str(target), source_operation, target_operation)
        )

    monkeypatch.setattr(mod, "_check_path", _capture_path)
    monkeypatch.setattr(mod, "_check_path_pair", _capture_pair)
    monkeypatch.setattr(mod, "_check_fd_kwargs", lambda _kwargs: None)
    monkeypatch.setattr(mod, "_skip_path_check_for_dir_fd", lambda _kwargs: False)
    monkeypatch.setattr(mod, "_skip_path_check_for_fd_path", lambda _path: False)

    mod._wrap_open(lambda _file, *args, **kwargs: None)(existing, "r")
    mod._wrap_open(lambda _file, *args, **kwargs: None)(existing, "w")
    mod._wrap_open(lambda _file, *args, **kwargs: None)(missing, "w")
    mod._wrap_os_open(lambda _path, _flags, *args, **kwargs: None)(
        missing,
        mod.os.O_CREAT | mod.os.O_WRONLY,
    )
    mod._wrap_os_optional_path(lambda _path, *args, **kwargs: None, "delete")(existing)
    mod._wrap_path_method(lambda _self, *args, **kwargs: None, "write_text")(missing)

    assert path_operations == [
        (str(existing), "read"),
        (str(existing), "modify"),
        (str(missing), "create"),
        (str(missing), "create"),
        (str(existing), "delete"),
        (str(missing), "create"),
    ]

    mod._wrap_shutil_path_pair(
        lambda _src, _dst, *args, **kwargs: None,
        "read",
        "create_or_modify",
    )(existing, missing)
    mod._wrap_shutil_path_pair(
        lambda _src, _dst, *args, **kwargs: None,
        "delete",
        "create_or_modify",
    )(existing, existing)

    assert pair_operations == [
        (str(existing), str(missing), "read", "create_or_modify"),
        (str(existing), str(existing), "delete", "create_or_modify"),
    ]


@pytest.mark.linux_only
def test_process_guard_process_calls_can_use_filesystem_execute_approval(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")

    monkeypatch.setattr(
        mod.shutil,
        "which",
        lambda command: "/usr/bin/echo" if command == "echo" else None,
    )
    calls: list[tuple[str, str, bool]] = []

    def _access(path, *, operation, register_request=False):
        calls.append((str(path), operation, bool(register_request)))
        return str(path) == "/usr/bin/echo"

    monkeypatch.setattr(mod, "_external_filesystem_access_allowed", _access)

    token = mod._STATE.set({"subject": "s", "subject_kind": "module", "allow_subprocess": False})
    try:
        allowed = mod._blocked_process_call(
            "subprocess.run",
            lambda *args, **kwargs: ("ok", args, kwargs),
        )
        assert allowed(["echo", "hello"])[0] == "ok"
        assert calls[-1] == ("/usr/bin/echo", "execute", True)

        denied = mod._blocked_process_call(
            "subprocess.run",
            lambda *args, **kwargs: ("ok", args, kwargs),
        )
        with pytest.raises(PermissionError, match="sandbox_subprocess_denied"):
            denied(["missing-binary"])

        with pytest.raises(PermissionError, match="sandbox_filesystem_execute_denied"):
            denied(["/usr/bin/blocked"])
        assert calls[-1] == ("/usr/bin/blocked", "execute", True)
    finally:
        mod._STATE.reset(token)


@pytest.mark.asyncio
async def test_helper_process_branch_arcs_remaining(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.helper_process")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    # _parent_pid_of return None when no PPid line
    monkeypatch.setattr(mod.Path, "read_text", lambda *_a, **_k: "Name:\tpython\n")
    assert mod._parent_pid_of(10) is None

    # watchdog non-pidfd loop sleep path before exit
    monkeypatch.setattr(mod, "_open_parent_pidfd", lambda _p: None)
    state = {"n": 0}

    def _alive_once(_p):
        state["n"] += 1
        return state["n"] < 2

    monkeypatch.setattr(mod, "_parent_pid_is_alive", _alive_once)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    monkeypatch.setattr(mod.os, "_exit", lambda _c: (_ for _ in ()).throw(SystemExit(0)))

    class _Thread:
        def __init__(self, target, **_k):
            self.target = target

        def start(self):
            try:
                self.target()
            except (SystemExit, RuntimeError):
                pass

    monkeypatch.setattr(mod.threading, "Thread", _Thread)
    mod._start_parent_watchdog(20)

    # periodic refresh failed branch
    lock = threading.Lock()
    applied_pids = {7}
    counter = {"n": 0}

    def _sleep(_s):
        counter["n"] += 1
        if counter["n"] > 1:
            raise RuntimeError("stop")
        return None

    monkeypatch.setattr(mod.time, "sleep", _sleep)
    monkeypatch.setattr(mod, "_load_endpoints_from_policy_file", lambda _p: [{"host": "x", "port": 1, "protocol": "tcp"}])
    monkeypatch.setattr(mod, "apply_application_network_endpoints", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    mod._start_policy_refresh_watchdog(
        policy_file=str(tmp_path / "p.json"),
        refresh_seconds=1,
        applied_pids=applied_pids,
        applied_pids_lock=lock,
    )

    # run server final unlink
    sock = tmp_path / "u.sock"
    sock.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod, "_start_parent_watchdog", lambda _p: None)
    monkeypatch.setattr(mod, "_start_policy_refresh_watchdog", lambda **_k: None)

    class _Server:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def serve_forever(self):
            Path(sock).write_text("", encoding="utf-8")
            raise asyncio.CancelledError()

    async def _start(*_a, **_k):
        return _Server()

    monkeypatch.setattr(mod.asyncio, "start_unix_server", _start)
    monkeypatch.setattr(mod, "_socket_owner_ids", lambda: None)
    monkeypatch.setattr(mod.os, "chmod", lambda *_a, **_k: None)
    await mod.run_os_sandbox_helper_server(str(sock), policy_file=str(tmp_path / "p.json"), token="test-token")
    assert not sock.exists()

    # force finally unlink line branch
    sock2 = tmp_path / "u2.sock"
    sock2.write_text("", encoding="utf-8")
    real_exists = Path.exists
    monkeypatch.setattr(
        mod.Path,
        "exists",
        lambda self: True if str(self).endswith("u2.sock") else real_exists(self),
    )
    monkeypatch.setattr(mod.Path, "unlink", lambda self: None)
    await mod.run_os_sandbox_helper_server(str(sock2), policy_file=str(tmp_path / "p.json"), token="test-token")

    # normal server termination path (line after finally)
    sock3 = tmp_path / "u3.sock"
    sock3.write_text("", encoding="utf-8")

    class _ServerDone:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def serve_forever(self):
            return None

    async def _start_done(*_a, **_k):
        return _ServerDone()

    monkeypatch.setattr(mod.asyncio, "start_unix_server", _start_done)
    rc = await mod.run_os_sandbox_helper_server(str(sock3), policy_file=str(tmp_path / "p.json"), token="test-token")
    assert rc == 0

    # finally branch where socket no longer exists
    sock4 = tmp_path / "u4.sock"
    sock4.write_text("", encoding="utf-8")
    real_exists = Path.exists
    monkeypatch.setattr(
        mod.Path,
        "exists",
        lambda self: False if str(self).endswith("u4.sock") else real_exists(self),
    )
    rc2 = await mod.run_os_sandbox_helper_server(str(sock4), policy_file=str(tmp_path / "p.json"), token="test-token")
    assert rc2 == 0


def test_process_guard_branch_arcs_remaining(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [str(tmp_path)])

    # _check_path_pair target allowed branch
    tok = mod._STATE.set(
        _guard_state(
            mod,
            (
                _access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path)),
            ),
        )
    )
    mod._check_path_pair(
        str(tmp_path / "a"),
        str(tmp_path / "b"),
        source_operation="read",
        target_operation="read",
    )
    mod._STATE.reset(tok)

    # enable with allow_subprocess=True while inactive to hit skip arc
    mod._ACTIVE = False
    mod._ACTIVE_COUNT = 0
    t = mod.enable_process_guard(
        subject="s",
        access=[_access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path))],
        allow_subprocess=True,
    )
    mod.disable_process_guard(t)

    # disable restore skip arcs when keys are absent
    mod._ACTIVE = True
    mod._ACTIVE_COUNT = 1
    mod._ORIGINALS.clear()
    mod.disable_process_guard(None)
    mod._ACTIVE = True
    mod._ACTIVE_COUNT = 0
    mod.disable_process_guard(None)

    # no os.fork + non-callable asyncio create_subprocess_* arcs
    monkeypatch.delattr(mod.os, "fork", raising=False)
    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", None, raising=False)
    monkeypatch.setattr(mod.asyncio, "create_subprocess_shell", None, raising=False)
    t2 = mod.enable_process_guard(
        subject="s",
        access=[_access_rule(mod, "module", "s", "filesystem", "read", str(tmp_path))],
        allow_subprocess=False,
    )
    mod.disable_process_guard(t2)


def test_process_guard_nested_context_extends_parent_scope(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [])
    debug_calls = []
    monkeypatch.setattr(
        mod,
        "debug_os_sandbox_flow",
        lambda event, **fields: debug_calls.append((event, fields)),
    )

    parent_dir = tmp_path / "parent"
    child_dir = tmp_path / "child"
    parent_dir.mkdir()
    child_dir.mkdir()

    parent = mod.enable_process_guard(
        subject="module.demo",
        subject_kind="module",
        access=[
            _access_rule(mod, "module", "module.demo", "filesystem", "read", str(parent_dir)),
            _access_rule(mod, "module", "module.demo", "network", "receive", "https://module.local/*"),
        ],
        allow_subprocess=False,
        include_runtime_access=False,
    )
    state_parent = mod._state()
    assert state_parent["subject"] == "module.demo"
    assert state_parent["subject_kind"] == "module"
    assert state_parent["subject_chain"] == [
        {"kind": "module", "name": "module.demo"},
    ]
    assert len(state_parent["subject_access_chain"]) == 1
    assert state_parent["subject_access_chain"][0]["kind"] == "module"
    assert state_parent["subject_access_chain"][0]["name"] == "module.demo"
    assert state_parent["subject_access_chain"][0]["access"] == [
        _access_rule(mod, "module", "module.demo", "filesystem", "read", str(parent_dir)).to_dict(),
        _access_rule(mod, "module", "module.demo", "network", "receive", "https://module.local/*").to_dict(),
    ]
    assert [rule.to_dict() for rule in state_parent["access"]] == [
        _access_rule(mod, "module", "module.demo", "filesystem", "read", str(parent_dir)).to_dict(),
        _access_rule(mod, "module", "module.demo", "network", "receive", "https://module.local/*").to_dict(),
    ]
    assert state_parent["allow_subprocess"] is False
    assert mod._path_allowed(parent_dir / "a.txt", operation="read")
    assert not mod._path_allowed(child_dir / "b.txt", operation="read")

    child = mod.enable_process_guard(
        subject="engine.demo",
        subject_kind="engine",
        access=[
            _access_rule(mod, "engine", "engine.demo", "filesystem", "read", str(child_dir)),
            _access_rule(mod, "engine", "engine.demo", "network", "receive", "https://engine.local/*"),
        ],
        allow_subprocess=True,
    )
    assert debug_calls[-1][0] == "process_guard.nested_access"
    assert debug_calls[-1][1]["parent_subject"] == "module.demo"
    assert debug_calls[-1][1]["child_subject"] == "engine.demo"
    assert debug_calls[-1][1]["parent_filesystem_access"]["read"] == [
        str(parent_dir.resolve())
    ]
    assert debug_calls[-1][1]["child_filesystem_access"]["read"] == [
        str(child_dir.resolve())
    ]
    assert debug_calls[-1][1]["merged_filesystem_access"]["read"] == [
        str(parent_dir.resolve()),
        str(child_dir.resolve()),
    ]
    state_child = mod._state()
    assert state_child["subject"] == "engine.demo"
    assert state_child["subject_kind"] == "engine"
    assert state_child["subject_chain"] == [
        {"kind": "module", "name": "module.demo"},
        {"kind": "engine", "name": "engine.demo"},
    ]
    assert len(state_child["subject_access_chain"]) == 2
    assert state_child["subject_access_chain"][0]["name"] == "module.demo"
    assert state_child["subject_access_chain"][1]["name"] == "engine.demo"
    assert [rule.to_dict() for rule in state_child["access"]] == [
        _access_rule(mod, "module", "module.demo", "filesystem", "read", str(parent_dir)).to_dict(),
        _access_rule(mod, "module", "module.demo", "network", "receive", "https://module.local/*").to_dict(),
        _access_rule(mod, "engine", "engine.demo", "filesystem", "read", str(child_dir)).to_dict(),
        _access_rule(mod, "engine", "engine.demo", "network", "receive", "https://engine.local/*").to_dict(),
    ]
    assert state_child["allow_subprocess"] is True
    assert mod._path_allowed(parent_dir / "a.txt", operation="read")
    assert mod._path_allowed(child_dir / "b.txt", operation="read")

    mod.disable_process_guard(child)
    state_after_child = mod._state()
    assert state_after_child["subject"] == "module.demo"
    assert state_after_child["subject_kind"] == "module"
    assert state_after_child["subject_chain"] == [
        {"kind": "module", "name": "module.demo"},
    ]
    assert len(state_after_child["subject_access_chain"]) == 1
    assert state_after_child["subject_access_chain"][0]["name"] == "module.demo"
    assert [rule.to_dict() for rule in state_after_child["access"]] == [
        _access_rule(mod, "module", "module.demo", "filesystem", "read", str(parent_dir)).to_dict(),
        _access_rule(mod, "module", "module.demo", "network", "receive", "https://module.local/*").to_dict(),
    ]
    assert state_after_child["allow_subprocess"] is False
    assert mod._path_allowed(parent_dir / "a.txt", operation="read")
    assert not mod._path_allowed(child_dir / "b.txt", operation="read")

    mod.disable_process_guard(parent)


def test_process_guard_rmtree_authorizes_composite_delete(tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    target = tmp_path / "staging"
    nested = target / "nested"
    nested.mkdir(parents=True)
    (nested / "artifact.bin").write_bytes(b"x")

    with mod.process_guard_context(
        subject="system",
        subject_kind="module",
        access=[
            _access_rule(mod, "module", "system", "filesystem", "read", str(tmp_path)),
            _access_rule(mod, "module", "system", "filesystem", "delete", str(tmp_path)),
        ],
        include_runtime_access=False,
    ):
        mod.shutil.rmtree(target)

    assert not target.exists()


def test_process_guard_propagates_context_to_thread(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [])

    access = [
        _access_rule(mod, "module", "module.demo", "filesystem", "read", str(tmp_path)),
        _access_rule(mod, "module", "module.demo", "network", "receive", "https://module.local/*"),
    ]
    token = mod.enable_process_guard(
        subject="module.demo",
        subject_kind="module",
        access=access,
        allow_subprocess=False,
        include_runtime_access=False,
    )
    try:
        seen: dict[str, object] = {}

        def _runner():
            seen["state"] = mod._state()

        thread = threading.Thread(target=_runner, name="guard-propagation-test")
        thread.start()
        thread.join(timeout=2)

        assert "state" in seen
        state = seen["state"]
        assert isinstance(state, dict)
        assert state["subject"] == "module.demo"
        assert state["subject_kind"] == "module"
        assert state["subject_chain"] == [{"kind": "module", "name": "module.demo"}]
        assert len(state["subject_access_chain"]) == 1
        assert state["subject_access_chain"][0]["access"] == [rule.to_dict() for rule in access]
    finally:
        mod.disable_process_guard(token)


def test_process_guard_propagates_context_to_threadpool(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [])

    access = [
        _access_rule(mod, "engine", "engine.demo", "filesystem", "read", str(tmp_path)),
        _access_rule(mod, "engine", "engine.demo", "network", "receive", "https://engine.local/*"),
    ]
    token = mod.enable_process_guard(
        subject="engine.demo",
        subject_kind="engine",
        access=access,
        allow_subprocess=False,
        include_runtime_access=False,
    )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(mod._state)
            state = future.result(timeout=2)

        assert state["subject"] == "engine.demo"
        assert state["subject_kind"] == "engine"
        assert state["subject_chain"] == [{"kind": "engine", "name": "engine.demo"}]
        assert len(state["subject_access_chain"]) == 1
        assert state["subject_access_chain"][0]["access"] == [rule.to_dict() for rule in access]
    finally:
        mod.disable_process_guard(token)


@pytest.mark.linux_only
def test_process_guard_engine_system_read_baseline_allows_os_release_only_with_explicit_rule(monkeypatch, tmp_path: Path):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.setattr(mod, "_runtime_filesystem_read_paths", lambda: [])
    monkeypatch.setattr(mod, "runtime_system_read_paths", lambda: ["/etc/os-release", "/usr"])

    access = [
        _access_rule(mod, "engine", "engine.demo", "filesystem", "read", path)
        for path in mod.runtime_system_read_paths()
    ]

    with mod.process_guard_context(
        subject="engine.demo",
        subject_kind="engine",
        access=access,
        include_runtime_access=False,
        inherit_parent_access=False,
    ):
        with open("/etc/os-release", encoding="utf-8") as handle:
            assert handle.read(1)
        assert not mod._path_allowed(tmp_path / "config.yaml", operation="read")


def test_process_guard_allows_internal_runtime_env_json(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.process_guard")
    monkeypatch.delenv("DEMOCRAI_RUNTIME_ENV_JSON", raising=False)
    monkeypatch.delenv("DEMOCRAI_BLOCKED_TEST", raising=False)

    try:
        with mod.process_guard_context(
            subject="engine.demo",
            subject_kind="engine",
            access=(),
            include_runtime_access=False,
            inherit_parent_access=False,
        ):
            os.environ["DEMOCRAI_RUNTIME_ENV_JSON"] = '{"os":"linux"}'
            assert os.environ["DEMOCRAI_RUNTIME_ENV_JSON"] == '{"os":"linux"}'
            with pytest.raises(PermissionError, match="sandbox_env_denied:DEMOCRAI_BLOCKED_TEST"):
                os.environ["DEMOCRAI_BLOCKED_TEST"] = "1"
    finally:
        os.environ.pop("DEMOCRAI_RUNTIME_ENV_JSON", None)
        os.environ.pop("DEMOCRAI_BLOCKED_TEST", None)
