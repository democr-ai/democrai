from __future__ import annotations

import asyncio
import os
from typing import Any

from democrai.core.application.home import resolve_guest_page_path
from democrai.core.application.session_keys import SessionKey
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload
from democrai.core.runtime.foundation.app import request_context_scope
from democrai.core.runtime.foundation.paths import get_data_dir

SETUP_FINALIZE_STREAM_ID = "system.setup.finalize.events"
SETUP_FINALIZE_REQUESTED = "setup.finalize.requested"


def build_setup_finalize_requested(
    *,
    admin_user: str,
    admin_pass: str,
    admin_email: str | None = None,
    stream_id: str | None = None,
    session_key: str | None = None,
) -> dict[str, Any]:
    resolved_admin_user = admin_user.strip() if isinstance(admin_user, str) else ""
    resolved_admin_pass = admin_pass.strip() if isinstance(admin_pass, str) else ""
    resolved_admin_email = admin_email.strip() if isinstance(admin_email, str) else ""
    resolved_stream_id = stream_id.strip() if isinstance(stream_id, str) else ""
    resolved_session_key = session_key.strip() if isinstance(session_key, str) else ""
    event = {
        "event_name": SETUP_FINALIZE_REQUESTED,
        "admin_user": resolved_admin_user if resolved_admin_user else "admin",
        "admin_pass": resolved_admin_pass if resolved_admin_pass else "password",
        "admin_email": resolved_admin_email,
    }
    if resolved_stream_id:
        event["stream_id"] = resolved_stream_id
    if resolved_session_key:
        event["session_key"] = resolved_session_key
    event["request_context"] = current_request_context_payload(
        "setup_finalize.build_requested"
    )
    return event


async def publish_setup_finalize_requested(
    *,
    admin_user: str,
    admin_pass: str,
    admin_email: str | None = None,
    stream_id: str | None = None,
    session_key: str | None = None,
) -> dict[str, Any]:
    event = build_setup_finalize_requested(
        admin_user=admin_user,
        admin_pass=admin_pass,
        admin_email=admin_email,
        stream_id=stream_id,
        session_key=session_key,
    )
    network = getattr(app_ctx(), "network", None)
    if network is None:
        raise RuntimeError("network_unavailable")
    await network.stream_manager.broadcast(SETUP_FINALIZE_STREAM_ID, event)
    return event


