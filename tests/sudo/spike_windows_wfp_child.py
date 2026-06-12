"""Spike phase 2 — validate the per-child app-id identity on real children.

Run ELEVATED (admin) from the repo root:

    python tests\\sudo\\spike_windows_wfp_child.py

Phase 0 proved WFP blocks the *current* process by its app-id. This proves the
production mechanism: a child launched from a DISTINCT interpreter path (a
hardlink/copy of python.exe — the "sandbox-host" executable) is blocked by a WFP
filter keyed on that path, while a child launched from the NORMAL interpreter is
untouched. That is exactly how the real backend will confine sandboxed children
(deny/proxy → sandbox-host exe → blocked-except-loopback) without touching the
core or any other process.

Expected:
  * sandbox-host child:   OUT=BLOCKED   LOOP=OK
  * normal interpreter:   OUT=OPEN      LOOP=OK
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WINFWP_PATH = os.path.join(
    _REPO_ROOT,
    "democrai", "core", "infrastructure", "sandbox", "os", "windows", "winfwp.py",
)
_spec = importlib.util.spec_from_file_location("winfwp", _WINFWP_PATH)
winfwp = importlib.util.module_from_spec(_spec)
sys.modules["winfwp"] = winfwp
_spec.loader.exec_module(winfwp)


_CHILD_CODE = r"""
import socket, sys
port = int(sys.argv[1])
def attempt(host, p):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(6.0)
    try:
        s.connect((host, p)); return "OK"
    except OSError as e:
        return f"ERR:{type(e).__name__}:{getattr(e,'winerror',e.errno)}"
    finally:
        s.close()
out = attempt("1.1.1.1", 443)
loop = attempt("127.0.0.1", port)
print("OUT=" + ("OPEN" if out == "OK" else "BLOCKED:" + out))
print("LOOP=" + ("OK" if loop == "OK" else "FAIL:" + loop))
"""


def _line(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))


def _make_sandbox_host_exe() -> tuple[str, bool]:
    """Hardlink (fallback copy) the interpreter to a distinct .exe path."""
    base = tempfile.mkdtemp(prefix="democrai_wfp_spike_")
    host = os.path.join(base, "democrai-sandbox-host-spike.exe")
    try:
        os.link(sys.executable, host)
        return host, True
    except OSError:
        shutil.copy2(sys.executable, host)
        return host, False


def _run_child(exe: str, port: int) -> dict[str, str]:
    proc = subprocess.run(
        [exe, "-c", _CHILD_CODE, str(port)],
        capture_output=True, text=True, timeout=40,
    )
    result: dict[str, str] = {}
    for raw in (proc.stdout or "").splitlines():
        if "=" in raw:
            key, _, value = raw.partition("=")
            result[key.strip()] = value.strip()
    if proc.returncode != 0 and not result:
        result["ERROR"] = (proc.stderr or "").strip()[:300]
    return result


def main() -> int:
    print("=== Spike phase 2: per-child app-id WFP enforcement ===")
    print(f"python: {sys.executable}")
    if not winfwp.is_process_elevated():
        print("Not elevated — re-run from an elevated shell.")
        return 2

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    loop_port = listener.getsockname()[1]
    stop = threading.Event()

    def _serve() -> None:
        listener.settimeout(1.0)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
                conn.close()
            except OSError:
                continue

    server = threading.Thread(target=_serve, daemon=True)
    server.start()

    host_exe, hardlinked = _make_sandbox_host_exe()
    print(f"sandbox-host exe: {host_exe} ({'hardlink' if hardlinked else 'copy'})")

    engine = winfwp.WfpEngine()
    rc = 0
    try:
        engine.open()
        identity = winfwp.WfpIdentity(kind="app_id", value=host_exe)
        engine.apply_block_except(identity, allowed=[], loopback=True)
        _line("apply block-except-loopback for sandbox-host app-id", True)

        host_result = _run_child(host_exe, loop_port)
        normal_result = _run_child(sys.executable, loop_port)
        print(f"  sandbox-host child: {host_result}")
        print(f"  normal child:       {normal_result}")

        host_blocked = host_result.get("OUT", "").startswith("BLOCKED")
        host_loop_ok = host_result.get("LOOP") == "OK"
        normal_open = normal_result.get("OUT") == "OPEN"

        _line("sandbox-host child OUTBOUND blocked by WFP", host_blocked, host_result.get("OUT", "?"))
        _line("sandbox-host child LOOPBACK works", host_loop_ok, host_result.get("LOOP", "?"))
        _line("normal interpreter child NOT blocked (rule is specific)", normal_open, normal_result.get("OUT", "?"))

        engine.clear_identity(identity)
        verdict = host_blocked and host_loop_ok and normal_open
        print("\n=== VERDICT ===")
        print("Per-child app-id identity " + (
            "WORKS — safe to wire low_integrity to launch deny/proxy children "
            "from a sandbox-host executable."
            if verdict else "did NOT behave as expected — see FAIL lines."))
        rc = 0 if verdict else 1
    except OSError as exc:
        _line("WFP operation", False, str(exc))
        rc = 1
    finally:
        stop.set()
        engine.close()
        listener.close()
        try:
            os.remove(host_exe)
            os.rmdir(os.path.dirname(host_exe))
        except OSError:
            pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
