from __future__ import annotations

import os
import ctypes
from types import SimpleNamespace

import pytest

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.sandbox.os import base
from democrai.core.infrastructure.sandbox.os import factory
from democrai.core.infrastructure.sandbox.os import launch_policy
from democrai.core.infrastructure.sandbox import launcher as sandbox_launcher
from democrai.core.infrastructure.sandbox.os.linux.provider import LinuxOsSandboxProvider
from democrai.core.infrastructure.sandbox.os.linux import provider as linux_provider
from democrai.core.infrastructure.sandbox.os.macos.provider import (
    MacOSOsSandboxProvider,
    seatbelt_profile,
)
from democrai.core.infrastructure.sandbox.os.windows import appcontainer as windows_appcontainer
from democrai.core.infrastructure.sandbox.os.windows import provider as windows_provider
from democrai.core.infrastructure.sandbox.os.windows.provider import WindowsOsSandboxProvider


def _rule(subject, resource_type: str, operation: str, target: str):
    return AccessManifestRule(
        subject=subject,
        resource=AccessResource.create(
            resource_type=resource_type,
            operation=operation,
            target=target,
        ),
    )


def test_launch_policy_network_modes_from_access_rules(tmp_path):
    subject = AccessSubject.create("module", "demo")
    state_without_network = {
        "subject": "demo",
        "subject_kind": "module",
        "access": (
            _rule(subject, "filesystem", "read", str(tmp_path)),
        ),
    }

    no_network = launch_policy.build_launch_policy(
        command=["echo", "ok"],
        cwd=None,
        env=None,
        state=state_without_network,
    )
    assert no_network.network_mode == launch_policy.NETWORK_DENY
    assert no_network.network_endpoints == ()

    state_with_network = {
        **state_without_network,
        "access": (
            *state_without_network["access"],
            _rule(subject, "network", "connect", "https://api.local"),
        ),
    }
    with_network = launch_policy.build_launch_policy(
        command=["echo", "ok"],
        cwd=None,
        env=None,
        state=state_with_network,
    )
    assert with_network.network_mode == launch_policy.NETWORK_PROXY
    assert with_network.network_endpoints[0].target == "https://api.local"

    trusted = launch_policy.build_launch_policy(
        command=["echo", "ok"],
        cwd=None,
        env=None,
        state=state_with_network,
        allow_all_network=True,
    )
    assert trusted.network_mode == launch_policy.NETWORK_ALLOW_ALL


def test_launch_policy_payload_roundtrip_uses_v2_access(tmp_path):
    subject = AccessSubject.create("engine", "onnx")
    policy = launch_policy.build_launch_policy(
        command=["python", "-V"],
        cwd=str(tmp_path),
        env={"A": "B"},
        state={
            "subject": "onnx",
            "subject_kind": "engine",
            "subject_chain": [{"kind": "module", "name": "system"}, {"kind": "engine", "name": "onnx"}],
            "user_id": 7,
            "access": (
                _rule(subject, "filesystem", "execute", "/bin/python"),
                _rule(subject, "network", "connect", "https://api.local:443"),
            ),
        },
    )
    payload = policy.to_dict()

    restored = launch_policy.policy_from_payload(payload)
    assert restored.command == ["python", "-V"]
    assert restored.cwd == str(tmp_path)
    assert restored.env == {"A": "B"}
    assert restored.filesystem_access[0].operation == "execute"
    assert restored.filesystem_access[0].target == "/bin/python"
    assert restored.network_mode == launch_policy.NETWORK_PROXY
    assert restored.subject_chain[0] == {"kind": "module", "name": "system"}


def test_launch_policy_rejects_legacy_payload():
    with pytest.raises(RuntimeError, match="sandbox_launch_policy_version_unsupported"):
        launch_policy.policy_from_payload(
            {
                "command": ["echo", "ok"],
                "access": [
                    {
                        "resource": {
                            "resource_type": "filesystem",
                            "operation": "read",
                            "target": "/tmp",
                        }
                    }
                ],
            }
        )


