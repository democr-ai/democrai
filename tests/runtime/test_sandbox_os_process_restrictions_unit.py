from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.sandbox.os.base import NoopOsSandboxProvider
import democrai.core.infrastructure.sandbox.os.linux.landlock as landlock_mod
import democrai.core.infrastructure.sandbox.os.linux.process_restrictions as linux_restrictions_mod
import democrai.core.infrastructure.sandbox.os.linux.seccomp as seccomp_mod
import democrai.core.infrastructure.sandbox.os.current_process as current_process_mod


def test_seccomp_support_and_apply_branches(monkeypatch):
    monkeypatch.setattr(seccomp_mod, "_arch_info", lambda: ("x86_64", 1, [59]))
    monkeypatch.setattr(seccomp_mod.ctypes.util, "find_library", lambda _n: "libc.so.6")
    monkeypatch.setattr(seccomp_mod.sys, "platform", "linux")
    assert seccomp_mod.is_seccomp_supported() is True

    class _Libc:
        def __init__(self):
            self.calls = []

        def prctl(self, *args):
            self.calls.append(("prctl", args))
            return 0

        def syscall(self, *args):
            self.calls.append(("syscall", args))
            if len([c for c in self.calls if c[0] == "syscall"]) == 1:
                return -1
            return 0

    fake = _Libc()
    monkeypatch.setattr(seccomp_mod.ctypes, "CDLL", lambda *_a, **_k: fake)
    seccomp_mod.apply_seccomp_blocklist()
    assert len([c for c in fake.calls if c[0] == "syscall"]) == 2

    monkeypatch.setattr(seccomp_mod.ctypes.util, "find_library", lambda _n: None)
    with pytest.raises(RuntimeError, match="libc_not_found"):
        seccomp_mod.apply_seccomp_blocklist()

    monkeypatch.setattr(seccomp_mod.ctypes.util, "find_library", lambda _n: "libc.so.6")

    class _LibcPrctlFail:
        def prctl(self, *_a):
            return -1

        def syscall(self, *_a):
            return 0

    monkeypatch.setattr(seccomp_mod.ctypes, "CDLL", lambda *_a, **_k: _LibcPrctlFail())
    monkeypatch.setattr(seccomp_mod.ctypes, "get_errno", lambda: 12)
    with pytest.raises(RuntimeError, match="prctl_no_new_privs:12"):
        seccomp_mod.apply_seccomp_blocklist()

    class _LibcSyscallFail:
        def prctl(self, *_a):
            return 0

        def syscall(self, *_a):
            return -1

    monkeypatch.setattr(seccomp_mod.ctypes, "CDLL", lambda *_a, **_k: _LibcSyscallFail())
    monkeypatch.setattr(seccomp_mod.ctypes, "get_errno", lambda: 95)
    with pytest.raises(RuntimeError, match="syscall_seccomp:95"):
        seccomp_mod.apply_seccomp_blocklist()

    monkeypatch.setattr(seccomp_mod.sys, "platform", "darwin")
    seccomp_mod.apply_seccomp_blocklist()
    assert seccomp_mod.is_seccomp_supported() is False


