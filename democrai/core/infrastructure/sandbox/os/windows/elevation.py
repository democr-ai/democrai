"""Per-session UAC elevation for the OS-sandbox network helper.

WFP write access requires an elevated token. Following privilege separation
(like the Linux helper's sudo/pkexec), only the helper process is elevated: it
is launched via ``ShellExecuteEx`` with the ``runas`` verb (which raises the
Windows UAC consent dialog once per session), while the rest of the app stays
unprivileged and talks to it over loopback + the existing HMAC token.

``runas`` cannot redirect stdio or pass an environment block, so the helper
command must be self-sufficient from its arguments; ``lpDirectory`` is set to the
app root so ``python -m <pkg>`` resolves without PYTHONPATH. The returned
:class:`ElevatedProcess` is a minimal Popen-like wrapper over the elevated
process handle (``SEE_MASK_NOCLOSEPROCESS``), enough for the supervisor's
poll/wait/terminate.
"""

from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes

from democrai.core.infrastructure.sandbox.os.windows.winfwp import is_process_elevated

__all__ = ["is_process_elevated", "spawn_elevated_process", "ElevatedProcess"]

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_HIDE = 0
_ERROR_CANCELLED = 1223
_WAIT_TIMEOUT = 0x00000102


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HANDLE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HANDLE),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


class ElevatedProcess:
    """Popen-like wrapper over an elevated process handle from ShellExecuteEx."""

    def __init__(self, handle: int, pid: int) -> None:
        self._handle = handle
        self.pid = int(pid)
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        if int(ctypes.windll.kernel32.WaitForSingleObject(self._handle, 0)) == 0:
            self.returncode = self._exit_code()
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is not None:
            return self.returncode
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ms = 0xFFFFFFFF if timeout is None else max(0, int(float(timeout) * 1000))
        result = int(kernel32.WaitForSingleObject(self._handle, ms))
        if result == _WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired("os-sandbox-helper", timeout)
        if result != 0:  # WAIT_FAILED / WAIT_ABANDONED — not a timeout
            raise ctypes.WinError(ctypes.get_last_error())
        self.returncode = self._exit_code()
        return self.returncode

    def terminate(self) -> None:
        if self.poll() is None:
            ctypes.windll.kernel32.TerminateProcess(self._handle, 1)

    def kill(self) -> None:
        self.terminate()

    def _exit_code(self) -> int:
        code = wintypes.DWORD(0)
        ctypes.windll.kernel32.GetExitCodeProcess(self._handle, ctypes.byref(code))
        return int(code.value)


def spawn_elevated_process(command: list[str], *, cwd: str | None = None) -> ElevatedProcess:
    """Launch ``command`` elevated via ShellExecuteEx ``runas`` (UAC prompt).

    ``command[0]`` is the executable; the rest become ``lpParameters``. Raises
    ``RuntimeError`` if the user declines the UAC prompt (ERROR_CANCELLED) or the
    launch otherwise fails — the caller fails closed.
    """
    if not command:
        raise RuntimeError("os_sandbox_helper_elevation_empty_command")
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD

    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(_SHELLEXECUTEINFOW)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = str(command[0])
    info.lpParameters = subprocess.list2cmdline([str(arg) for arg in command[1:]])
    info.lpDirectory = str(cwd) if cwd is not None else None
    info.nShow = _SW_HIDE
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == _ERROR_CANCELLED:
            raise RuntimeError("os_sandbox_helper_elevation_declined")
        raise RuntimeError(f"os_sandbox_helper_elevation_failed:{error}")
    if not info.hProcess:
        raise RuntimeError("os_sandbox_helper_elevation_no_process_handle")
    pid = int(kernel32.GetProcessId(info.hProcess))
    return ElevatedProcess(int(info.hProcess), pid)