def test_provider_dispatch(monkeypatch):
    assert isinstance(factory.get_os_sandbox_provider("linux"), LinuxOsSandboxProvider)
    assert isinstance(factory.get_os_sandbox_provider("darwin"), MacOSOsSandboxProvider)
    assert isinstance(factory.get_os_sandbox_provider("win32"), WindowsOsSandboxProvider)
    assert isinstance(factory.get_os_sandbox_provider("plan9"), base.NoopOsSandboxProvider)


def test_network_env_keeps_explicit_empty_env(monkeypatch):
    monkeypatch.setenv("DEMOCRAI_PARENT_ONLY", "secret")
    policy = launch_policy.SandboxLaunchPolicy(
        command=["echo", "ok"],
        cwd=None,
        env={},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_DENY,
    )

    assert base.network_env(policy) == {}


def test_network_env_reuses_existing_proxy_env(monkeypatch):
    monkeypatch.setattr(
        base,
        "proxy_url_for_policy",
        lambda _policy: (_ for _ in ()).throw(AssertionError("proxy_session_started")),
    )
    policy = launch_policy.SandboxLaunchPolicy(
        command=["echo", "ok"],
        cwd=None,
        env={"ALL_PROXY": "http://127.0.0.1:4123"},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_PROXY,
        network_endpoints=(launch_policy.NetworkLaunchEndpoint("connect", "https://api.local"),),
    )

    env = base.network_env(policy)

    assert env["ALL_PROXY"] == "http://127.0.0.1:4123"
    assert env["HTTP_PROXY"] == "http://127.0.0.1:4123"


def test_network_env_ignores_external_proxy_env(monkeypatch):
    monkeypatch.setattr(
        base,
        "proxy_url_for_policy",
        lambda _policy: "http://127.0.0.1:5123",
    )
    policy = launch_policy.SandboxLaunchPolicy(
        command=["echo", "ok"],
        cwd=None,
        env={"ALL_PROXY": "http://proxy.example.com:8080"},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_PROXY,
        network_endpoints=(launch_policy.NetworkLaunchEndpoint("connect", "https://api.local"),),
    )

    env = base.network_env(policy)

    assert env["ALL_PROXY"] == "http://127.0.0.1:5123"
    assert env["HTTP_PROXY"] == "http://127.0.0.1:5123"


def test_provider_capabilities_are_explicit():
    linux = LinuxOsSandboxProvider().capabilities()
    macos = MacOSOsSandboxProvider().capabilities()
    windows = WindowsOsSandboxProvider().capabilities()

    assert linux.filesystem and linux.network_deny and linux.network_proxy and linux.execute
    assert macos.filesystem and macos.network_deny and not macos.network_proxy and macos.execute
    assert windows.filesystem and windows.network_deny and windows.network_proxy and windows.execute


def test_base_provider_fails_closed_for_strict_policy():
    policy = launch_policy.SandboxLaunchPolicy(
        command=["echo", "ok"],
        cwd=None,
        env={},
        filesystem_access=(launch_policy.FilesystemLaunchAccess("read", "/tmp"),),
        network_mode=launch_policy.NETWORK_DENY,
    )

    with pytest.raises(RuntimeError, match="os_sandbox_policy_not_supported"):
        base.BaseOsSandboxProvider().run(policy)


