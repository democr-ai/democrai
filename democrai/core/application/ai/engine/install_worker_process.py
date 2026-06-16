"""Standalone process entrypoint for engine install and reconcile work."""

from __future__ import annotations

import asyncio
import signal
import threading
from types import SimpleNamespace

from democrai.core.infrastructure.database.factory import PersistenceProviderFactory
from democrai.core.infrastructure.network.config import NetworkStreamConfig
from democrai.core.infrastructure.network.factory import StreamProviderFactory
from democrai.core.infrastructure.observability.logger.manager import LoggerManager
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.runtime.bootstrap.bootstrap_pipeline import RuntimeBootstrapper
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import (
    configure_temp_environment,
    get_runtime_engine_dirs,
    get_runtime_extractor_dirs,
    get_runtime_module_dirs,
    logs_dir,
)


_STOP_EVENT = threading.Event()


def _request_stop(_signum, _frame) -> None:
    _STOP_EVENT.set()


def _bootstrap_context() -> None:
    ctx = app_ctx()
    configure_temp_environment()
    ctx.logger = LoggerManager(log_dir=str(logs_dir()))
    bootstrapper = RuntimeBootstrapper()
    bootstrapper.init_config(ctx)
    if getattr(ctx, "setup_mode", False):
        raise RuntimeError("engine_install_worker_setup_mode")
    ctx.node_id = str(ctx.config.get("network.node_id", SERVER_NAME) or SERVER_NAME)
    ctx.runtime_module_paths = get_runtime_module_dirs()
    ctx.runtime_engine_paths = get_runtime_engine_dirs()
    ctx.runtime_extractor_paths = get_runtime_extractor_dirs()
    _init_storage(ctx)
    bootstrapper.sync_engine_registry(ctx)
    _init_stream_network(ctx)


def _init_storage(ctx) -> None:
    config = ctx.config
    db_type = config.get("database.type", "sqlite")
    db_url = config.get("database.url", None)
    ctx.db = PersistenceProviderFactory.get_provider(db_type, db_url=db_url)


def _init_stream_network(ctx) -> None:
    config = ctx.config
    stream_config = NetworkStreamConfig.load(config)
    streams = StreamProviderFactory.get_provider(
        stream_config.provider_type, **stream_config.params
    )
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(
        target=_run_stream_loop,
        args=(loop,),
        name="EngineInstallWorkerStreamLoop",
        daemon=True,
    )
    loop_thread.start()
    ctx.network = SimpleNamespace(
        stream_manager=streams,
        _loop=loop,
        _loop_thread=loop_thread,
    )


def _run_stream_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def run_worker_loop() -> int:
    _bootstrap_context()
    from democrai.core.application.ai.engine.install_events import (
        start_engine_install_consumer,
        start_engine_install_reconcile,
    )

    logger = getattr(app_ctx(), "logger", None)
    if logger is not None:
        logger.info("[EngineInstallWorker] starting consumer and reconcile")
    start_engine_install_consumer()
    start_engine_install_reconcile()
    if logger is not None:
        logger.info("[EngineInstallWorker] ready")
    while not _STOP_EVENT.is_set():
        _STOP_EVENT.wait(1.0)
    network = getattr(app_ctx(), "network", None)
    if network is not None:
        if network._loop is not None:
            network._loop.call_soon_threadsafe(network._loop.stop)
        if network._loop_thread is not None and network._loop_thread.is_alive():
            network._loop_thread.join(timeout=2)
    return 0


def main() -> int:
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_stop)
    return run_worker_loop()


if __name__ == "__main__":
    raise SystemExit(main())
