from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from ctypes import wintypes


CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
SE_GROUP_ENABLED = 0x00000004
STARTF_USESTDHANDLES = 0x00000100
STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12
HANDLE_FLAG_INHERIT = 0x00000001
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Sid", wintypes.LPVOID),
        ("Attributes", wintypes.DWORD),
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


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", STARTUPINFOW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


class ProcThreadAttributeList:
    """A PROC_THREAD_ATTRIBUTE_LIST carrying a single HANDLE_LIST attribute.

    Passed via STARTUPINFOEXW with ``EXTENDED_STARTUPINFO_PRESENT`` so a child
    created with ``bInheritHandles=TRUE`` inherits ONLY the listed handles —
    instead of every inheritable handle in the parent (which would leak the
    broker's listening socket, other children's pipes, etc. into a sandboxed,
    Low-integrity child). Hold the instance alive until CreateProcess* returns,
    then ``close()`` it.
    """

    def __init__(self, handles) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.InitializeProcThreadAttributeList.argtypes = [
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
        kernel32.UpdateProcThreadAttribute.argtypes = [
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.c_size_t,
            wintypes.LPVOID,
            ctypes.c_size_t,
            wintypes.LPVOID,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
        kernel32.DeleteProcThreadAttributeList.argtypes = [wintypes.LPVOID]
        kernel32.DeleteProcThreadAttributeList.restype = None
        self._kernel32 = kernel32
        self.pointer = None

        seen: set[int] = set()
        values: list[int] = []
        for handle in handles:
            value = int(handle or 0)
            if value in (0, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF) or value in seen:
                continue
            seen.add(value)
            values.append(value)
        if not values:
            raise ValueError("proc_thread_attribute_handle_list_empty")
        self._handles = (wintypes.HANDLE * len(values))(*values)

        size = ctypes.c_size_t(0)
        # First call is expected to fail with ERROR_INSUFFICIENT_BUFFER and fill
        # in the required buffer size.
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        self._buffer = (ctypes.c_byte * size.value)()
        pointer = ctypes.cast(self._buffer, wintypes.LPVOID)
        if not kernel32.InitializeProcThreadAttributeList(
            pointer, 1, 0, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        self.pointer = pointer
        if not kernel32.UpdateProcThreadAttribute(
            pointer,
            0,
            PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            ctypes.cast(self._handles, wintypes.LPVOID),
            ctypes.sizeof(self._handles),
            None,
            None,
        ):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def close(self) -> None:
        if self.pointer is not None:
            self._kernel32.DeleteProcThreadAttributeList(self.pointer)
            self.pointer = None


def is_windows() -> bool:
    return sys.platform == "win32"


def _string_sid_to_psid(package_sid: str):
    advapi32 = ctypes.windll.advapi32
    psid = wintypes.LPVOID()
    if not advapi32.ConvertStringSidToSidW(str(package_sid), ctypes.byref(psid)):
        raise ctypes.WinError()
    return psid


_LABEL_SECURITY_INFORMATION = 0x00000010
_SE_FILE_OBJECT = 1


class _ACL_HEADER(ctypes.Structure):
    _fields_ = [
        ("AclRevision", ctypes.c_ubyte),
        ("Sbz1", ctypes.c_ubyte),
        ("AclSize", ctypes.c_ushort),
        ("AceCount", ctypes.c_ushort),
        ("Sbz2", ctypes.c_ushort),
    ]


class _MANDATORY_LABEL_ACE(ctypes.Structure):
    # ACE_HEADER (4 bytes) + DWORD mask + DWORD SidStart
    _fields_ = [
        ("AceType", ctypes.c_ubyte),
        ("AceFlags", ctypes.c_ubyte),
        ("AceSize", ctypes.c_ushort),
        ("Mask", wintypes.DWORD),
        ("SidStart", wintypes.DWORD),
    ]


def current_integrity_label_sid(path: str) -> str | None:
    """String SID of a path's mandatory integrity label, or None if unlabeled.

    Used to skip re-labeling a path that is already at the desired level — an
    ``icacls /setintegritylevel`` re-propagates the label across the whole
    subtree, so doing it every launch on a large writable dir is slow.
    """
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
    psacl = wintypes.LPVOID()
    psd = wintypes.LPVOID()
    error = advapi32.GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _LABEL_SECURITY_INFORMATION,
        None,
        None,
        None,
        ctypes.byref(psacl),
        ctypes.byref(psd),
    )
    if error or not psacl.value:
        return None
    try:
        acl = ctypes.cast(psacl, ctypes.POINTER(_ACL_HEADER))[0]
        if int(acl.AceCount) < 1:
            return None
        ace_ptr = wintypes.LPVOID()
        if not advapi32.GetAce(psacl, 0, ctypes.byref(ace_ptr)):
            return None
        sid_offset = _MANDATORY_LABEL_ACE.SidStart.offset
        sid_address = int(getattr(ace_ptr, "value", ace_ptr) or 0) + sid_offset
        return _sid_to_string(ctypes.c_void_p(sid_address))
    finally:
        if psd.value:
            kernel32.LocalFree(psd)


def _sid_to_string(sid) -> str:
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
    # ``sid`` may be a ctypes pointer instance (CreateAppContainerProfile byref)
    # or a raw integer address (an element of a POINTER(LPVOID) array, e.g. a
    # capability SID). Coerce both to a void pointer.
    address = int(getattr(sid, "value", sid) or 0)
    string_sid = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(
        ctypes.c_void_p(address), ctypes.byref(string_sid)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return str(string_sid.value)
    finally:
        kernel32.LocalFree(string_sid)


_TOKEN_QUERY = 0x0008
_TOKEN_LOGON_SID = 28


class _TOKEN_GROUPS_ONE(ctypes.Structure):
    # TOKEN_GROUPS with a single SID_AND_ATTRIBUTES — TokenLogonSid always
    # returns exactly one group.
    _fields_ = [
        ("GroupCount", wintypes.DWORD),
        ("Groups", SID_AND_ATTRIBUTES * 1),
    ]


def current_logon_sid() -> str:
    """String SID of the current session's logon SID (S-1-5-5-X-Y).

    Used as the write-restricting SID: NT-authority (accepted by both
    CreateRestrictedToken and icacls), absent from default file ACLs (so writes
    are denied unless we explicitly grant it), and never broadly present. This
    is the classic restricted-token sandbox primitive. Per-session, so callers
    re-grant it each launch.
    """
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        wintypes.HANDLE(-1), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, _TOKEN_LOGON_SID, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(max(size.value, ctypes.sizeof(_TOKEN_GROUPS_ONE)))
        if not advapi32.GetTokenInformation(
            token, _TOKEN_LOGON_SID, buffer, size.value, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        groups = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_GROUPS_ONE))[0]
        if int(groups.GroupCount) < 1:
            raise RuntimeError("windows_sandbox_logon_sid_unavailable")
        return _sid_to_string(groups.Groups[0].Sid)
    finally:
        kernel32.CloseHandle(token)


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


def _set_startup_stdio(
    startup: STARTUPINFOW,
    *,
    stdin=None,
    stdout=None,
    stderr=None,
) -> list[int]:
    """Wire child stdio; returns temp fds the caller must close after spawn.

    ``None`` keeps the previous behaviour (inherit this process's std
    handles). An int is a local fd (e.g. a pipe end duplicated in by the
    spawn broker); ``subprocess.DEVNULL``/``subprocess.STDOUT`` mirror their
    Popen semantics.
    """
    import msvcrt

    kernel32 = ctypes.windll.kernel32
    try:
        kernel32.GetStdHandle.restype = wintypes.HANDLE
    except Exception:
        pass
    cleanup_fds: list[int] = []

    def _resolve(value, std_id, *, stdout_handle=None):
        if value is None:
            return _inheritable_std_handle(kernel32, std_id)
        if value == subprocess.DEVNULL:
            fd = os.open(os.devnull, os.O_RDWR)
            cleanup_fds.append(fd)
            handle = msvcrt.get_osfhandle(fd)
        elif value == subprocess.STDOUT:
            handle = stdout_handle
        elif isinstance(value, int) and value >= 0:
            handle = msvcrt.get_osfhandle(int(value))
        else:
            raise RuntimeError(f"windows_sandbox_stdio_unsupported:{value!r}")
        if handle is None:
            raise RuntimeError("windows_sandbox_stdio_inherit_failed")
        if not kernel32.SetHandleInformation(
            wintypes.HANDLE(handle), HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT
        ):
            raise RuntimeError("windows_sandbox_stdio_inherit_failed")
        return handle

    try:
        stdin_handle = _resolve(stdin, STD_INPUT_HANDLE)
        stdout_handle = _resolve(stdout, STD_OUTPUT_HANDLE)
        stderr_handle = _resolve(stderr, STD_ERROR_HANDLE, stdout_handle=stdout_handle)
        if stdout_handle is None or stderr_handle is None:
            raise RuntimeError("windows_sandbox_stdio_inherit_failed")
    except Exception:
        for fd in cleanup_fds:
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    startup.dwFlags |= STARTF_USESTDHANDLES
    startup.hStdInput = stdin_handle or wintypes.HANDLE()
    startup.hStdOutput = stdout_handle
    startup.hStdError = stderr_handle
    return cleanup_fds


def _inheritable_std_handle(kernel32, handle_id: int):
    handle = kernel32.GetStdHandle(handle_id)
    handle_value = int(getattr(handle, "value", handle) or 0)
    if handle_value in {-1, 0}:
        return None
    if not kernel32.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT):
        raise RuntimeError("windows_sandbox_stdio_inherit_failed")
    return handle


def _clean_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", ".", str(value or "").strip())
    return cleaned.strip(".") or "sandbox"


def _environment_block(env: dict[str, str]) -> str:
    items = [f"{key}={value}" for key, value in sorted(env.items())]
    return "\0".join(items) + "\0\0"


def _windows_command_line(command: list[str]) -> str:
    return subprocess.list2cmdline([str(item) for item in command])


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