def finalize_setup_runtime(
    *,
    admin_user: str,
    admin_pass: str,
    admin_email: str | None = None,
) -> None:
    from democrai.core.application.auth.service import seed_admin_user_custom
    from democrai.core.infrastructure.database import _default_engine
    from democrai.core.infrastructure.database.factory import PersistenceProviderFactory
    from democrai.core.infrastructure.storage.data.factory import DataStorageProviderFactory
    from democrai.core.infrastructure.storage.kg.factory import KGStoreFactory
    from democrai.core.infrastructure.storage.media.factory import MediaProviderFactory
    from democrai.core.infrastructure.storage.migrations.orchestrator import run_storage_migrations
    from democrai.core.infrastructure.storage.observability.factory import ObservabilityFactory
    from democrai.core.infrastructure.storage.vector.factory import VectorStoreFactory

    import democrai.core.infrastructure.database
    import democrai.core.infrastructure.storage.data.database

    context = app_ctx()
    if not bool(getattr(context, "setup_mode", False)):
        raise PermissionError("APPLICATION NOT IN SETUP MODE")

    if _default_engine:
        _default_engine.dispose()
    democrai.core.infrastructure.database._default_engine = None
    democrai.core.infrastructure.database._default_SessionLocal = None
    democrai.core.infrastructure.database._db_url = None

    if democrai.core.infrastructure.storage.data.database._engine:
        democrai.core.infrastructure.storage.data.database._engine.dispose()
    democrai.core.infrastructure.storage.data.database._engine = None
    democrai.core.infrastructure.storage.data.database._SessionLocal = None

    db_type = context.config.get("database.type", "sqlite")
    db_url = context.config.get("database.url")
    if db_type == "sqlite":
        context.db = PersistenceProviderFactory.get_provider(db_type)
    else:
        context.db = PersistenceProviderFactory.get_provider(db_type, db_url=db_url)

    media_type = context.config.get("storage.media.type", "local")
    media_path = context.config.get("storage.media.path")
    media_bucket = context.config.get("storage.media.bucket")
    media_region = context.config.get("storage.media.region", "us-east-1")
    media_access_key = context.config.get("storage.media.access_key")
    media_secret_key = context.config.get("storage.media.secret_key")
    media_session_token = context.config.get("storage.media.session_token")
    media_endpoint_url = context.config.get("storage.media.endpoint_url")
    media_public_base_url = context.config.get("storage.media.public_base_url")
    media_key_prefix = context.config.get("storage.media.key_prefix")
    media_use_path_style = context.config.get("storage.media.use_path_style", False)

    _ensure_setup_storage_writable(context.config)
    context.media = MediaProviderFactory.get_provider(
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
    context.kg_store = KGStoreFactory.get_provider(
        context.config.get("storage.kg.type", "sqlite"),
        db_path=context.config.get("storage.kg.db_path"),
        uri=context.config.get("storage.kg.uri"),
        user=context.config.get("storage.kg.user"),
        password=context.config.get("storage.kg.password"),
    )
    context.vector_store = VectorStoreFactory.get_provider(
        context.config.get("storage.vector.type", "sqlite-vec"),
        host=context.config.get("storage.vector.host", "localhost"),
        port=context.config.get("storage.vector.port", 19530),
        user=context.config.get("storage.vector.user", ""),
        password=context.config.get("storage.vector.password", ""),
        api_key=context.config.get(
            "storage.vector.api_key",
            os.getenv("PINECONE_API_KEY", ""),
        ),
        cloud=context.config.get("storage.vector.cloud", "aws"),
        region=context.config.get("storage.vector.region", "us-east-1"),
        index_prefix=context.config.get("storage.vector.index_prefix", "democrai"),
    )
    context.data_store = DataStorageProviderFactory.get_provider(
        context.config.get("database.data_type") or db_type,
        db_url=context.config.get("database.data_url") or db_url,
    )
    context.obs_store = ObservabilityFactory.get_provider(
        context.config.get("storage.observability.type", "sqlite"),
        connection_url=context.config.get("storage.observability.url"),
        otlp_enabled=context.config.get(
            "storage.observability.exporters.otlp.enabled", False
        ),
        otlp_endpoint=context.config.get("storage.observability.exporters.otlp.endpoint"),
        otlp_insecure=context.config.get(
            "storage.observability.exporters.otlp.insecure", False
        ),
        otlp_service_name=context.config.get(
            "storage.observability.exporters.otlp.service_name", "democrai"
        ),
    )

    network = getattr(context, "network", None)
    if network and getattr(network, "core", None):
        network.core.reset_session_store()

    context.db.run_migrations()
    run_storage_migrations(context)
    seed_admin_user_custom(admin_user, admin_pass, admin_email)
    _sync_loaded_module_authorization(context)

    os_sandbox_enabled = False
    try:
        from democrai.core.infrastructure.sandbox.os.current_process import (
            apply_current_process_os_sandbox,
            is_os_sandbox_enabled,
        )
        os_sandbox_enabled = is_os_sandbox_enabled(context.config)
        if os_sandbox_enabled:
            from democrai.core.infrastructure.sandbox.process_guard import (
                process_guard_bypass_context,
            )

            with process_guard_bypass_context():
                apply_current_process_os_sandbox(context.config)
    except Exception as exc:
        if os_sandbox_enabled:
            raise
        import warnings

        warnings.warn(f"[Sandbox] current process OS sandbox failed: {exc}")

    context.setup_mode = False
    from democrai.core.infrastructure.observability.logger.manager import LoggerManager
    from democrai.core.runtime.foundation.paths import logs_dir

    context.logger = LoggerManager(log_dir=str(logs_dir()), config=context.config)

    from democrai.core.application.ai.engine.install_worker_runtime import (
        start_engine_install_worker_process,
    )
    from democrai.core.application.ai.engine.manifests import sync_engine_manifests_to_registry
    from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
        EngineOrchestratorProviderResolver,
    )
    from democrai.core.application.ai.engine.orchestrator.runtime import (
        start_engine_orchestrator_process,
    )
    from democrai.core.application.knowledge.extractor.manifests import (
        sync_extractor_manifests_to_registry,
    )
    from democrai.core.application.knowledge.extractor.queue_worker_runtime import (
        start_extraction_queue_worker_process,
    )
    from democrai.core.application.knowledge.query.runtime import (
        start_knowledge_query_process,
    )

    sync_engine_manifests_to_registry()
    start_engine_orchestrator_process(context)
    start_knowledge_query_process(context)
    EngineOrchestratorProviderResolver(config=context.config).provider().sync_active_engines()
    start_engine_install_worker_process(context)
    sync_extractor_manifests_to_registry()
    start_extraction_queue_worker_process(context)


def _sync_loaded_module_authorization(context) -> None:
    modules = getattr(context, "modules", None)
    get_all_modules = getattr(modules, "get_all_modules", None)
    if not callable(get_all_modules):
        return
    try:
        loaded_modules = get_all_modules()
    except Exception as exc:
        context.logger.warning(f"[Setup] Unable to list modules for RBAC sync: {exc}")
        return
    if loaded_modules is None:
        return
    loaded_modules = list(loaded_modules)
    if not loaded_modules:
        return

    from democrai.core.application.auth.service import sync_module_authorization
    from democrai.core.infrastructure.modules.loading import _load_module_rbac_manifest

    for module in loaded_modules:
        module_name = getattr(module, "name", None)
        if not isinstance(module_name, str) or not module_name:
            continue
        try:
            sync_module_authorization(
                module_name,
                _load_module_rbac_manifest(module),
            )
        except Exception as exc:
            context.logger.error(
                f"[Setup] Failed to sync module RBAC for {module_name}: {exc}"
            )