def test_linux_provider_proxy_allows_only_proxy_endpoint(monkeypatch, tmp_path):
    policy = launch_policy.SandboxLaunchPolicy(
        command=["echo", "ok"],
        cwd=None,
        env={},
        filesystem_access=(
            launch_policy.FilesystemLaunchAccess("read", str(tmp_path / "ro")),
            launch_policy.FilesystemLaunchAccess("modify", str(tmp_path / "rw")),
        ),
        network_mode=launch_policy.NETWORK_PROXY,
        network_endpoints=(
            launch_policy.NetworkLaunchEndpoint("connect", "https://api.local:443"),
        ),
    )
    landlock_calls = []
    network_calls = []
    exec_calls = []
    monkeypatch.setattr(base, "proxy_url_for_policy", lambda _policy: "http://tok:x@127.0.0.1:4123")
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.linux.landlock.is_landlock_supported",
        lambda: True,
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.linux.landlock.apply_landlock_filesystem_rules",
        lambda **kwargs: landlock_calls.append(kwargs),
    )
    monkeypatch.setattr(
        linux_provider.importlib,
        "import_module",
        lambda name: SimpleNamespace(
            apply_application_network_endpoints_with_helper=lambda endpoints, pid=None: network_calls.append((endpoints, pid))
        )
        if name == "democrai.core.infrastructure.sandbox.os.helper"
        else __import__(name, fromlist=["*"]),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.linux.network.apply_application_network_endpoints",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("direct_linux_network_backend_called")),
    )
    monkeypatch.setattr(
        base.os,
        "execvpe",
        lambda *args: exec_calls.append(args),
    )

    LinuxOsSandboxProvider().run(policy)

    assert landlock_calls == [
        {
            "read_only_paths": [str(tmp_path / "ro")],
            "read_write_paths": [str(tmp_path / "rw")],
        }
    ]
    assert network_calls[0][0] == [
        {
            "host": "127.0.0.1",
            "port": 4123,
            "protocol": "tcp",
            "source": "sandbox_proxy",
            "purpose": "sandbox_network_proxy",
        }
    ]
    assert exec_calls


def test_linux_provider_deny_applies_empty_network_allowlist(monkeypatch):
    policy = launch_policy.SandboxLaunchPolicy(
        command=["echo", "ok"],
        cwd=None,
        env={},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_DENY,
    )
    network_calls = []
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.linux.landlock.is_landlock_supported",
        lambda: False,
    )
    monkeypatch.setattr(
        linux_provider.importlib,
        "import_module",
        lambda name: SimpleNamespace(
            apply_application_network_endpoints_with_helper=lambda endpoints, pid=None: network_calls.append((endpoints, pid))
        )
        if name == "democrai.core.infrastructure.sandbox.os.helper"
        else __import__(name, fromlist=["*"]),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.linux.network.apply_application_network_endpoints",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("direct_linux_network_backend_called")),
    )
    monkeypatch.setattr(base.os, "execvpe", lambda *_a: None)

    LinuxOsSandboxProvider().run(policy)

    assert network_calls == [([], os.getpid())]


def test_linux_provider_maps_dev_null_modify_to_read_write_only(monkeypatch):
    policy = launch_policy.SandboxLaunchPolicy(
        command=["python", "-V"],
        cwd=None,
        env={},
        filesystem_access=(
            launch_policy.FilesystemLaunchAccess("read", "/dev"),
            launch_policy.FilesystemLaunchAccess("modify", "/dev/null"),
        ),
        network_mode=launch_policy.NETWORK_ALLOW_ALL,
    )
    landlock_calls = []
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.linux.landlock.is_landlock_supported",
        lambda: True,
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.linux.landlock.apply_landlock_filesystem_rules",
        lambda **kwargs: landlock_calls.append(kwargs),
    )
    monkeypatch.setattr(base.os, "execvpe", lambda *_a: None)

    LinuxOsSandboxProvider().run(policy)

    assert landlock_calls == [
        {
            "read_only_paths": ["/dev"],
            "read_write_paths": ["/dev/null"],
        }
    ]


def test_macos_proxy_profile_allows_only_loopback_proxy():
    policy = launch_policy.SandboxLaunchPolicy(
        command=["python", "-V"],
        cwd=None,
        env={},
        filesystem_access=(
            launch_policy.FilesystemLaunchAccess("read", "/tmp/ro"),
            launch_policy.FilesystemLaunchAccess("modify", "/tmp/rw"),
        ),
        network_mode=launch_policy.NETWORK_PROXY,
        network_endpoints=(launch_policy.NetworkLaunchEndpoint("connect", "https://api.local"),),
    )

    profile = seatbelt_profile(policy, proxy_url="http://127.0.0.1:4123")

    assert "(deny default)" in profile
    assert "(allow ipc-posix-shm*)" in profile
    assert '(allow network-outbound (remote tcp "127.0.0.1:4123"))' in profile
    assert '(allow file-read* (subpath "/tmp/ro"))' in profile
    assert '(allow file-read* file-write* (subpath "/tmp/rw"))' in profile


