from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes
from dataclasses import dataclass

from democrai.core.infrastructure.sandbox.os.launch_policy import SandboxLaunchPolicy
from democrai.core.infrastructure.sandbox.os.windows.winapi import (
    CREATE_UNICODE_ENVIRONMENT,
    EXTENDED_STARTUPINFO_PRESENT,
    PROCESS_INFORMATION,
    ProcThreadAttributeList,
    SID_AND_ATTRIBUTES,
    STARTUPINFOEXW,
    _acl_target_for_access,
    _environment_block,
    _set_startup_stdio,
    _string_sid_to_psid,
    _windows_command_line,
    current_integrity_label_sid,
    is_windows,
)


# Low mandatory integrity level SID. A Low-integrity process can read Medium
# objects (read-up is allowed by the default NO_WRITE_UP policy) but cannot
# WRITE them, which is the write-confinement boundary. Writable policy paths are
# explicitly relabeled Low so the sandboxed core can write them.
LOW_INTEGRITY_SID = "S-1-16-4096"

# Token access rights / DuplicateTokenEx levels / SetTokenInformation class.
TOKEN_DUPLICATE = 0x0002
TOKEN_QUERY = 0x0008
TOKEN_ASSIGN_PRIMARY = 0x0001
TOKEN_ADJUST_DEFAULT = 0x0080
TOKEN_ALL_ACCESS = 0xF01FF
SECURITY_IMPERSONATION = 2
TOKEN_PRIMARY = 1
TOKEN_INTEGRITY_LEVEL = 25
SE_GROUP_INTEGRITY = 0x00000020
ERROR_PRIVILEGE_NOT_HELD = 1314
LOGON_WITH_PROFILE = 0x00000001

_WRITABLE_OPERATIONS = {"create", "modify", "delete", "write"}


class _TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


@dataclass(frozen=True)
class WindowsPreparedSandbox:
    # Field names kept for continuity with the rest of the Windows backend.
    # ``package_sid`` holds the Low integrity SID; ``acl_targets`` are the dirs
    # relabeled Low so the sandboxed process can write them.
    appcontainer_name: str
    package_sid: str
    proxy_url: str
    acl_targets: tuple[str, ...] = ()
    firewall_rule_prefix: str = ""


def _require_windows() -> None:
    if not is_windows():
        raise RuntimeError("windows_sandbox_low_integrity_unavailable:not_windows")


def low_integrity_sid(policy: SandboxLaunchPolicy | None = None) -> str:
    return LOW_INTEGRITY_SID


