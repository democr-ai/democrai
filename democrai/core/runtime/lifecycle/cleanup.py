from __future__ import annotations

import asyncio
import inspect
from typing import Any

from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.lifecycle.process_supervisor import process_supervisor


def run_shutdown_cleanup(ctx: Any, reloader: Any | None, child_proc: Any | None) -> None:
    """Run deterministic shutdown for reloader, child process, network and AI resources."""
    app_ctx().logger.info("Starting cleanup sequence...")

    if reloader:
        reloader.stop()

    core_reloader = getattr(ctx, "runtime_core_reloader", None)
    if core_reloader:
        core_reloader.stop()

    if child_proc:
        process_supervisor.terminate(child_proc)

    engine_orchestrator_process = getattr(ctx, "engine_orchestrator_process", None)
    if engine_orchestrator_process is not None:
        process_supervisor.terminate(engine_orchestrator_process)
        ctx.engine_orchestrator_process = None
        try:
            from democrai.core.application.ai.engine.orchestrator.config import (
                EngineOrchestratorConfig,
            )

            EngineOrchestratorConfig.load(ctx.config).cleanup_socket()
        except Exception as exc:
            app_ctx().logger.error(
                f"Error during engine orchestrator cleanup: {exc}"
            )

    try:
        from democrai.core.application.knowledge.query.runtime import (
            stop_knowledge_query_service,
        )
        from democrai.core.application.knowledge.query.config import (
            cleanup_knowledge_query_socket,
        )

        stop_knowledge_query_service(ctx)
        cleanup_knowledge_query_socket(ctx.config)
    except Exception as exc:
        app_ctx().logger.error(
            f"Error during knowledge query cleanup: {exc}"
        )

    if getattr(ctx, "os_sandbox_helper_process", None) is not None:
        process_supervisor.terminate(ctx.os_sandbox_helper_process)
        try:
            from democrai.core.infrastructure.sandbox.os.helper import (
                cleanup_os_sandbox_policy_file,
            )

            cleanup_os_sandbox_policy_file(ctx.config)
        except Exception as exc:
            app_ctx().logger.error(f"Error during OS sandbox policy cleanup: {exc}")

    try:
        ctx.network.core.session_service.shutdown()
    except Exception as exc:
        app_ctx().logger.error(f"Error during session cleanup shutdown: {exc}")

    try:
        if getattr(ctx, "obs_maintenance_service", None) is not None:
            ctx.obs_maintenance_service.shutdown()
    except Exception as exc:
        app_ctx().logger.error(f"Error during observability cleanup shutdown: {exc}")

    try:
        if getattr(ctx, "knowledge_runtime", None) is not None:
            ctx.knowledge_runtime.stop()
    except Exception as exc:
        app_ctx().logger.error(f"Error during knowledge runtime shutdown: {exc}")

    try:
        extractor_runtime = getattr(ctx, "extractor_runtime", None)
        if extractor_runtime is not None:
            extractor_runtime.shutdown()
            ctx.extractor_runtime = None
    except Exception as exc:
        app_ctx().logger.error(f"Error during extractor runtime shutdown: {exc}")

    ctx.network.stop()
    process_supervisor.terminate_all()

    background_services_lock = getattr(ctx, "background_services_lock", None)
    if background_services_lock is not None:
        try:
            background_services_lock.release()
        except Exception as exc:
            app_ctx().logger.error(
                f"Error releasing background services lock: {exc}"
            )
        ctx.background_services_lock = None

    try:
        from democrai.core.application.ai.engine.provider_manager import genai_manager
        from democrai.core.infrastructure.ai.engine.response.factory import (
            EngineResponseStreamFactory,
        )
        from democrai.core.infrastructure.modules.runtime import get_module_runtime

        genai_manager.shutdown()
        get_module_runtime().shutdown()
        engine_runtime = getattr(ctx, "engine_runtime", None)
        if engine_runtime is not None:
            engine_runtime.shutdown()
        asyncio.run(EngineResponseStreamFactory.aclose_shared_streams())
    except Exception as exc:
        app_ctx().logger.error(f"Error during AI cleanup: {exc}")

    try:
        kg_store = getattr(ctx, "kg_store", None)
        close = getattr(kg_store, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                asyncio.run(result)
    except Exception as exc:
        app_ctx().logger.error(f"Error during KG storage cleanup: {exc}")