def test_macos_execute_allows_literal_and_subpath():
    policy = launch_policy.SandboxLaunchPolicy(
        command=["python", "-V"],
        cwd=None,
        env={},
        filesystem_access=(
            launch_policy.FilesystemLaunchAccess("execute", "/opt/runtime/bin"),
        ),
        network_mode=launch_policy.NETWORK_DENY,
    )

    profile = seatbelt_profile(policy)

    assert '(allow file-read* (literal "/opt/runtime/bin"))' in profile
    assert '(allow file-read* (subpath "/opt/runtime/bin"))' in profile


def test_macos_proxy_requires_loopback_proxy():
    policy = launch_policy.SandboxLaunchPolicy(
        command=["python", "-V"],
        cwd=None,
        env={},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_PROXY,
        network_endpoints=(launch_policy.NetworkLaunchEndpoint("connect", "https://api.local"),),
    )

    with pytest.raises(RuntimeError, match="macos_sandbox_proxy_unenforceable"):
        seatbelt_profile(policy, proxy_url="http://10.0.0.8:8080")


def test_macos_proxy_policy_fails_closed_until_verified():
    policy = launch_policy.SandboxLaunchPolicy(
        command=["python", "-V"],
        cwd=None,
        env={},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_PROXY,
        network_endpoints=(launch_policy.NetworkLaunchEndpoint("connect", "https://api.local"),),
    )

    with pytest.raises(RuntimeError, match="macos_sandbox_proxy_unenforceable"):
        MacOSOsSandboxProvider().prepare(policy)


def test_windows_provider_fails_closed_when_appcontainer_unavailable(monkeypatch):
    policy = launch_policy.SandboxLaunchPolicy(
        command=["cmd", "/c", "echo ok"],
        cwd=None,
        env={},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_DENY,
    )
    monkeypatch.setattr(windows_appcontainer, "is_windows", lambda: False)
    monkeypatch.setattr(windows_provider, "is_windows", lambda: False)

    with pytest.raises(RuntimeError, match="windows_sandbox_appcontainer_unavailable"):
        WindowsOsSandboxProvider().run(policy)


def test_windows_provider_prepares_appcontainer_before_launch(monkeypatch):
    policy = launch_policy.SandboxLaunchPolicy(
        command=["cmd", "/c", "echo ok"],
        cwd=None,
        env={"A": "B"},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_DENY,
    )
    calls = []
    prepared = windows_appcontainer.WindowsPreparedSandbox(
        appcontainer_name="democrai.test",
        package_sid="S-1-15-2-1",
        proxy_url="",
    )
    monkeypatch.setattr(windows_provider, "is_windows", lambda: True)
    monkeypatch.setattr(
        windows_provider,
        "prepare_windows_appcontainer",
        lambda prepared_policy, proxy_url="": calls.append(("prepare", prepared_policy, proxy_url)) or prepared,
    )
    monkeypatch.setattr(
        windows_provider,
        "launch_appcontainer_process",
        lambda launch_policy_value, prepared_value, env: calls.append(("launch", launch_policy_value, prepared_value, env)) or 7,
    )

    with pytest.raises(SystemExit) as exc:
        WindowsOsSandboxProvider().run(policy)

    assert exc.value.code == 7
    assert calls[0][0] == "prepare"
    assert calls[1][0] == "launch"
    assert calls[1][2] == prepared
    assert calls[1][3] == {"A": "B"}


