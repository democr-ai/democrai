from __future__ import annotations

import ctypes
import hashlib
import os
import re
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass
from urllib.parse import urlparse

from democrai.core.infrastructure.sandbox.os.launch_policy import (
    NETWORK_ALLOW_ALL,
    NETWORK_DENY,
    NETWORK_PROXY,
    SandboxLaunchPolicy,
)


CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
SE_GROUP_ENABLED = 0x00000004
ERROR_ALREADY_EXISTS_HRESULT = -2147024713
STARTF_USESTDHANDLES = 0x00000100
STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12
HANDLE_FLAG_INHERIT = 0x00000001


@dataclass(frozen=True)
class WindowsPreparedSandbox:
    appcontainer_name: str
    package_sid: str
    proxy_url: str
    acl_targets: tuple[str, ...] = ()
    firewall_rule_prefix: str = ""


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Sid", wintypes.LPVOID),
        ("Attributes", wintypes.DWORD),
    ]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", wintypes.LPVOID),
        ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", STARTUPINFOW),
        ("lpAttributeList", wintypes.LPVOID),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def is_windows() -> bool:
    return sys.platform == "win32"


def prepare_windows_appcontainer(
    policy: SandboxLaunchPolicy,
    *,
    proxy_url: str = "",
) -> WindowsPreparedSandbox:
    package_name = appcontainer_name(policy)
    package_sid = ensure_appcontainer_profile(policy, package_name)
    acl_targets: tuple[str, ...] = ()
    firewall_rule_prefix = ""
    try:
        acl_targets = apply_filesystem_acls(policy, package_sid)
        firewall_rule_prefix = configure_network(policy, package_sid, proxy_url=proxy_url)
    except Exception:
        cleanup_windows_appcontainer(
            WindowsPreparedSandbox(
                appcontainer_name=package_name,
                package_sid=package_sid,
                proxy_url=proxy_url,
                acl_targets=acl_targets,
                firewall_rule_prefix=firewall_rule_prefix or _firewall_rule_prefix(package_sid),
            )
        )
        raise
    return WindowsPreparedSandbox(
        appcontainer_name=package_name,
        package_sid=package_sid,
        proxy_url=proxy_url,
        acl_targets=acl_targets,
        firewall_rule_prefix=firewall_rule_prefix,
    )


def appcontainer_name(policy: SandboxLaunchPolicy) -> str:
    subject = _clean_name(policy.subject or "subject")
    kind = _clean_name(policy.subject_kind or "sandbox")
    raw = "|".join(
        [
            kind,
            subject,
            policy.network_mode,
            policy.session_key or "",
            str(policy.user_id or ""),
            str(policy.organization_id or ""),
        ]
    )
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"democrai.{kind}.{subject}.{suffix}"[:64]


def ensure_appcontainer_profile(policy: SandboxLaunchPolicy, package_name: str) -> str:
    _require_windows_appcontainer()
    appcontainer_sid = _create_or_derive_appcontainer_sid(policy, package_name)
    return _sid_to_string(appcontainer_sid)


def shared_memory_package_sid(policy: SandboxLaunchPolicy) -> str:
    package_name = appcontainer_name(policy)
    _require_windows_appcontainer()
    return _sid_to_string(_derive_appcontainer_sid(package_name))