def test_landlock_status_and_apply_branches(monkeypatch):
    monkeypatch.setattr(landlock_mod.sys, "platform", "linux")
    monkeypatch.setattr(landlock_mod, "_libc", lambda: object())
    monkeypatch.setattr(landlock_mod, "_syscall", lambda *_a, **_k: 3)
    assert landlock_mod.get_landlock_abi_version() == 3
    status = landlock_mod.get_landlock_status()
    assert status["supported"] is True
    assert status["abi_version"] == 3

    monkeypatch.setattr(landlock_mod, "get_landlock_abi_version", lambda: 0)
    with pytest.raises(RuntimeError, match="landlock_not_supported"):
        landlock_mod.apply_landlock_filesystem_rules(read_only_paths=[], read_write_paths=[])

    call_log: list[tuple[str, int]] = []

    class _Libc:
        def prctl(self, *_a):
            return 0

    def _syscall(lib, nr, *args):  # noqa: ARG001
        call_log.append(("syscall", nr))
        if nr == landlock_mod._SYS_LANDLOCK_CREATE_RULESET:
            return 50
        if nr == landlock_mod._SYS_LANDLOCK_RESTRICT_SELF:
            return 0
        return 0

    close_calls: list[int] = []
    monkeypatch.setattr(landlock_mod, "_libc", lambda: _Libc())
    monkeypatch.setattr(landlock_mod, "_syscall", _syscall)
    monkeypatch.setattr(landlock_mod, "get_landlock_abi_version", lambda: 4)
    monkeypatch.setattr(landlock_mod.os.path, "realpath", lambda p: str(p))
    monkeypatch.setattr(landlock_mod.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(landlock_mod.os, "open", lambda _p, _f: 77)
    monkeypatch.setattr(landlock_mod.os, "stat", lambda _p: SimpleNamespace(st_mode=0o040755))
    monkeypatch.setattr(landlock_mod.os, "close", lambda fd: close_calls.append(fd))
    landlock_mod.apply_landlock_filesystem_rules(
        read_only_paths=["/ro"],
        read_write_paths=["/rw"],
    )
    assert any(nr == landlock_mod._SYS_LANDLOCK_ADD_RULE for _, nr in call_log)
    assert 50 in close_calls

    def _syscall_fail_write_rule(lib, nr, *args):  # noqa: ARG001
        if nr == landlock_mod._SYS_LANDLOCK_CREATE_RULESET:
            return 50
        if nr == landlock_mod._SYS_LANDLOCK_ADD_RULE:
            return -1
        if nr == landlock_mod._SYS_LANDLOCK_RESTRICT_SELF:
            return 0
        return 0

    monkeypatch.setattr(landlock_mod, "_syscall", _syscall_fail_write_rule)
    monkeypatch.setattr(landlock_mod.ctypes, "get_errno", lambda: 13)
    monkeypatch.setattr(landlock_mod.os, "stat", lambda _p: SimpleNamespace(st_mode=0o100644))
    with pytest.raises(RuntimeError, match="landlock_add_rule_failed:/dev/null:13"):
        landlock_mod.apply_landlock_filesystem_rules(
            read_only_paths=[],
            read_write_paths=["/dev/null"],
        )

    monkeypatch.setattr(landlock_mod, "_syscall", lambda _l, nr, *_a: 50 if nr == landlock_mod._SYS_LANDLOCK_CREATE_RULESET else -1)
    monkeypatch.setattr(landlock_mod.ctypes, "get_errno", lambda: 1)
    with pytest.raises(RuntimeError, match="landlock_restrict_self_failed:1"):
        landlock_mod.apply_landlock_filesystem_rules(read_only_paths=["/x"], read_write_paths=[])

    monkeypatch.setattr(landlock_mod.sys, "platform", "win32")
    monkeypatch.setattr(landlock_mod, "get_landlock_abi_version", lambda: 0)
    assert landlock_mod.get_landlock_abi_version() == 0
    landlock_mod.apply_landlock_filesystem_rules(read_only_paths=[], read_write_paths=[])


def test_landlock_libc_falls_back_to_loaded_process_libc(monkeypatch):
    calls = []
    monkeypatch.setattr(landlock_mod.ctypes.util, "find_library", lambda _name: None)
    monkeypatch.setattr(
        landlock_mod.ctypes,
        "CDLL",
        lambda name, **kwargs: calls.append((name, kwargs)) or object(),
    )

    assert landlock_mod._libc() is not None
    assert calls == [(None, {"use_errno": True})]


def test_linux_process_restrictions_apply_and_status(monkeypatch):
    events: list[str] = []

    class _Cfg:
        def get(self, key, default=None):
            data = {
                "sandbox.os.landlock.extra_read_paths": ["/ro-extra"],
                "sandbox.os.landlock.extra_write_paths": ["/rw-extra"],
            }
            return data.get(key, default)

    monkeypatch.setattr(linux_restrictions_mod, "_resolve_config", lambda _cfg=None: _Cfg())
    monkeypatch.setattr(linux_restrictions_mod, "_collect_system_read_only_paths", lambda: ["/ro"])
    monkeypatch.setattr(linux_restrictions_mod, "_collect_app_read_write_paths", lambda _cfg: ["/rw"])
    monkeypatch.setattr(linux_restrictions_mod, "_dedupe_existing", lambda paths: list(dict.fromkeys(paths)))
    monkeypatch.setattr(linux_restrictions_mod, "debug_os_sandbox_flow", lambda event, **_k: events.append(event))

    seccomp_calls: list[str] = []
    landlock_calls: list[dict[str, list[str]]] = []
    monkeypatch.setattr(linux_restrictions_mod, "is_seccomp_supported", lambda: True)
    monkeypatch.setattr(linux_restrictions_mod, "is_landlock_supported", lambda: True)
    monkeypatch.setattr(linux_restrictions_mod, "apply_seccomp_blocklist", lambda: seccomp_calls.append("ok"))
    monkeypatch.setattr(
        linux_restrictions_mod,
        "apply_landlock_filesystem_rules",
        lambda **kwargs: landlock_calls.append(kwargs),
    )

    res = linux_restrictions_mod.apply_process_restrictions(_Cfg())
    assert res["seccomp"]["applied"] is True
    assert res["landlock"]["applied"] is True
    assert seccomp_calls == ["ok"]
    assert landlock_calls and "/ro-extra" in landlock_calls[0]["read_only_paths"]
    assert "process_restrictions.seccomp_applied" in events
    assert "process_restrictions.landlock_applied" in events

    monkeypatch.setattr(linux_restrictions_mod, "apply_seccomp_blocklist", lambda: (_ for _ in ()).throw(RuntimeError("sec-bad")))
    with pytest.raises(RuntimeError, match="sec-bad"):
        linux_restrictions_mod.apply_process_restrictions(_Cfg())

    monkeypatch.setattr(linux_restrictions_mod, "apply_seccomp_blocklist", lambda: None)
    monkeypatch.setattr(linux_restrictions_mod, "apply_landlock_filesystem_rules", lambda **_k: (_ for _ in ()).throw(RuntimeError("ll-bad")))
    with pytest.raises(RuntimeError, match="ll-bad"):
        linux_restrictions_mod.apply_process_restrictions(_Cfg())

    status = linux_restrictions_mod.get_process_restrictions_status(_Cfg())
    assert "supported" in status["seccomp"] or status["seccomp"]
    assert "enabled" not in status["seccomp"]
    assert "enabled" not in status["landlock"]


def test_linux_app_read_write_paths_include_device_nodes():
    paths = linux_restrictions_mod._collect_app_read_write_paths(None)
    # /dev/null must be writable: subprocess stdin/stdout DEVNULL redirection
    # opens it O_RDWR, which a read-only /dev rule does not cover.
    assert "/dev/null" in paths
    assert "/dev/shm" in paths


def test_linux_app_read_write_paths_include_process_self_proc():
    # The core's Landlock layer is the most restrictive ancestor every
    # sandboxed descendant inherits, and layers can only narrow. Native
    # runtimes (CUDA/torch) write /proc/self/task/<tid>/comm to name threads;
    # if the core grants /proc read-only, a child engine worker cannot
    # re-grant write and cuInit fails with error 304. The core must grant it.
    paths = linux_restrictions_mod._collect_app_read_write_paths(None)
    assert "/proc" in paths


def test_linux_app_read_write_paths_cover_core_endpoint_dir(monkeypatch):
    # The launcher unlinks the endpoint file before spawning (its appearance
    # is the readiness signal), so the core needs create access on the
    # PARENT directory, not on the not-yet-existing file.
    monkeypatch.setenv(
        "DEMOCRAI_CORE_ENDPOINT_FILE",
        "/tmp/democrai-core-endpoint-test.json",
    )
    paths = linux_restrictions_mod._collect_app_read_write_paths(None)
    assert "/tmp" in paths


def test_linux_process_restrictions_unsupported_kernel_hard_fails(monkeypatch):
    monkeypatch.setattr(linux_restrictions_mod, "_resolve_config", lambda _cfg=None: None)
    monkeypatch.setattr(linux_restrictions_mod, "debug_os_sandbox_flow", lambda *_a, **_k: None)
    monkeypatch.setattr(linux_restrictions_mod, "get_seccomp_status", lambda: {"supported": False, "machine": "x"})
    monkeypatch.setattr(linux_restrictions_mod, "get_landlock_status", lambda: {"supported": False, "abi_version": 0})
    applied: list[str] = []
    monkeypatch.setattr(linux_restrictions_mod, "apply_seccomp_blocklist", lambda: applied.append("seccomp"))
    monkeypatch.setattr(linux_restrictions_mod, "apply_landlock_filesystem_rules", lambda **_k: applied.append("landlock"))

    monkeypatch.setattr(linux_restrictions_mod, "is_seccomp_supported", lambda: False)
    monkeypatch.setattr(linux_restrictions_mod, "is_landlock_supported", lambda: True)
    with pytest.raises(RuntimeError, match="os_sandbox_seccomp_unsupported"):
        linux_restrictions_mod.apply_process_restrictions(None)

    monkeypatch.setattr(linux_restrictions_mod, "is_seccomp_supported", lambda: True)
    monkeypatch.setattr(linux_restrictions_mod, "is_landlock_supported", lambda: False)
    with pytest.raises(RuntimeError, match="os_sandbox_landlock_unsupported"):
        linux_restrictions_mod.apply_process_restrictions(None)

    # Support is verified for both mechanisms before applying either one.
    assert applied == []


def test_os_process_restrictions_dispatches_through_provider(monkeypatch):
    calls: list[str] = []

    class _Provider:
        def apply_current_process_os_sandbox(self, config):
            calls.append(config.get("marker"))
            return {"provider": "P", "applied": True, "skipped": False, "error": None}

        def get_current_process_os_sandbox_status(self, config):
            return {"provider": "P", "supported": True, "marker": config.get("marker")}

    cfg = SimpleNamespace(get=lambda key, default=None: {
        "sandbox.os.enabled": True,
        "marker": "cfg",
    }.get(key, default))
    monkeypatch.setattr(current_process_mod, "_current_provider", lambda: _Provider())

    assert current_process_mod.is_os_sandbox_enabled(cfg) is True
    assert current_process_mod.apply_current_process_os_sandbox(cfg)["applied"] is True
    assert calls == ["cfg"]
    status = current_process_mod.get_current_process_os_sandbox_status(cfg)
    assert status["enabled"] is True
    assert status["provider"] == "P"

    monkeypatch.setattr(current_process_mod, "_resolve_config", lambda _cfg=None: None)
    assert current_process_mod.is_os_sandbox_enabled(None) is False
    assert current_process_mod.apply_current_process_os_sandbox(None)["skipped"] is True


def test_os_process_restrictions_noop_provider_fails_when_enabled(monkeypatch):
    cfg = SimpleNamespace(get=lambda key, default=None: {
        "sandbox.os.enabled": True,
    }.get(key, default))
    monkeypatch.setattr(
        current_process_mod,
        "_current_provider",
        lambda: NoopOsSandboxProvider(),
    )

    with pytest.raises(RuntimeError, match="os_sandbox_provider_unavailable"):
        current_process_mod.apply_current_process_os_sandbox(cfg)


def test_process_restrictions_resolve_config_from_app_context(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.foundation.app",
        SimpleNamespace(app_ctx=lambda: SimpleNamespace(config="CFG")),
    )
    assert current_process_mod._resolve_config(None) == "CFG"

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.foundation.app",
        SimpleNamespace(app_ctx=lambda: (_ for _ in ()).throw(RuntimeError("x"))),
    )
    assert current_process_mod._resolve_config(None) is None