def test_windows_shared_memory_package_sid_derives_appcontainer_sid(monkeypatch):
    policy = launch_policy.SandboxLaunchPolicy(
        command=["cmd", "/c", "echo ok"],
        cwd=None,
        env={},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_DENY,
        subject="docling",
        subject_kind="extractor",
    )
    calls = []
    monkeypatch.setattr(
        windows_appcontainer,
        "_require_windows_appcontainer",
        lambda: calls.append(("require",)),
    )
    monkeypatch.setattr(
        windows_appcontainer,
        "_derive_appcontainer_sid",
        lambda package_name: calls.append(("derive", package_name)) or object(),
    )
    monkeypatch.setattr(
        windows_appcontainer,
        "_sid_to_string",
        lambda _sid: "S-1-15-2-1",
    )

    package_sid = windows_appcontainer.shared_memory_package_sid(policy)

    assert package_sid == "S-1-15-2-1"
    assert calls[0] == ("require",)
    assert calls[1][0] == "derive"
    assert calls[1][1].startswith("democrai.extractor.docling.")


def test_launcher_popen_attaches_windows_shared_memory_sid(monkeypatch, tmp_path):
    process = SimpleNamespace()
    popen_calls = []
    written_policies = []
    monkeypatch.setattr(sandbox_launcher.sys, "platform", "win32")
    monkeypatch.setattr(sandbox_launcher, "_os_sandbox_enabled", lambda: True)
    monkeypatch.setattr(sandbox_launcher, "_with_os_sandbox_helper_env", lambda env: dict(env or {}))
    monkeypatch.setattr(
        sandbox_launcher,
        "_write_policy",
        lambda policy: written_policies.append(policy) or tmp_path / "policy.json",
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.windows.appcontainer.shared_memory_package_sid",
        lambda _policy: "S-1-15-2-1",
    )
    monkeypatch.setattr(
        sandbox_launcher.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)) or process,
    )

    result = sandbox_launcher.popen(
        ["python", "-V"],
        env={"A": "B"},
        state={
            "subject": "docling",
            "subject_kind": "extractor",
            "access": (),
        },
    )

    assert result is process
    assert getattr(result, "democrai_os_sandbox_appcontainer_sid") == "S-1-15-2-1"
    assert popen_calls[0][1]["env"]["DEMOCRAI_OS_SANDBOX_APPCONTAINER_SID"] == "S-1-15-2-1"
    assert written_policies[0].env["DEMOCRAI_OS_SANDBOX_APPCONTAINER_SID"] == "S-1-15-2-1"


def test_windows_appcontainer_maps_acl_and_loopback(monkeypatch, tmp_path):
    policy = launch_policy.SandboxLaunchPolicy(
        command=["cmd", "/c", "echo ok"],
        cwd=None,
        env={},
        filesystem_access=(
            launch_policy.FilesystemLaunchAccess("read", str(tmp_path / "ro")),
            launch_policy.FilesystemLaunchAccess("modify", str(tmp_path / "rw")),
        ),
        network_mode=launch_policy.NETWORK_PROXY,
        network_endpoints=(launch_policy.NetworkLaunchEndpoint("connect", "https://api.local"),),
    )
    (tmp_path / "ro").mkdir()
    (tmp_path / "rw").mkdir()
    calls = []
    monkeypatch.setattr(windows_appcontainer, "is_windows", lambda: True)
    monkeypatch.setattr(
        windows_appcontainer.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)) or type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})(),
    )

    windows_appcontainer.apply_filesystem_acls(policy, "S-1-15-2-1")
    windows_appcontainer.configure_network(
        policy,
        "S-1-15-2-1",
        proxy_url="http://127.0.0.1:4123",
    )

    assert ["icacls", str(tmp_path / "ro"), "/grant", "*S-1-15-2-1:(OI)(CI)RX"] not in [item[0] for item in calls]
    assert ["icacls", str(tmp_path / "rw"), "/grant", "*S-1-15-2-1:(OI)(CI)M"] in [item[0] for item in calls]
    assert ["CheckNetIsolation", "LoopbackExempt", "-a", "-p=S-1-15-2-1"] in [item[0] for item in calls]
    assert any(
        item[0][:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
        and "New-NetFirewallRule" in item[0][-1]
        and "-Package 'S-1-15-2-1'" in item[0][-1]
        for item in calls
    )


def test_windows_acl_create_missing_path_uses_existing_parent(monkeypatch, tmp_path):
    parent = tmp_path / "venv-parent"
    parent.mkdir()
    missing_target = parent / "engine-env"
    policy = launch_policy.SandboxLaunchPolicy(
        command=["cmd", "/c", "echo ok"],
        cwd=None,
        env={},
        filesystem_access=(
            launch_policy.FilesystemLaunchAccess("create", str(missing_target)),
        ),
        network_mode=launch_policy.NETWORK_DENY,
    )
    calls = []
    monkeypatch.setattr(windows_appcontainer, "is_windows", lambda: True)
    monkeypatch.setattr(
        windows_appcontainer.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)) or type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})(),
    )

    windows_appcontainer.apply_filesystem_acls(policy, "S-1-15-2-1")

    assert missing_target.exists()
    assert calls[0][0][1] == str(missing_target)


