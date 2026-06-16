from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any


APPLICATION_RESTART_EXIT_CODE = 75
_CORE_CHILD_ENV = "DEMOCRAI_CORE_PROCESS"


def _cleanup_engine_orchestrator_for_restart(ctx: Any) -> None:
    process = getattr(ctx, "engine_orchestrator_process", None)
    if process is None:
        return
    try:
        from democrai.core.runtime.lifecycle.process_supervisor import process_supervisor

        process_supervisor.terminate(process, timeout_ms=5000)
    except Exception as exc:
        logger = getattr(ctx, "logger", None)
        if logger is not None:
            logger.error(f"Error stopping engine orchestrator before restart: {exc}")
    finally:
        ctx.engine_orchestrator_process = None
        try:
            from democrai.core.application.ai.engine.orchestrator.config import (
                EngineOrchestratorConfig,
            )

            EngineOrchestratorConfig.load(
                getattr(ctx, "config", None)
            ).cleanup_socket()
        except Exception as exc:
            logger = getattr(ctx, "logger", None)
            if logger is not None:
                logger.error(
                    f"Error cleaning engine orchestrator socket before restart: {exc}"
                )


def request_application_restart(ctx: Any, *, delay_seconds: float = 1.0) -> None:
    """Restart the current runtime after the caller has returned its response."""

    def _restart() -> None:
        time.sleep(max(0.0, delay_seconds))
        try:
            network = getattr(ctx, "network", None)
            if network is not None:
                network.stop()
        finally:
            if os.environ.get(_CORE_CHILD_ENV) == "1":
                _cleanup_engine_orchestrator_for_restart(ctx)
                os._exit(APPLICATION_RESTART_EXIT_CODE)
            os.execv(sys.executable, [sys.executable] + sys.argv)  # nosec B606

    threading.Thread(
        target=_restart,
        name="application-restart-request",
        daemon=True,
    ).start()
