from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from democrai.core.application.ai.engine.install_events import start_engine_install_consumer
from democrai.core.infrastructure.network.providers.stream.memory import MemoryStreamProvider
from democrai.core.infrastructure.network.runtime.network import Network
from democrai.core.runtime.foundation.app import app_ctx
from democrai.sdk.client import SDK


ENGINE_ROOT = APP_ROOT / "engines"
MODULE_ROOT = APP_ROOT / "modules"


def server_args() -> argparse.Namespace:
    return argparse.Namespace(
        mode="server",
        http=False,
        host="127.0.0.1",
        port=0,
        listen_fd=None,
    )


def system_session() -> dict[str, Any]:
    return {
        "user": {"id": 1, "organization_id": 1, "access_level": 10},
        "current_path": "/system/engines",
    }


def system_sdk(session: dict[str, Any]) -> SDK:
    return SDK(
        "modules/system",
        "system",
        current_path="/system/engines",
        session=session,
    )


def load_system_actions() -> None:
    import modules.system.actions  # noqa: F401


def configure_runtime_paths() -> None:
    os.environ.setdefault("DEMOCRAI_MODULES_PATH", str(MODULE_ROOT))
    os.environ.setdefault("DEMOCRAI_ENGINES_PATH", str(ENGINE_ROOT))
    from democrai.core.application.ai.engine.manifests import list_engine_manifests

    ctx = app_ctx()
    ctx.runtime_module_paths = (str(MODULE_ROOT),)
    ctx.runtime_engine_paths = (str(ENGINE_ROOT),)
    list_engine_manifests.cache_clear()


async def ensure_app_runtime() -> None:
    from democrai.core.application.ai.engine.runtime.manager import get_engine_runtime

    ctx = app_ctx()
    if getattr(ctx, "network", None) is None:
        ctx.network = Network([], MemoryStreamProvider())
    if getattr(ctx.network, "_loop", None) is None:
        ctx.network._loop = asyncio.get_running_loop()
    if getattr(ctx, "task_manager", None) is None:
        ctx.task_manager = ctx.network.task_manager
    ctx.task_manager.set_loop(asyncio.get_running_loop())
    get_engine_runtime()
    start_engine_install_consumer()
    await asyncio.sleep(0.1)
