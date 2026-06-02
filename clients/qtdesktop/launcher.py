from __future__ import annotations

import os
import subprocess
import sys
from typing import Any


def _env(app_dir: str, client_root: str, ipc_endpoint: str, *, debug_enabled: bool) -> dict:
    env = os.environ.copy()
    paths = [app_dir, os.path.dirname(os.path.abspath(client_root))]
    env["PYTHONPATH"] = os.pathsep.join(paths) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONFAULTHANDLER", "1")
    env["DEMOCRAI_IPC_ENDPOINT"] = str(ipc_endpoint)
    if debug_enabled:
        env["DEMOCRAI_UI_DEVTOOLS"] = "1"
    return env


def start(*, args: Any, ipc_endpoint: str, app_dir: str, client_root: str):
    env = _env(
        app_dir,
        client_root,
        ipc_endpoint,
        debug_enabled=bool(getattr(args, "dev", 0) == 1),
    )
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "qtdesktop.main",
            "--host",
            str(getattr(args, "host", "127.0.0.1")),
            "--port",
            str(getattr(args, "port", 8000)),
        ],
        env=env,
    )