def label_writable_paths_low(
    policy: SandboxLaunchPolicy,
    *,
    integrity: str = "L",
) -> tuple[str, ...]:
    """Relabel the policy's writable paths to Low integrity.

    A Low-integrity process cannot write Medium objects; labeling the writable
    targets Low lets the sandboxed core write exactly those (Medium processes
    keep write access — writing down in integrity is always allowed). Read and
    execute targets need no change (read-up works).
    """
    if not policy.filesystem_access:
        return ()
    if not is_windows():
        raise RuntimeError("windows_sandbox_acl_apply_failed:not_windows")
    applied: list[str] = []
    for item in policy.filesystem_access:
        if item.operation not in _WRITABLE_OPERATIONS:
            continue
        raw_target = str(item.target or "").strip()
        target = _acl_target_for_access(raw_target, item.operation)
        # Idempotent: icacls /setintegritylevel re-propagates the label across
        # the whole subtree, so skip targets already at Low — otherwise every
        # launch re-labels large writable dirs (the media/data trees).
        try:
            if current_integrity_label_sid(target) == LOW_INTEGRITY_SID:
                applied.append(target)
                continue
        except OSError:
            pass
        spec = f"(OI)(CI){integrity}" if os.path.isdir(target) else integrity
        completed = subprocess.run(
            ["icacls", target, "/setintegritylevel", spec],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = str(completed.stderr or "").strip()
            raise RuntimeError(f"windows_sandbox_acl_apply_failed:{target}:{stderr}")
        applied.append(target)
    return tuple(dict.fromkeys(applied))


def prepare_windows_low_integrity(
    policy: SandboxLaunchPolicy,
    *,
    proxy_url: str = "",
) -> WindowsPreparedSandbox:
    _require_windows()
    acl_targets = label_writable_paths_low(policy)
    return WindowsPreparedSandbox(
        appcontainer_name="low",
        package_sid=LOW_INTEGRITY_SID,
        proxy_url=proxy_url,
        acl_targets=acl_targets,
    )


def cleanup_windows_low_integrity(prepared: WindowsPreparedSandbox) -> None:
    # The Low labels on the writable dirs are kept across runs (re-labeling is a
    # cheap idempotent op on the small writable set, and a Low label is harmless
    # — Medium processes still write down to them). Nothing per-run to undo.
    return


def _create_low_integrity_token():
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    current = wintypes.HANDLE()
    access = TOKEN_DUPLICATE | TOKEN_QUERY | TOKEN_ASSIGN_PRIMARY | TOKEN_ADJUST_DEFAULT
    if not advapi32.OpenProcessToken(wintypes.HANDLE(-1), access, ctypes.byref(current)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        low = wintypes.HANDLE()
        if not advapi32.DuplicateTokenEx(
            current,
            TOKEN_ALL_ACCESS,
            None,
            SECURITY_IMPERSONATION,
            TOKEN_PRIMARY,
            ctypes.byref(low),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            psid = _string_sid_to_psid(LOW_INTEGRITY_SID)
            label = _TOKEN_MANDATORY_LABEL()
            label.Label.Sid = ctypes.cast(psid, wintypes.LPVOID)
            label.Label.Attributes = SE_GROUP_INTEGRITY
            if not advapi32.SetTokenInformation(
                low, TOKEN_INTEGRITY_LEVEL, ctypes.byref(label), ctypes.sizeof(label)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return low
        except BaseException:
            kernel32.CloseHandle(low)
            raise
    finally:
        kernel32.CloseHandle(current)


class WindowsLowIntegrityProcess:
    def __init__(self, *, prepared, token_handle, process_handle, thread_handle, pid: int) -> None:
        self._prepared = prepared
        self._token_handle = token_handle
        self._process_handle = process_handle
        self._thread_handle = thread_handle
        self.pid = int(pid)
        self.returncode: int | None = None
        self._closed = False

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        kernel32 = ctypes.windll.kernel32
        if int(kernel32.WaitForSingleObject(self._process_handle, 0)) == 0:
            self.returncode = self._exit_code()
            self._close()
            return self.returncode
        return None

    def wait(self, timeout: float | None = None):
        if self.returncode is not None:
            return self.returncode
        kernel32 = ctypes.windll.kernel32
        milliseconds = 0xFFFFFFFF if timeout is None else max(0, int(float(timeout) * 1000))
        if int(kernel32.WaitForSingleObject(self._process_handle, milliseconds)) != 0:
            raise TimeoutError("windows_low_integrity_process_wait_timeout")
        self.returncode = self._exit_code()
        self._close()
        return self.returncode

    def terminate(self):
        if self.poll() is not None:
            return
        ctypes.windll.kernel32.TerminateProcess(self._process_handle, 1)

    def kill(self):
        self.terminate()

    def _exit_code(self) -> int:
        exit_code = wintypes.DWORD(1)
        ctypes.windll.kernel32.GetExitCodeProcess(self._process_handle, ctypes.byref(exit_code))
        return int(exit_code.value)

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        kernel32 = ctypes.windll.kernel32
        try:
            if self._thread_handle:
                kernel32.CloseHandle(self._thread_handle)
            kernel32.CloseHandle(self._process_handle)
            if self._token_handle:
                kernel32.CloseHandle(self._token_handle)
        finally:
            cleanup_windows_low_integrity(self._prepared)


def spawn_low_integrity_process(
    policy: SandboxLaunchPolicy,
    prepared: WindowsPreparedSandbox,
    env: dict[str, str],
    *,
    stdin=None,
    stdout=None,
    stderr=None,
) -> WindowsLowIntegrityProcess:
    _require_windows()
    token = _create_low_integrity_token()
    try:
        startup = STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        cleanup_fds = _set_startup_stdio(
            startup.StartupInfo, stdin=stdin, stdout=stdout, stderr=stderr
        )
        attribute_list = None
        try:
            # Restrict handle inheritance to exactly the child's stdio handles so
            # the Low-integrity child cannot inherit any other inheritable handle
            # held by this process (the broker's listening/client sockets, other
            # children's pipes, ...). Without the list, bInheritHandles=TRUE would
            # pass every inheritable handle to the sandboxed child.
            info = startup.StartupInfo
            attribute_list = ProcThreadAttributeList(
                [info.hStdInput, info.hStdOutput, info.hStdError]
            )
            startup.lpAttributeList = attribute_list.pointer
            child_env = dict(env)
            child_env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
            process_info = PROCESS_INFORMATION()
            command_line = ctypes.create_unicode_buffer(_windows_command_line(policy.command))
            environment = ctypes.create_unicode_buffer(_environment_block(child_env))
            cwd = str(policy.cwd) if policy.cwd is not None else None
            if not _create_process_as_user(token, command_line, environment, cwd, startup, process_info):
                raise ctypes.WinError(ctypes.get_last_error())
            return WindowsLowIntegrityProcess(
                prepared=prepared,
                token_handle=token,
                process_handle=process_info.hProcess,
                thread_handle=process_info.hThread,
                pid=int(process_info.dwProcessId),
            )
        finally:
            if attribute_list is not None:
                attribute_list.close()
            for cleanup_fd in cleanup_fds:
                try:
                    os.close(cleanup_fd)
                except OSError:
                    pass
    except BaseException:
        try:
            ctypes.windll.kernel32.CloseHandle(token)
        except Exception:
            pass
        raise


def _create_process_as_user(token, command_line, environment, cwd, startup, process_info) -> bool:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    # EXTENDED_STARTUPINFO_PRESENT makes CreateProcess* read the STARTUPINFOEXW
    # attribute list (the restricted handle-inheritance list).
    flags = CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT
    created = advapi32.CreateProcessAsUserW(
        token, None, command_line, None, None, True,
        flags, environment, cwd,
        ctypes.byref(startup), ctypes.byref(process_info),
    )
    if created:
        return True
    if ctypes.get_last_error() != ERROR_PRIVILEGE_NOT_HELD:
        return False
    return bool(
        advapi32.CreateProcessWithTokenW(
            token, LOGON_WITH_PROFILE, None, command_line,
            flags, environment, cwd,
            ctypes.byref(startup), ctypes.byref(process_info),
        )
    )


def launch_low_integrity_process(
    policy: SandboxLaunchPolicy,
    prepared: WindowsPreparedSandbox,
    env: dict[str, str],
) -> int:
    return int(spawn_low_integrity_process(policy, prepared, env).wait())
