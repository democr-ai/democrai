from __future__ import annotations

import asyncio
import os
import signal

from democrai.core.runtime.bootstrap.bootstrap_pipeline import RuntimeBootstrapper
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import configure_temp_environment


async def bootstrap_context() -> None:
    os.environ["DEMOCRAI_KNOWLEDGE_QUERY_SERVICE"] = "1"
    configure_temp_environment()
    ctx = app_ctx()
    bootstrapper = RuntimeBootstrapper()
    bootstrapper.init_config(ctx)
    if getattr(ctx, "setup_mode", False):
        raise RuntimeError("knowledge_query_setup_mode")
    bootstrapper.configure_logging(ctx)
    bootstrapper.init_storage(ctx)


async def _main() -> int:
    await bootstrap_context()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: _stop())

    parent_watchdog_task = asyncio.create_task(
        _stop_when_parent_exits(stop_event),
        name="knowledge-query-parent-watchdog",
    )
    try:
        from democrai.core.application.knowledge.query.server import (
            serve_until_stopped,
        )

        await serve_until_stopped(stop_event=stop_event)
    finally:
        parent_watchdog_task.cancel()
        try:
            await parent_watchdog_task
        except asyncio.CancelledError:
            pass
    return 0


async def _stop_when_parent_exits(stop_event: asyncio.Event) -> None:
    parent_pid = int(os.environ.get("DEMOCRAI_KNOWLEDGE_QUERY_PARENT_PID") or 0)
    if parent_pid <= 0:
        return
    while not stop_event.is_set():
        if not _pid_exists(parent_pid):
            stop_event.set()
            return
        await asyncio.sleep(1.0)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def main() -> int:
    try:
        return int(asyncio.run(_main()) or 0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
