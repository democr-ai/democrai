"""Spike phase 3 — validate per-session UAC elevation of the helper.

Run from a NORMAL (un-elevated) shell so the UAC dialog actually appears:

    python tests\\sudo\\spike_windows_wfp_elevation.py

It mirrors the real design: an unprivileged process spawns the helper ELEVATED
via ShellExecuteEx verb "runas" (the UAC dialog), and the elevated child talks
back over loopback (the same channel the real helper uses) and proves it can
drive WFP. This de-risks the elevation piece before wiring it into the helper
start path.

Expected: a UAC prompt → accept → all PASS (child elevated + WFP works + loopback
handshake). Decline the prompt → ShellExecuteEx returns ERROR_CANCELLED (1223),
which is the real fail-closed signal.
"""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import socket
import sys
from ctypes import wintypes

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WINFWP_PATH = os.path.join(
    _REPO_ROOT,
    "democrai", "core", "infrastructure", "sandbox", "os", "windows", "winfwp.py",
)
_CHILD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_elevation_child.py")

_spec = importlib.util.spec_from_file_location("winfwp", _WINFWP_PATH)
winfwp = importlib.util.module_from_spec(_spec)
sys.modules["winfwp"] = winfwp
_spec.loader.exec_module(winfwp)


SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_HIDE = 0
ERROR_CANCELLED = 1223
WAIT_TIMEOUT = 0x00000102


class SHELLEXECUTEINFOW(ctypes.Structure):
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


def _line(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))


def _shell_execute_runas(file: str, params: str, directory: str) -> wintypes.HANDLE:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = file
    sei.lpParameters = params
    sei.lpDirectory = directory
    sei.nShow = SW_HIDE
    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        raise ctypes.WinError(ctypes.get_last_error())
    return sei.hProcess


def main() -> int:
    print("=== Spike phase 3: UAC elevation of the helper ===")
    print(f"python: {sys.executable}")
    if winfwp.is_process_elevated():
        print("NOTE: this shell is ALREADY elevated — runas will not show a UAC "
              "prompt. Run from a normal shell to exercise the dialog.")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    listener.settimeout(60.0)

    params = f'"{_CHILD_PATH}" {port} "{_WINFWP_PATH}"'
    print("Launching elevated helper child (accept the UAC prompt)...")
    try:
        process = _shell_execute_runas(sys.executable, params, _REPO_ROOT)
        _line("ShellExecuteEx runas launched (UAC accepted)", True)
    except OSError as exc:
        cancelled = getattr(exc, "winerror", None) == ERROR_CANCELLED
        _line("ShellExecuteEx runas launched", False,
              "UAC declined (ERROR_CANCELLED) = fail-closed" if cancelled else str(exc))
        listener.close()
        return 2

    status: dict[str, object] = {}
    try:
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(10.0)
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
        status = json.loads(data.decode("utf-8").strip() or "{}")
    except (OSError, ValueError) as exc:
        _line("elevated child handshake on loopback", False, str(exc))
        listener.close()
        return 1
    finally:
        listener.close()

    print(f"  child status: {status}")
    elevated = bool(status.get("elevated"))
    wfp_ok = bool(status.get("wfp_ok"))
    _line("elevated child handshake on loopback", True)
    _line("child process IS elevated", elevated)
    _line("elevated child can drive WFP", wfp_ok, str(status.get("wfp_detail") or ""))

    kernel32 = ctypes.windll.kernel32
    if process:
        kernel32.WaitForSingleObject(process, 15000)
        kernel32.CloseHandle(process)

    verdict = elevated and wfp_ok
    print("\n=== VERDICT ===")
    print("UAC per-session elevation " + (
        "WORKS — safe to start the helper elevated via ShellExecuteEx runas."
        if verdict else "did NOT behave as expected — see FAIL lines."))
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
