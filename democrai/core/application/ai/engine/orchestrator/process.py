from __future__ import annotations

import asyncio
import os
import signal
from typing import Any

from democrai.core.infrastructure.database.factory import PersistenceProviderFactory
from democrai.core.infrastructure.observability.logger.manager import LoggerManager
from democrai.core.infrastructure.storage.observability.factory import ObservabilityFactory
from democrai.core.infrastructure.storage.media.factory import MediaProviderFactory
from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import (
    configure_temp_environment,
    get_data_dir,
    get_runtime_engine_dirs,
    get_runtime_extractor_dirs,
    get_runtime_module_dirs,
    logs_dir,
)


def _init_config(ctx: Any) -> None:
    config_path = os.path.join(get_data_dir(), "config.yaml")
    ctx.setup_mode = not os.path.exists(config_path)
    if ctx.setup_mode:
        raise RuntimeError("engine_orchestrator_setup_mode")
    ctx.config = YamlConfigProvider(config_path)
    ctx.node_id = str(ctx.config.get("network.node_id", SERVER_NAME) or SERVER_NAME)


def _init_storage(ctx: Any) -> None:
    config = ctx.config
    db_type = config.get("database.type", "sqlite")
    db_url = config.get("database.url", None)
    media_type = config.get("storage.media.type", "local")
    media_path = config.get("storage.media.path", None)
    media_bucket = config.get("storage.media.bucket")
    media_region = config.get("storage.media.region", "us-east-1")
    media_access_key = config.get("storage.media.access_key")
    media_secret_key = config.get("storage.media.secret_key")
    media_session_token = config.get("storage.media.session_token")
    media_endpoint_url = config.get("storage.media.endpoint_url")
    media_public_base_url = config.get("storage.media.public_base_url")
    media_key_prefix = config.get("storage.media.key_prefix")
    media_use_path_style = config.get("storage.media.use_path_style", False)
    obs_type = config.get("storage.observability.type", "sqlite")
    obs_url = config.get("storage.observability.url", None)
    obs_otlp_enabled = config.get(
        "storage.observability.exporters.otlp.enabled", False
    )
    obs_otlp_endpoint = config.get(
        "storage.observability.exporters.otlp.endpoint", None
    )
    obs_otlp_insecure = config.get(
        "storage.observability.exporters.otlp.insecure", False
    )
    obs_otlp_service_name = config.get(
        "storage.observability.exporters.otlp.service_name", "democrai"
    )

    ctx.db = PersistenceProviderFactory.get_provider(db_type, db_url=db_url)
    ctx.media = MediaProviderFactory.get_provider(
        media_type,
        base_dir=media_path,
        bucket_name=media_bucket,
        region=media_region,
        access_key=media_access_key,
        secret_key=media_secret_key,
        session_token=media_session_token,
        endpoint_url=media_endpoint_url,
        public_base_url=media_public_base_url,
        key_prefix=media_key_prefix,
        use_path_style=media_use_path_style,
    )
    ctx.obs_store = ObservabilityFactory.get_provider(
        obs_type,
        connection_url=obs_url,
        otlp_enabled=obs_otlp_enabled,
        otlp_endpoint=obs_otlp_endpoint,
        otlp_insecure=obs_otlp_insecure,
        otlp_service_name=obs_otlp_service_name,
    )


async def bootstrap_context() -> None:
    os.environ["DEMOCRAI_ENGINE_ORCHESTRATOR"] = "1"
    configure_temp_environment()
    ctx = app_ctx()
    ctx.dev = str(os.environ.get("DEMOCRAI_DEV") or "").strip() == "1"
    _init_config(ctx)
    ctx.logger = LoggerManager(log_dir=str(logs_dir()), config=ctx.config)
    ctx.runtime_module_paths = get_runtime_module_dirs()
    ctx.runtime_engine_paths = get_runtime_engine_dirs()
    ctx.runtime_extractor_paths = get_runtime_extractor_dirs()
    _init_storage(ctx)
    from democrai.core.infrastructure.sandbox.os.bootstrap import (
        bootstrap_current_process_os_sandbox_async,
    )
    from democrai.core.runtime.bootstrap import bootstrap_pipeline_helpers
    from democrai.core.application.ai.engine.manifests import sync_engine_manifests_to_registry
    from democrai.core.application.ai.engine.runtime import get_engine_runtime

    await bootstrap_current_process_os_sandbox_async(
        ctx,
        reason="engine_orchestrator_bootstrap",
        mode="engine_orchestrator",
    )
    bootstrap_pipeline_helpers.init_modules(ctx, ctx, load_ui=False)
    sync_engine_manifests_to_registry()
    get_engine_runtime()


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

    from democrai.core.application.ai.engine.orchestrator.server import (
        serve_until_stopped,
    )
    from democrai.core.application.ai.engine.orchestrator.registry_reconcile import (
        reconcile_registries_until_stopped,
    )

    reconcile_task = asyncio.create_task(
        reconcile_registries_until_stopped(stop_event),
        name="engine-orchestrator-registry-reconcile",
    )
    parent_watchdog_task = asyncio.create_task(
        _stop_when_parent_exits(stop_event),
        name="engine-orchestrator-parent-watchdog",
    )
    try:
        await serve_until_stopped(stop_event=stop_event)
    finally:
        reconcile_task.cancel()
        parent_watchdog_task.cancel()
        try:
            await reconcile_task
        except asyncio.CancelledError:
            pass
        try:
            await parent_watchdog_task
        except asyncio.CancelledError:
            pass
    return 0


async def _stop_when_parent_exits(stop_event: asyncio.Event) -> None:
    parent_pid = int(os.environ.get("DEMOCRAI_ENGINE_ORCHESTRATOR_PARENT_PID") or 0)
    if parent_pid <= 0:
        return
    while not stop_event.is_set():
        if not _pid_exists(parent_pid):
            stop_event.set()
            return
        await asyncio.sleep(1.0)


def _pid_exists(pid: int) -> bool:
    from democrai.core.platform.utils.process import pid_exists

    try:
        return pid_exists(int(pid))
    except Exception:
        return False


def main() -> int:
    try:
        return int(asyncio.run(_main()) or 0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
