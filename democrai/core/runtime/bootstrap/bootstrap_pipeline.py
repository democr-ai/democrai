from __future__ import annotations

import os
import sys
import time
from typing import Any, Protocol

from filelock import FileLock, Timeout

from democrai.core.application.observability.maintenance import ObservabilityMaintenanceService
from democrai.core.application.observability.sqlalchemy_audit import (
    install_sqlalchemy_audit_hooks,
)
from democrai.core.runtime.foundation.app import AppContext, app_ctx
from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.core.infrastructure.database.factory import PersistenceProviderFactory
from democrai.core.infrastructure.network.factory import StreamProviderFactory
from democrai.core.infrastructure.network.runtime.network import Network
from democrai.core.runtime.foundation.paths import (
    configure_temp_environment,
    get_data_dir,
    logs_dir,
    state_dir,
)
from democrai.core.application.routing.router import Router
from democrai.core.infrastructure.storage.data.factory import DataStorageProviderFactory
from democrai.core.infrastructure.storage.kg.factory import KGStoreFactory
from democrai.core.infrastructure.storage.media.factory import MediaProviderFactory
from democrai.core.infrastructure.storage.observability.factory import ObservabilityFactory
from democrai.core.infrastructure.storage.migrations.orchestrator import run_storage_migrations
from democrai.core.infrastructure.storage.vector.factory import VectorStoreFactory
from democrai.core.infrastructure.storage.vector.sqlite_vec_store import SQLiteVecVectorProvider
from democrai.core.platform.utils.env import SERVER_NAME, get_ipc_server_name
from democrai.core.runtime.dependencies.ai_bootstrap import ensure_engine_env_base

from . import bootstrap_pipeline_helpers


class RuntimeArgs(Protocol):
    mode: str
    http: bool
    host: str
    port: int
    dev: int
    listen_fd: int | None
    module_paths: tuple[str, ...]
    engine_paths: tuple[str, ...]
    extractor_paths: tuple[str, ...]