async def process_setup_finalize_event(payload: dict[str, Any]) -> None:
    event_name_value = payload.get("event_name")
    event_name = event_name_value.strip() if isinstance(event_name_value, str) else ""
    if event_name != SETUP_FINALIZE_REQUESTED:
        return
    admin_user_value = payload.get("admin_user")
    admin_pass_value = payload.get("admin_pass")
    admin_email_value = payload.get("admin_email")
    stream_id_value = payload.get("stream_id")
    session_key_value = payload.get("session_key")
    admin_user = admin_user_value.strip() if isinstance(admin_user_value, str) else ""
    admin_pass = admin_pass_value.strip() if isinstance(admin_pass_value, str) else ""
    admin_email = admin_email_value.strip() if isinstance(admin_email_value, str) else ""
    stream_id = stream_id_value.strip() if isinstance(stream_id_value, str) else ""
    session_key = session_key_value.strip() if isinstance(session_key_value, str) else ""
    request_context = payload.get("request_context")
    if request_context is None:
        request_context_payload = {}
    elif isinstance(request_context, dict):
        request_context_payload = dict(request_context)
    else:
        raise RuntimeError("setup_request_context_must_be_dict")
    with request_context_scope(request_context_payload):
        await asyncio.to_thread(
            finalize_setup_runtime,
            admin_user=admin_user if admin_user else "admin",
            admin_pass=admin_pass if admin_pass else "admin",
            admin_email=admin_email,
        )
    await _render_post_setup_transition(
        stream_id=stream_id or None,
        session_key=session_key or None,
    )
    from democrai.core.runtime.lifecycle.restart import request_application_restart

    request_application_restart(app_ctx())


async def _consume_setup_finalize_stream() -> None:
    network = getattr(app_ctx(), "network", None)
    if network is None:
        return
    queue = network.stream_manager.subscribe(SETUP_FINALIZE_STREAM_ID)
    try:
        while True:
            payload = await queue.get()
            if not isinstance(payload, dict):
                continue
            try:
                await process_setup_finalize_event(payload)
            except Exception:
                app_ctx().logger.exception("[Setup] Finalization event failed")
    except asyncio.CancelledError:
        pass
    finally:
        network.stream_manager.unsubscribe(SETUP_FINALIZE_STREAM_ID, queue)


def _log_setup_finalize_consumer_failure(future) -> None:
    try:
        exc = future.exception()
    except asyncio.CancelledError:
        return
    except Exception:
        app_ctx().logger.exception("[Setup] Unable to inspect finalization consumer")
        return
    if exc is not None:
        app_ctx().logger.exception(
            "[Setup] Finalization consumer stopped unexpectedly",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    app_ctx().setup_finalize_consumer = None


def start_setup_finalize_consumer() -> None:
    ctx = app_ctx()
    network = getattr(ctx, "network", None)
    if network is None or getattr(network, "_loop", None) is None:
        return
    if getattr(ctx, "setup_finalize_consumer", None) is not None:
        return
    future = asyncio.run_coroutine_threadsafe(
        _consume_setup_finalize_stream(),
        network._loop,
    )
    future.add_done_callback(_log_setup_finalize_consumer_failure)
    ctx.setup_finalize_consumer = future


def _ensure_setup_storage_writable(cfg) -> None:
    data_dir = get_data_dir()
    os.makedirs(data_dir, exist_ok=True)

    media_type_value = cfg.get("storage.media.type", "local")
    media_type = (
        media_type_value.strip().lower()
        if isinstance(media_type_value, str)
        else "local"
    )
    if not media_type:
        media_type = "local"
    if media_type != "local":
        return
    media_path_value = cfg.get("storage.media.path")
    media_path = media_path_value.strip() if isinstance(media_path_value, str) else ""
    if not media_path:
        media_path = os.path.join(data_dir, "assets")
    os.makedirs(media_path, exist_ok=True)


async def _render_post_setup_transition(
    *,
    stream_id: str | None,
    session_key: str | None,
) -> None:
    if not stream_id or not session_key:
        return
    network = getattr(app_ctx(), "network", None)
    if network is None or getattr(network, "core", None) is None:
        return
    core = network.core
    session = core.get_session(None, None, session_key=session_key)
    session[SessionKey.CURRENT_PATH] = resolve_guest_page_path()
    messages = await core.render(session, force_shell=True)
    core.session_service.persist(session_key)
    for message in messages:
        await network.stream_manager.broadcast(stream_id, message)
