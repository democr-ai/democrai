"""Spike 0 — validate WFP egress plumbing + identity mechanism on Windows 11.

Run this ELEVATED (admin) from a Windows shell:

    python tests\\sudo\\spike_windows_wfp.py

It does NOT need pytest, a sandbox, or the rest of the app — only ``winfwp``.
Goal: prove the WFP ctypes layer actually programs the TCP/IP stack, and decide
the identity mechanism for the real implementation:

  * Candidate B (ALE_APP_ID): block this very process's egress (it is python.exe)
    except loopback, then from inside verify a direct outbound connect is blocked
    while loopback still works. Self-contained, no child needed. If this passes,
    B is validated as the robust identity and we can skip token surgery.

Report the printed PASS/FAIL lines back. Any non-zero ``0x8032xxxx`` code is a
WFP API/struct error to iterate on; a clean run tells us B works end to end.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading

# Load winfwp directly by path so the spike runs under ANY elevated Python with
# ctypes — no venv/PYTHONPATH juggling and no pull-in of the heavy sandbox
# package import chain (which needs a newer interpreter for StrEnum, etc.).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WINFWP_PATH = os.path.join(
    _REPO_ROOT,
    "democrai", "core", "infrastructure", "sandbox", "os", "windows", "winfwp.py",
)
_spec = importlib.util.spec_from_file_location("winfwp", _WINFWP_PATH)
winfwp = importlib.util.module_from_spec(_spec)
sys.modules["winfwp"] = winfwp
_spec.loader.exec_module(winfwp)


def _line(label: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"[{status}] {label}{suffix}")


def _direct_outbound_blocked(host: str = "1.1.1.1", port: int = 443) -> tuple[bool, str]:
    """True if a direct outbound connect is refused/blocked at the OS level."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(6.0)
    try:
        sock.connect((host, port))
        return False, "connect succeeded (NOT blocked)"
    except OSError as exc:
        return True, f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()


def _loopback_still_works() -> tuple[bool, str]:
    """True if a loopback connect to a local listener succeeds under the filters."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    accepted: list[socket.socket] = []

    def _accept() -> None:
        try:
            conn, _ = listener.accept()
            accepted.append(conn)
        except OSError:
            pass

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(6.0)
    try:
        client.connect(("127.0.0.1", port))
        thread.join(timeout=3.0)
        return True, f"connected to 127.0.0.1:{port}"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        for conn in accepted:
            conn.close()
        listener.close()


def main() -> int:
    print("=== Spike 0: Windows WFP egress enforcement ===")
    print(f"python: {sys.executable}")

    elevated = winfwp.is_process_elevated()
    _line("process is elevated (admin)", elevated)
    if not elevated:
        print("\nNot elevated — re-run from an elevated shell. WFP write needs admin.")
        return 2

    # Sanity baseline: before any filters, is direct outbound even reachable?
    base_blocked, base_detail = _direct_outbound_blocked()
    print(f"[INFO] baseline outbound (no filters): "
          f"{'blocked' if base_blocked else 'open'} — {base_detail}")

    identity = winfwp.WfpIdentity(kind="app_id", value=sys.executable)
    engine = winfwp.WfpEngine()
    try:
        engine.open()
        _line("FwpmEngineOpen0 + sublayer", True)
    except OSError as exc:
        _line("FwpmEngineOpen0 + sublayer", False, str(exc))
        return 1

    try:
        try:
            engine.apply_block_except(identity, allowed=[], loopback=True)
            _line("apply_block_except (block-all-except-loopback, app_id)", True)
        except OSError as exc:
            _line("apply_block_except", False, str(exc))
            return 1

        blocked, detail = _direct_outbound_blocked()
        _line("direct outbound 1.1.1.1:443 is BLOCKED by WFP", blocked, detail)

        loop_ok, loop_detail = _loopback_still_works()
        _line("loopback connect still WORKS under filters", loop_ok, loop_detail)

        engine.clear_identity(identity)
        _line("clear_identity removed filters", True)

        after_blocked, after_detail = _direct_outbound_blocked()
        _line(
            "outbound reachable again after clear",
            (not after_blocked) or base_blocked,
            after_detail,
        )

        verdict = blocked and loop_ok
        print("\n=== VERDICT ===")
        print("Candidate B (ALE_APP_ID) "
              + ("WORKS — proceed with per-child executable identity."
                 if verdict else "did NOT enforce as expected — see FAIL lines above."))
        return 0 if verdict else 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
