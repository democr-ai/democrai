from __future__ import annotations

import os

_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ACCESS_DENIED = 5


def pid_exists(pid: int) -> bool:
    """Cross-platform liveness probe for an arbitrary pid.

    Never use ``os.kill(pid, 0)`` on Windows for this: ``0`` is
    ``signal.CTRL_C_EVENT`` there, so the call does not probe the pid — it
    invokes ``GenerateConsoleCtrlEvent`` and can broadcast a phantom Ctrl+C
    to every process attached to the console (observed under ConPTY
    terminals), while always reporting success even for dead pids.
    """
    resolved = int(pid)
    if resolved <= 0:
        return False
    if os.name == "nt":
        return _pid_exists_windows(resolved)
    try:
        os.kill(resolved, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_exists_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return kernel32.GetLastError() == _ERROR_ACCESS_DENIED
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)