def test_windows_acl_missing_non_create_fails(tmp_path):
    with pytest.raises(RuntimeError, match="windows_sandbox_acl_apply_failed:missing_path"):
        windows_appcontainer._acl_target_for_access(str(tmp_path / "missing"), "modify")


def test_windows_proxy_gets_internet_client_capability(monkeypatch):
    policy = launch_policy.SandboxLaunchPolicy(
        command=["cmd", "/c", "echo ok"],
        cwd=None,
        env={},
        filesystem_access=(),
        network_mode=launch_policy.NETWORK_PROXY,
        network_endpoints=(launch_policy.NetworkLaunchEndpoint("connect", "https://api.local"),),
    )
    monkeypatch.setattr(windows_appcontainer, "_derive_capability_sid", lambda name: ctypes.c_void_p(1))

    capabilities, capability_count = windows_appcontainer._capabilities_for_policy(policy)

    assert capabilities is not None
    assert capability_count == 1


def test_windows_cleanup_removes_firewall_and_acl(monkeypatch, tmp_path):
    target = tmp_path / "allowed"
    target.mkdir()
    prepared = windows_appcontainer.WindowsPreparedSandbox(
        appcontainer_name="democrai.test",
        package_sid="S-1-15-2-1",
        proxy_url="",
        acl_targets=(str(target),),
        firewall_rule_prefix="Democrai Sandbox abc",
    )
    calls = []
    monkeypatch.setattr(windows_appcontainer.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(
        windows_appcontainer.subprocess,
        "run",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)) or type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})(),
    )

    windows_appcontainer.cleanup_windows_appcontainer(prepared)

    assert any("Remove-NetFirewallRule" in item[0][-1] for item in calls)
    assert ["CheckNetIsolation", "LoopbackExempt", "-d", "-p=S-1-15-2-1"] in [item[0] for item in calls]
    assert ["icacls", str(target), "/remove:g", "*S-1-15-2-1"] in [item[0] for item in calls]


def test_windows_stdio_handles_are_made_inheritable(monkeypatch):
    calls = []

    class _Kernel32:
        def GetStdHandle(self, handle_id):
            return ctypes.c_void_p(abs(handle_id))

        def SetHandleInformation(self, handle, mask, flags):
            calls.append((handle.value, mask, flags))
            return True

    class _Windll:
        kernel32 = _Kernel32()

    startup = windows_appcontainer.STARTUPINFOEXW()
    monkeypatch.setattr(windows_appcontainer.ctypes, "windll", _Windll(), raising=False)

    windows_appcontainer._set_startup_stdio(startup)

    assert startup.StartupInfo.dwFlags & windows_appcontainer.STARTF_USESTDHANDLES
    assert startup.StartupInfo.hStdOutput
    assert startup.StartupInfo.hStdError
    assert calls
