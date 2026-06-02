from __future__ import annotations

import os

SERVER_NAME = "democr.ai"
APP_NAME = "democrai"
SDK_VERSION = "1.0.0"


def get_ipc_server_name() -> str:
    return str(
        os.getenv("DEMOCRAI_IPC_ENDPOINT")
        or os.getenv("DEMOCRAI_IPC_SERVER_NAME")
        or SERVER_NAME
    )


def build_desktop_ipc_server_name(port: int) -> str:
    return f"{SERVER_NAME}.{int(port)}"
