from __future__ import annotations

from democrai.core.infrastructure.network.http.app import build_fastapi_app


def start(network) -> None:
    from democrai.core.infrastructure.network.runtime import network as network_mod

    network._loop = network_mod.asyncio.new_event_loop()
    network._loop_thread = network_mod.threading.Thread(
        target=network._run_network_loop, name="NetworkLoop", daemon=True
    )
    network._loop_thread.start()

    network.task_manager.set_loop(network._loop)
    if not bool(getattr(network_mod.app_ctx(), "setup_mode", False)):
        network.task_manager.recover_from_db()

    cfg = network_mod.app_ctx().config
    if cfg and cfg.get("network.redis.enabled"):
        redis_url = cfg.get("network.redis.url", "redis://localhost:6379")
        from democrai.core.application.tasks.redis_task_bridge import RedisTaskBridge

        network.redis_task_bridge = RedisTaskBridge(
            redis_url, network.connection_registry
        )
        network_mod.app_ctx().redis_task_bridge = network.redis_task_bridge
        if network.redis_task_bridge:
            network_mod.asyncio.run_coroutine_threadsafe(
                network.redis_task_bridge.start(), network._loop
            )
        network_mod.app_ctx().logger.info(
            f"[Network] Redis task bridge enabled ({redis_url})"
        )

    for bus in network.buses:
        set_loop = getattr(bus, "set_loop", None)
        if callable(set_loop):
            set_loop(network._loop)
        bus.start()


def init_http_ws(
    network, host: str, port: int, fd: int | None = None, *, app_mode: str = "full"
):
    import uvicorn
    from democrai.core.infrastructure.network.runtime import network as network_mod

    app = build_fastapi_app(network.core, app_mode=app_mode)
    config = uvicorn.Config(
        app, host=host, port=port, fd=fd, log_level="info", loop="asyncio"
    )
    network._http_server = uvicorn.Server(config)

    def _run():
        network._http_server.run()

    network._http_thread = network_mod.threading.Thread(
        target=_run, name="uvicorn-thread", daemon=True
    )
    network._http_thread.start()
    if fd is not None:
        network_mod.app_ctx().logger.info(
            f"[Network] HTTP/WS server started on shared fd={fd} ({host}:{port})"
        )
    else:
        network_mod.app_ctx().logger.info(
            f"[Network] HTTP/WS server started on {host}:{port}"
        )


def stop_http_ws(network) -> None:
    if hasattr(network, "_http_server") and network._http_server:
        network._http_server.should_exit = True
        t = network._http_thread
        if t and t.is_alive():
            t.join(timeout=2)
    network._http_thread = None
    network._http_server = None


def run_network_loop(network):
    from democrai.core.infrastructure.network.runtime import network as network_mod

    network_mod.asyncio.set_event_loop(network._loop)
    network_mod.app_ctx().logger.info("[Network] Persistent event loop started.")
    network._loop.run_forever()


def stop(network) -> None:
    from democrai.core.infrastructure.network.runtime import network as network_mod
    from democrai.core.application.runtime_metrics.events import stop_runtime_metrics_publisher
    from democrai.core.application.runtime_prompt.grpc.server import (
        stop_runtime_prompt_grpc_server,
    )

    def _wait_shutdown(future, *, label: str) -> None:
        try:
            future.result(timeout=5)
        except Exception as exc:
            logger = getattr(network_mod.app_ctx(), "logger", None)
            if logger is not None:
                logger.error(f"[Network] Failed to stop {label}: {exc}")

    network.stop_http_ws()
    stop_runtime_metrics_publisher()
    if network._loop:
        _wait_shutdown(
            network_mod.asyncio.run_coroutine_threadsafe(
                stop_runtime_prompt_grpc_server(), network._loop
            ),
            label="runtime prompt gRPC server",
        )
    if network.redis_task_bridge and network._loop:
        _wait_shutdown(
            network_mod.asyncio.run_coroutine_threadsafe(
                network.redis_task_bridge.stop(), network._loop
            ),
            label="redis task bridge",
        )
    for bus in network.buses:
        bus.stop()
    if network._loop:
        network._loop.call_soon_threadsafe(network._loop.stop)