class RuntimeBootstrapper:
    """Application bootstrap pipeline split by runtime responsibilities."""

    def bootstrap(self, args: RuntimeArgs) -> str | None:
        """
        Bootstrap order is FIXED. Dependencies:
        1. init_config()     — sets ctx.setup_mode, ctx.config
        2. init_storage()    — requires ctx.config; sets ctx.db, ctx.vector_store, ...
        3. init_network()    — requires ctx.config; sets ctx.network
        4. init_modules()    — requires ctx.db, ctx.network; loads modules into ctx.modules
        5. run_migrations()  — requires ctx.db, ctx.modules loaded (skipped in setup mode)
        6. network.start()   — requires ctx.network initialized
        7. start_knowledge_runtime() — requires ctx.knowledge_service, ctx.network running
        """
        ctx = app_ctx()
        network_started = False
        try:
            configure_temp_environment()
            self.init_config(ctx)
            self.configure_logging(ctx)
            self.ensure_core_os_sandbox_relaunched(ctx, args)
            ensure_engine_env_base()
            self.refresh_os_network_allowlist(ctx)
            self.init_storage(ctx)
            self.sync_engine_registry(ctx)
            self.init_network(ctx, args)
            self.init_modules(ctx, args)
            self.sync_environment_definitions(ctx)
            self.warmup_routing(ctx, args)
            self.process_deferred_external_access_resumes(ctx)
            owns_background_services = self.acquire_background_services_lock(ctx)

            if not ctx.setup_mode:
                self.run_migrations(ctx, owns_background_services=owns_background_services)
                self.sync_extractor_registry(ctx)
                self.apply_environment_variables(ctx)
            else:
                ctx.logger.info("[Bootstrap] Deferring migrations until setup is complete.")

            ctx.network.start()
            network_started = True
            self.start_external_access_cache_runtime(ctx)
            ipc_endpoint = self.ipc_endpoint(ctx)
            if owns_background_services:
                self.start_core_reloader(ctx, args)
                self.start_runtime_prompt_grpc_runtime(ctx)
                self.start_engine_orchestrator_runtime(ctx)
                self.start_knowledge_query_runtime(ctx)
                self.start_setup_finalize_runtime(ctx)
                self.start_environment_runtime(ctx)
                self.start_os_allowlist_runtime(ctx)
                self.start_engine_install_runtime(ctx)
                self.start_extractor_install_runtime(ctx)
                self.start_runtime_metrics_runtime(ctx)
                self.start_knowledge_extraction_queue_runtime(ctx)
                self.start_knowledge_runtime(ctx)
                ctx.network.core.session_service.start_cleanup_loop()
                ctx.modules.schedule_startup(getattr(ctx.network, "_loop", None))
            if args.mode == "server":
                ctx.network.init_http_ws(
                    args.host,
                    args.port,
                    fd=getattr(args, "listen_fd", None),
                    app_mode="full",
                )
            elif args.mode == "desktop":
                ctx.network.init_http_ws(
                    "127.0.0.1",
                    args.port,
                    fd=getattr(args, "listen_fd", None),
                    app_mode="full" if args.http else "media_proxy_only",
                )
        except Exception:
            if network_started:
                try:
                    ctx.network.stop()
                except Exception as stop_exc:
                    logger = getattr(ctx, "logger", None)
                    if logger is not None:
                        logger.error(
                            f"[Bootstrap] Failed to stop network after startup failure: {stop_exc}"
                        )
            raise

        return ipc_endpoint if args.mode == "desktop" else None

    def acquire_background_services_lock(self, ctx: AppContext) -> bool:
        lock_path = state_dir() / "background-services.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(lock_path), timeout=0)
        try:
            lock.acquire(timeout=0)
        except Timeout:
            ctx.logger.info(
                f"[Bootstrap] Background services already owned by another process: {lock_path}"
            )
            return False
        ctx.background_services_lock = lock
        ctx.background_services_generation = f"{os.getpid()}:{time.time()}"
        generation_path = state_dir() / "background-services.generation"
        generation_path.write_text(
            str(ctx.background_services_generation),
            encoding="utf-8",
        )
        ctx.logger.info(f"[Bootstrap] Background services lock acquired: {lock_path}")
        return True

    def start_core_reloader(self, ctx: AppContext, args: RuntimeArgs) -> None:
        if getattr(args, "dev", 0) != 1:
            return
        from democrai.core.runtime.lifecycle.reloader import create_dev_reloader

        def _restart_application() -> None:
            if os.environ.get("DEMOCRAI_CORE_PROCESS") == "1":
                from democrai.core.runtime.lifecycle.restart import (
                    request_application_restart,
                )

                request_application_restart(ctx, delay_seconds=0)
                return
            from democrai.core.runtime.lifecycle.cleanup import run_shutdown_cleanup

            run_shutdown_cleanup(ctx, reloader=None, child_proc=None)
            os.execv(sys.executable, [sys.executable] + sys.argv)  # nosec B606

        ctx.runtime_core_reloader = create_dev_reloader(
            ctx=ctx,
            module_paths=getattr(args, "module_paths", ()),
            engine_paths=getattr(args, "engine_paths", ()),
            extractor_paths=getattr(args, "extractor_paths", ()),
            restart_application=_restart_application,
        )

    def ipc_endpoint(self, ctx: AppContext) -> str | None:
        ipc = getattr(getattr(ctx, "network", None), "ipc", None)
        raw_endpoint = getattr(ipc, "endpoint", None)
        endpoint = raw_endpoint.strip() if isinstance(raw_endpoint, str) else ""
        if endpoint:
            return endpoint
        server = getattr(ipc, "server", None)
        if server is not None and hasattr(server, "fullServerName"):
            raw_endpoint = server.fullServerName()
            endpoint = raw_endpoint.strip() if isinstance(raw_endpoint, str) else ""
            if endpoint:
                return endpoint
        raw_endpoint = getattr(ipc, "server_name", None)
        endpoint = raw_endpoint.strip() if isinstance(raw_endpoint, str) else ""
        return endpoint or None

    def sync_engine_registry(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.ai.engine.manifests import sync_engine_manifests_to_registry

        sync_engine_manifests_to_registry()

    def sync_extractor_registry(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.knowledge.extractor.manifests import (
            sync_extractor_manifests_to_registry,
        )

        try:
            sync_extractor_manifests_to_registry()
        except Exception as exc:
            logger = getattr(ctx, "logger", None)
            if logger is not None:
                logger.warning(
                    f"[Bootstrap] Skipping extractor registry sync until schema is ready: {exc}"
                )

    def sync_environment_definitions(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.environment.definitions import (
            sync_environment_definitions_from_runtime,
        )

        sync_environment_definitions_from_runtime()

    def apply_environment_variables(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.environment.service import apply_environment_variables

        try:
            apply_environment_variables()
        except Exception as exc:
            logger = getattr(ctx, "logger", None)
            if logger is not None:
                logger.warning(f"[Bootstrap] Environment variable apply skipped: {exc}")

    def refresh_os_network_allowlist(self, ctx: AppContext) -> None:
        from democrai.core.infrastructure.sandbox.os.bootstrap import (
            bootstrap_current_process_os_sandbox,
        )

        bootstrap_current_process_os_sandbox(
            ctx,
            reason="bootstrap_config_initialized",
            mode="bootstrap",
        )

    def ensure_core_os_sandbox_relaunched(
        self,
        ctx: AppContext,
        args: RuntimeArgs,
    ) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.infrastructure.sandbox.os.core_relaunch import (
            ensure_core_os_sandbox_relaunched,
        )

        ensure_core_os_sandbox_relaunched(args)

    def init_config(self, ctx: AppContext) -> None:
        config_path = os.path.join(get_data_dir(), "config.yaml")
        ctx.setup_mode = not os.path.exists(config_path)
        if ctx.setup_mode:
            ctx.logger.info("[Bootstrap] Setup mode detected: config.yaml missing.")
        ctx.config = YamlConfigProvider(config_path)

    def configure_logging(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.infrastructure.observability.logger.manager import LoggerManager

        ctx.logger = LoggerManager(log_dir=str(logs_dir()), config=ctx.config)

    def init_storage(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            self.init_setup_storage(ctx)
            return

        db_type = ctx.config.get("database.type", "sqlite")
        db_url = ctx.config.get("database.url", None)

        data_type = ctx.config.get("database.data_type") or db_type
        data_url = ctx.config.get("database.data_url") or db_url

        media_type = ctx.config.get("storage.media.type", "local")
        media_path = ctx.config.get("storage.media.path", None)
        media_bucket = ctx.config.get("storage.media.bucket")
        media_region = ctx.config.get("storage.media.region", "us-east-1")
        media_access_key = ctx.config.get("storage.media.access_key")
        media_secret_key = ctx.config.get("storage.media.secret_key")
        media_session_token = ctx.config.get("storage.media.session_token")
        media_endpoint_url = ctx.config.get("storage.media.endpoint_url")
        media_public_base_url = ctx.config.get("storage.media.public_base_url")
        media_key_prefix = ctx.config.get("storage.media.key_prefix")
        media_use_path_style = ctx.config.get("storage.media.use_path_style", False)

        obs_type = ctx.config.get("storage.observability.type", "sqlite")
        obs_url = ctx.config.get("storage.observability.url", None)
        obs_otlp_enabled = ctx.config.get(
            "storage.observability.exporters.otlp.enabled", False
        )
        obs_otlp_endpoint = ctx.config.get(
            "storage.observability.exporters.otlp.endpoint", None
        )
        obs_otlp_insecure = ctx.config.get(
            "storage.observability.exporters.otlp.insecure", False
        )
        obs_otlp_service_name = ctx.config.get(
            "storage.observability.exporters.otlp.service_name", "democrai"
        )
        obs_events_days = int(
            ctx.config.get("storage.observability.retention.events_days", 30)
        )
        obs_audit_days = int(
            ctx.config.get("storage.observability.retention.audit_days", 180)
        )
        obs_ai_model_usage_days = int(
            ctx.config.get("storage.observability.retention.ai_model_usage_days", 90)
        )
        obs_export_outbox_days = int(
            ctx.config.get("storage.observability.retention.export_outbox_days", 14)
        )
        obs_trace_archive_queue_days = int(
            ctx.config.get("storage.observability.traces.retention.queue_days", 14)
        )
        obs_cleanup_interval_seconds = int(
            ctx.config.get(
                "storage.observability.retention.cleanup_interval_seconds", 86400
            )
        )
        obs_outbox_flush_interval_seconds = int(
            ctx.config.get(
                "storage.observability.exporters.outbox.flush_interval_seconds", 30
            )
        )
        obs_trace_archive_interval_seconds = int(
            ctx.config.get(
                "storage.observability.traces.worker_interval_seconds", 5
            )
        )
        obs_trace_archive_batch_size = int(
            ctx.config.get("storage.observability.traces.worker_batch_size", 25)
        )
        obs_trace_archive_lock_timeout_seconds = int(
            ctx.config.get(
                "storage.observability.traces.lock_timeout_seconds", 300
            )
        )

        kg_type = ctx.config.get("storage.kg.type", "sqlite")
        kg_db_path = ctx.config.get("storage.kg.db_path", None)
        kg_uri = ctx.config.get("storage.kg.uri", None)
        kg_user = ctx.config.get("storage.kg.user", None)
        kg_pass = ctx.config.get("storage.kg.password", None)

        vector_type = ctx.config.get("storage.vector.type", "sqlite-vec")
        vector_host = ctx.config.get("storage.vector.host", "localhost")
        vector_port = ctx.config.get("storage.vector.port", 19530)
        vector_user = ctx.config.get("storage.vector.user", "")
        vector_pass = ctx.config.get("storage.vector.password", "")
        vector_api_key = ctx.config.get(
            "storage.vector.api_key", os.getenv("PINECONE_API_KEY", "")
        )
        vector_cloud = ctx.config.get("storage.vector.cloud", "aws")
        vector_region = ctx.config.get("storage.vector.region", "us-east-1")
        vector_index_prefix = ctx.config.get("storage.vector.index_prefix", "democrai")

        ctx.logger.info(
            f"[Bootstrap] Initializing providers: db={db_type}, media={media_type}, "
            f"obs={obs_type}, kg={kg_type}, vector={vector_type}"
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
        ctx.kg_store = KGStoreFactory.get_provider(
            kg_type,
            db_path=kg_db_path,
            uri=kg_uri,
            user=kg_user,
            password=kg_pass,
        )
        ctx.vector_store = VectorStoreFactory.get_provider(
            vector_type,
            host=vector_host,
            port=vector_port,
            user=vector_user,
            password=vector_pass,
            api_key=vector_api_key,
            cloud=vector_cloud,
            region=vector_region,
            index_prefix=vector_index_prefix,
        )
        ctx.data_store = DataStorageProviderFactory.get_provider(
            data_type, db_url=data_url
        )

        if not getattr(ctx, "setup_mode", False):
            install_sqlalchemy_audit_hooks()

        if hasattr(ctx.obs_store, "flush_export_outbox") and hasattr(
            ctx.obs_store, "apply_retention"
        ):
            ctx.obs_maintenance_service = ObservabilityMaintenanceService(
                store=ctx.obs_store,
                logger=ctx.logger,
                events_days=obs_events_days,
                audit_days=obs_audit_days,
                ai_model_usage_days=obs_ai_model_usage_days,
                export_outbox_days=obs_export_outbox_days,
                trace_archive_queue_days=obs_trace_archive_queue_days,
                cleanup_interval_seconds=obs_cleanup_interval_seconds,
                outbox_flush_interval_seconds=obs_outbox_flush_interval_seconds,
                trace_archive_interval_seconds=obs_trace_archive_interval_seconds,
                trace_archive_batch_size=obs_trace_archive_batch_size,
                trace_archive_lock_timeout_seconds=obs_trace_archive_lock_timeout_seconds,
            )
            ctx.obs_maintenance_service.start()
        else:
            ctx.obs_maintenance_service = None
        self.init_knowledge(ctx)

    def init_setup_storage(self, ctx: AppContext) -> None:
        ctx.logger.info(
            "[Bootstrap] Setup mode: initializing minimal local providers."
        )

        ctx.db = None
        ctx.media = MediaProviderFactory.get_provider("local")
        ctx.obs_store = None
        ctx.kg_store = None
        ctx.vector_store = None
        ctx.data_store = None
        ctx.obs_maintenance_service = None
        ctx.knowledge_service = None
        ctx.knowledge_ingestion = None
        ctx.knowledge_runtime = None

    def init_knowledge(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        return bootstrap_pipeline_helpers.init_knowledge(ctx)

    def init_network(self, ctx: AppContext, args: RuntimeArgs) -> None:
        configured_node_id = ctx.config.get("network.node_id", SERVER_NAME)
        ctx.node_id = (
            configured_node_id
            if isinstance(configured_node_id, str) and configured_node_id
            else SERVER_NAME
        )
        buses: list[Any] = []
        ipc_bus_cls = None
        redis_bus = None
        if args.mode == "server":
            from democrai.core.infrastructure.network.providers.bus.ws import WsBusProvider

            buses.append(WsBusProvider())
        else:
            from democrai.core.infrastructure.network.providers.bus.ipc import IpcBusProvider
            from democrai.core.infrastructure.network.providers.bus.ws import WsBusProvider

            ipc_bus_cls = IpcBusProvider
            buses.append(IpcBusProvider(get_ipc_server_name()))
            if args.http:
                buses.append(WsBusProvider())

        if ctx.config.get("network.redis.enabled", False):
            from democrai.core.infrastructure.network.providers.bus.redis import RedisBusProvider

            redis_url = ctx.config.get("network.redis.url", "redis://localhost:6379")
            node_id = ctx.node_id
            redis_bus = RedisBusProvider(node_id=str(node_id), redis_url=str(redis_url))
            buses.append(redis_bus)

        stream_type = ctx.config.get("network.stream.type", "memory")

        stream_kwargs = {}
        if stream_type == "redis":
            stream_kwargs["redis_url"] = ctx.config.get(
                "network.redis.url", "redis://localhost:6379"
            )

        streams = StreamProviderFactory.get_provider(stream_type, **stream_kwargs)

        ctx.network = Network(buses, streams)
        if ipc_bus_cls is None:
            ctx.network.ipc = None
        else:
            ctx.network.ipc = next(
                (b for b in buses if isinstance(b, ipc_bus_cls)), None
            )

        if redis_bus is not None:
            local_buses = [bus for bus in buses if bus is not redis_bus]

            def _local_send(client_id: Any, message: dict[str, Any]) -> None:
                for bus in local_buses:
                    sockets = getattr(bus, "_sockets", None)
                    if isinstance(sockets, dict) and client_id in sockets:
                        bus.send(client_id, message)
                        return
                ctx.logger.warning(
                    f"[Bootstrap] Redis bus could not resolve local client {client_id!r}"
                )

            def _local_broadcast(message: dict[str, Any]) -> None:
                for bus in local_buses:
                    bus.broadcast(message)

            redis_bus.local_send = _local_send
            redis_bus.local_broadcast = _local_broadcast

    def start_engine_install_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.ai.engine.install_worker_runtime import (
            start_engine_install_worker_process,
        )

        try:
            start_engine_install_worker_process(ctx)
        except Exception as exc:
            logger = getattr(ctx, "logger", None)
            if logger is not None:
                logger.error(f"[Bootstrap] Engine install worker start failed: {exc}")
        if getattr(ctx, "network", None) is not None and getattr(ctx.network, "_loop", None) is not None:
            async def _sync_active() -> None:
                from democrai.core.application.ai.engine.orchestrator.client import (
                    EngineOrchestratorClient,
                )

                await asyncio.to_thread(EngineOrchestratorClient().sync_active_engines)

            import asyncio

            asyncio.run_coroutine_threadsafe(_sync_active(), ctx.network._loop)

    def start_engine_orchestrator_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.ai.engine.orchestrator.runtime import (
            start_engine_orchestrator_process,
        )

        start_engine_orchestrator_process(ctx)

    def start_knowledge_query_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.knowledge.query.runtime import (
            start_knowledge_query_service,
        )

        start_knowledge_query_service(ctx)

    def start_runtime_prompt_grpc_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.runtime_prompt.grpc.runtime import (
            start_runtime_prompt_grpc_server,
        )

        start_runtime_prompt_grpc_server(ctx)

    def start_setup_finalize_runtime(self, ctx: AppContext) -> None:
        if not getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.setup.finalization import start_setup_finalize_consumer

        start_setup_finalize_consumer()

    def start_os_allowlist_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.infrastructure.sandbox.os.events import (
            start_application_network_allowlist_refresh_consumer,
        )

        start_application_network_allowlist_refresh_consumer()

    def start_environment_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.environment.events import start_environment_variable_consumer

        start_environment_variable_consumer()

    def start_external_access_cache_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.services.external_access import (
            start_external_access_cache_consumer,
        )

        start_external_access_cache_consumer()

    def process_deferred_external_access_resumes(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.services.external_access import (
            process_deferred_filesystem_resume_actions_sync,
        )

        process_deferred_filesystem_resume_actions_sync()

    def start_extractor_install_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.knowledge.extractor.install_events import (
            start_extractor_install_consumer,
            start_extractor_install_reconcile,
        )
        from democrai.core.application.knowledge.extractor.runtime import get_extractor_runtime

        get_extractor_runtime()

        start_extractor_install_consumer()
        start_extractor_install_reconcile()
        if getattr(ctx, "network", None) is not None and getattr(ctx.network, "_loop", None) is not None:
            async def _sync_active() -> None:
                runtime = get_extractor_runtime()
                await runtime.sync_active_extractors()

            import asyncio

            asyncio.run_coroutine_threadsafe(_sync_active(), ctx.network._loop)

    def start_runtime_metrics_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.runtime_metrics.events import (
            start_runtime_metrics_publisher,
        )

        start_runtime_metrics_publisher()

    def start_knowledge_extraction_queue_runtime(self, ctx: AppContext) -> None:
        if getattr(ctx, "setup_mode", False):
            return
        from democrai.core.application.knowledge.extractor.queue_worker_runtime import (
            start_extraction_queue_worker_process,
        )

        try:
            start_extraction_queue_worker_process(ctx)
        except Exception as exc:
            logger = getattr(ctx, "logger", None)
            if logger is not None:
                logger.error(
                    f"[Bootstrap] Knowledge extraction worker start failed: {exc}"
                )

    def init_modules(self, ctx: AppContext, args: RuntimeArgs) -> None:
        assert ctx.config is not None, "init_config() must run before init_modules()"
        return bootstrap_pipeline_helpers.init_modules(ctx, args)

    def warmup_routing(self, ctx: AppContext, args: RuntimeArgs) -> None:
        if args.mode == "server":
            ctx.logger.info("[Bootstrap] Skipping route warmup in server mode.")
            return

        ctx.logger.info("[Bootstrap] Warming up routes...")
        failures = Router.warmup()
        if failures:
            ctx.logger.error(
                f"[Bootstrap] Route warmup detected {len(failures)} broken modules:"
            )
            for fail in failures:
                module_name = fail.get("module_name", fail.get("module", "-"))
                module_path = fail.get("module", fail.get("path", "-"))
                ctx.logger.error(
                    f"  - {module_name} :: {module_path} -> {fail['error']}"
                )
        else:
            ctx.logger.debug("[Bootstrap] Route warmup passed.")

    def run_migrations(
        self,
        ctx: AppContext,
        *,
        owns_background_services: bool = True,
    ) -> None:
        assert ctx.db is not None, "init_storage() must run before run_migrations()"
        lock_path = state_dir() / "migrations.lock"
        ready_path = state_dir() / "migrations.ready"
        generation_path = state_dir() / "background-services.generation"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if not owns_background_services:
            self.wait_for_migrations_ready(
                ctx,
                ready_path=ready_path,
                generation_path=generation_path,
            )
            return

        lock = FileLock(str(lock_path), timeout=120)
        try:
            ctx.logger.info(f"[Bootstrap] Waiting for migration lock: {lock_path}")
            with lock:
                ctx.logger.info("[Bootstrap] Migration lock acquired.")
                ctx.db.run_migrations()
                run_storage_migrations(ctx)
                generation = getattr(ctx, "background_services_generation", None)
                ready_path.write_text(
                    generation if isinstance(generation, str) else "",
                    encoding="utf-8",
                )
        except Timeout as exc:
            raise TimeoutError(f"migration_lock_timeout:{lock_path}") from exc

    def wait_for_migrations_ready(
        self,
        ctx: AppContext,
        *,
        ready_path,
        generation_path,
        timeout_seconds: float = 120.0,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        expected_generation = ""
        ctx.logger.info(f"[Bootstrap] Waiting for migration ready marker: {ready_path}")
        while time.monotonic() < deadline:
            if not expected_generation and generation_path.exists():
                expected_generation = generation_path.read_text(encoding="utf-8").strip()
            if ready_path.exists():
                ready_generation = ready_path.read_text(encoding="utf-8").strip()
                if expected_generation and ready_generation == expected_generation:
                    ctx.logger.info("[Bootstrap] Migration ready marker found.")
                    return
            time.sleep(0.05)
        raise TimeoutError(f"migration_ready_timeout:{ready_path}")

    def start_knowledge_runtime(self, ctx: AppContext) -> None:
        runtime = getattr(ctx, "knowledge_runtime", None)
        if runtime is None:
            return
        if getattr(ctx, "setup_mode", False):
            return
        try:
            runtime.start()
        except Exception as e:
            ctx.logger.error(f"[Bootstrap] Knowledge runtime start failed: {e}")
            # Non-fatal: app continues without knowledge processing
