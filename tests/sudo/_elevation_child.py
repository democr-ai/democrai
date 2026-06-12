"""Elevated child for spike_windows_wfp_elevation.py — not run directly.

Launched via ShellExecuteEx "runas" (UAC). Confirms it is elevated, that an
elevated process can drive WFP, then reports status back to the parent over the
loopback port passed as argv[1] (argv[2] = path to winfwp.py to load by path).
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys


def main() -> int:
    port = int(sys.argv[1])
    winfwp_path = sys.argv[2]
    spec = importlib.util.spec_from_file_location("winfwp", winfwp_path)
    winfwp = importlib.util.module_from_spec(spec)
    sys.modules["winfwp"] = winfwp
    spec.loader.exec_module(winfwp)

    status: dict[str, object] = {
        "elevated": winfwp.is_process_elevated(),
        "pid": os.getpid(),
        "image": sys.executable,
        "wfp_ok": False,
        "wfp_detail": "",
    }
    try:
        engine = winfwp.WfpEngine()
        engine.open()
        identity = winfwp.WfpIdentity(kind="app_id", value=sys.executable)
        engine.apply_block_except(identity, allowed=[], loopback=True)
        engine.clear_identity(identity)
        engine.close()
        status["wfp_ok"] = True
    except Exception as exc:  # noqa: BLE001 - report any failure verbatim
        status["wfp_detail"] = f"{type(exc).__name__}: {exc}"

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(8.0)
        sock.connect(("127.0.0.1", port))
        sock.sendall(json.dumps(status).encode("utf-8") + b"\n")
        sock.close()
    except OSError:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