def apply_filesystem_acls(policy: SandboxLaunchPolicy, package_sid: str) -> tuple[str, ...]:
    if not policy.filesystem_access:
        return ()
    if not is_windows():
        raise RuntimeError("windows_sandbox_acl_apply_failed:not_windows")
    applied: list[str] = []
    for item in policy.filesystem_access:
        if item.operation in {"read", "execute"}:
            continue
        permission = "M"
        raw_target = str(item.target or "").strip()
        target = _acl_target_for_access(raw_target, item.operation)
        grant = f"*{package_sid}:(OI)(CI){permission}"
        completed = subprocess.run(
            ["icacls", target, "/grant", grant],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = str(completed.stderr or "").strip()
            raise RuntimeError(f"windows_sandbox_acl_apply_failed:{target}:{stderr}")
        applied.append(target)
    return tuple(dict.fromkeys(applied))


def _acl_target_for_access(target: str, operation: str) -> str:
    if not target:
        raise RuntimeError("windows_sandbox_acl_apply_failed:missing_path:")
    if os.path.exists(target):
        return target
    if operation != "create":
        raise RuntimeError(f"windows_sandbox_acl_apply_failed:missing_path:{target}")
    try:
        os.makedirs(target, exist_ok=True)
    except Exception as exc:
        raise RuntimeError(f"windows_sandbox_acl_apply_failed:create_target:{target}") from exc
    return target


def configure_network(
    policy: SandboxLaunchPolicy,
    package_sid: str,
    *,
    proxy_url: str,
) -> str:
    if not is_windows():
        raise RuntimeError("windows_sandbox_appcontainer_unavailable:not_windows")
    rule_prefix = _firewall_rule_prefix(package_sid)
    _remove_firewall_rules(rule_prefix)
    if policy.network_mode == NETWORK_DENY:
        _loopback_exempt(package_sid, enabled=False)
        _add_firewall_rule(
            display_name=f"{rule_prefix} deny outbound",
            package_sid=package_sid,
            action="Block",
        )
        return rule_prefix
    if policy.network_mode == NETWORK_PROXY:
        proxy_host, proxy_port = _loopback_proxy_endpoint(proxy_url)
        if not proxy_host or proxy_port <= 0:
            raise RuntimeError("os_sandbox_proxy_required")
        # CheckNetIsolation loopback exemption is SID-wide, not per port. Firewall
        # rules still block non-loopback traffic; local services must enforce auth.
        _loopback_exempt(package_sid, enabled=True)
        _add_firewall_rule(
            display_name=f"{rule_prefix} block internet",
            package_sid=package_sid,
            action="Block",
            remote_addresses=("Internet", "LocalSubnet", "Intranet", "DefaultGateway", "DNS", "DHCP", "WINS"),
        )
        return rule_prefix
    if policy.network_mode == NETWORK_ALLOW_ALL:
        _loopback_exempt(package_sid, enabled=True)
        return rule_prefix
    return rule_prefix


def cleanup_windows_appcontainer(prepared: WindowsPreparedSandbox) -> None:
    _remove_firewall_rules(str(prepared.firewall_rule_prefix or ""))
    _loopback_exempt(prepared.package_sid, enabled=False)
    for target in tuple(prepared.acl_targets or ()):
        _remove_acl(target, prepared.package_sid)
    _delete_appcontainer_profile(prepared.appcontainer_name)


def launch_appcontainer_process(
    policy: SandboxLaunchPolicy,
    prepared: WindowsPreparedSandbox,
    env: dict[str, str],
) -> int:
    _require_windows_appcontainer()
    appcontainer_sid = _derive_appcontainer_sid(prepared.appcontainer_name)
    security_capabilities = SECURITY_CAPABILITIES()
    security_capabilities.AppContainerSid = appcontainer_sid
    capabilities, capability_count = _capabilities_for_policy(policy)
    security_capabilities.Capabilities = capabilities
    security_capabilities.CapabilityCount = capability_count
    security_capabilities.Reserved = 0

    kernel32 = ctypes.windll.kernel32
    size = ctypes.c_size_t(0)
    kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attribute_list = ctypes.create_string_buffer(size.value)
    if not kernel32.InitializeProcThreadAttributeList(attribute_list, 1, 0, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel32.UpdateProcThreadAttribute(
            attribute_list,
            0,
            PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            ctypes.byref(security_capabilities),
            ctypes.sizeof(security_capabilities),
            None,
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        startup = STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(startup)
        _set_startup_stdio(startup)
        startup.lpAttributeList = ctypes.cast(attribute_list, wintypes.LPVOID)
        process_info = PROCESS_INFORMATION()
        command_line = ctypes.create_unicode_buffer(_windows_command_line(policy.command))
        environment = ctypes.create_unicode_buffer(_environment_block(env))
        cwd = str(policy.cwd) if policy.cwd is not None else None
        if not kernel32.CreateProcessW(
            None,
            command_line,
            None,
            None,
            True,
            EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
            environment,
            cwd,
            ctypes.byref(startup),
            ctypes.byref(process_info),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            kernel32.WaitForSingleObject(process_info.hProcess, 0xFFFFFFFF)
            exit_code = wintypes.DWORD(1)
            kernel32.GetExitCodeProcess(process_info.hProcess, ctypes.byref(exit_code))
            return int(exit_code.value)
        finally:
            kernel32.CloseHandle(process_info.hThread)
            kernel32.CloseHandle(process_info.hProcess)
    finally:
        kernel32.DeleteProcThreadAttributeList(attribute_list)


def _require_windows_appcontainer() -> None:
    if not is_windows() or not hasattr(ctypes, "windll"):
        raise RuntimeError("windows_sandbox_appcontainer_unavailable")
    if not hasattr(ctypes.windll, "userenv"):
        raise RuntimeError("windows_sandbox_appcontainer_unavailable")


def _create_or_derive_appcontainer_sid(policy: SandboxLaunchPolicy, package_name: str):
    userenv = ctypes.windll.userenv
    capabilities, capability_count = _capabilities_for_policy(policy)
    sid = wintypes.LPVOID()
    userenv.CreateAppContainerProfile.restype = wintypes.HRESULT
    hr = int(
        userenv.CreateAppContainerProfile(
            package_name,
            package_name,
            "Democrai OS sandbox profile",
            capabilities,
            capability_count,
            ctypes.byref(sid),
        )
    )
    if hr not in {0, ERROR_ALREADY_EXISTS_HRESULT}:
        raise RuntimeError(f"windows_sandbox_appcontainer_unavailable:create_profile:{hr}")
    if hr == ERROR_ALREADY_EXISTS_HRESULT:
        return _derive_appcontainer_sid(package_name)
    return sid


def _derive_appcontainer_sid(package_name: str):
    sid = wintypes.LPVOID()
    userenv = ctypes.windll.userenv
    userenv.DeriveAppContainerSidFromAppContainerName.restype = wintypes.HRESULT
    hr = int(userenv.DeriveAppContainerSidFromAppContainerName(package_name, ctypes.byref(sid)))
    if hr != 0:
        raise RuntimeError(f"windows_sandbox_appcontainer_unavailable:derive_sid:{hr}")
    return sid


def _capabilities_for_policy(policy: SandboxLaunchPolicy):
    if policy.network_mode not in {NETWORK_PROXY, NETWORK_ALLOW_ALL}:
        return None, 0
    sid = _derive_capability_sid("internetClient")
    if not sid:
        raise RuntimeError("windows_sandbox_appcontainer_unavailable:internet_client_capability")
    capabilities = (SID_AND_ATTRIBUTES * 1)()
    capabilities[0].Sid = sid
    capabilities[0].Attributes = SE_GROUP_ENABLED
    return capabilities, 1


def _derive_capability_sid(name: str):
    kernelbase = ctypes.windll.kernelbase
    if not hasattr(kernelbase, "DeriveCapabilitySidsFromName"):
        return None
    group_sids = ctypes.POINTER(wintypes.LPVOID)()
    group_count = wintypes.DWORD(0)
    capability_sids = ctypes.POINTER(wintypes.LPVOID)()
    capability_count = wintypes.DWORD(0)
    if not kernelbase.DeriveCapabilitySidsFromName(
        name,
        ctypes.byref(group_sids),
        ctypes.byref(group_count),
        ctypes.byref(capability_sids),
        ctypes.byref(capability_count),
    ):
        return None
    if int(capability_count.value) <= 0:
        return None
    return capability_sids[0]


def _sid_to_string(sid) -> str:
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
    string_sid = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(string_sid)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return str(string_sid.value)
    finally:
        kernel32.LocalFree(string_sid)


def _loopback_exempt(package_sid: str, *, enabled: bool) -> None:
    action = "-a" if enabled else "-d"
    try:
        completed = subprocess.run(
            ["CheckNetIsolation", "LoopbackExempt", action, f"-p={package_sid}"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        if not enabled:
            return
        raise RuntimeError(f"windows_sandbox_firewall_admin_required:{exc}") from exc
    if completed.returncode != 0 and enabled:
        stderr = str(completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"windows_sandbox_firewall_admin_required:{stderr}")


def _set_startup_stdio(startup: STARTUPINFOEXW) -> None:
    kernel32 = ctypes.windll.kernel32
    try:
        kernel32.GetStdHandle.restype = wintypes.HANDLE
    except Exception:
        pass
    stdin_handle = _inheritable_std_handle(kernel32, STD_INPUT_HANDLE)
    stdout_handle = _inheritable_std_handle(kernel32, STD_OUTPUT_HANDLE)
    stderr_handle = _inheritable_std_handle(kernel32, STD_ERROR_HANDLE)
    if stdout_handle is None or stderr_handle is None:
        raise RuntimeError("windows_sandbox_stdio_inherit_failed")
    startup.StartupInfo.dwFlags |= STARTF_USESTDHANDLES
    startup.StartupInfo.hStdInput = stdin_handle or wintypes.HANDLE()
    startup.StartupInfo.hStdOutput = stdout_handle
    startup.StartupInfo.hStdError = stderr_handle


def _inheritable_std_handle(kernel32, handle_id: int):
    handle = kernel32.GetStdHandle(handle_id)
    handle_value = int(getattr(handle, "value", handle) or 0)
    if handle_value in {-1, 0}:
        return None
    if not kernel32.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT):
        raise RuntimeError("windows_sandbox_stdio_inherit_failed")
    return handle


def _firewall_rule_prefix(package_sid: str) -> str:
    digest = hashlib.sha256(str(package_sid or "").encode("utf-8")).hexdigest()[:16]
    return f"Democrai Sandbox {digest}"


def _add_firewall_rule(
    *,
    display_name: str,
    package_sid: str,
    action: str,
    remote_addresses: tuple[str, ...] = (),
) -> None:
    remote_clause = ""
    if remote_addresses:
        quoted = ",".join(f"'{item}'" for item in remote_addresses)
        remote_clause = f" -RemoteAddress @({quoted})"
    script = (
        "New-NetFirewallRule"
        f" -DisplayName '{_powershell_literal(display_name)}'"
        " -Direction Outbound"
        f" -Action {action}"
        f" -Package '{_powershell_literal(package_sid)}'"
        f"{remote_clause}"
        " | Out-Null"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = str(completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"windows_sandbox_firewall_admin_required:{stderr}")


def _remove_firewall_rules(rule_prefix: str) -> None:
    prefix = str(rule_prefix or "").strip()
    if not prefix:
        return
    script = (
        f"Get-NetFirewallRule -DisplayName '{_powershell_literal(prefix)}*'"
        " -ErrorAction SilentlyContinue | Remove-NetFirewallRule"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
    )


def _remove_acl(target: str, package_sid: str) -> None:
    if not target or not package_sid or not os.path.exists(target):
        return
    subprocess.run(
        ["icacls", target, "/remove:g", f"*{package_sid}"],
        check=False,
        capture_output=True,
        text=True,
    )


def _delete_appcontainer_profile(package_name: str) -> None:
    if not package_name or not is_windows() or not hasattr(ctypes, "windll"):
        return
    userenv = getattr(ctypes.windll, "userenv", None)
    if userenv is None or not hasattr(userenv, "DeleteAppContainerProfile"):
        return
    try:
        userenv.DeleteAppContainerProfile(str(package_name))
    except Exception:
        return


def _powershell_literal(value: str) -> str:
    return str(value or "").replace("'", "''")


def _loopback_proxy_endpoint(proxy_url: str) -> tuple[str, int]:
    parsed = urlparse(str(proxy_url or "").strip())
    host = str(parsed.hostname or "").strip().lower()
    port = int(parsed.port or 0)
    if host == "localhost":
        host = "127.0.0.1"
    if host not in {"127.0.0.1", "::1"} or port <= 0:
        return "", 0
    return host, port


def _clean_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", ".", str(value or "").strip())
    return cleaned.strip(".") or "sandbox"


def _environment_block(env: dict[str, str]) -> str:
    items = [f"{key}={value}" for key, value in sorted(env.items())]
    return "\0".join(items) + "\0\0"


def _windows_command_line(command: list[str]) -> str:
    return subprocess.list2cmdline([str(item) for item in command])
