from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from democrai.core.application.ai.engine.orchestrator.client import (
    EngineOrchestratorClient,
)
from democrai.core.application.ai.engine.orchestrator.config import (
    cleanup_orchestrator_socket,
    orchestrator_enabled,
    orchestrator_process_env,
    orchestrator_startup_timeout_seconds,
    orchestrator_target,
)
from democrai.core.infrastructure.sandbox.os.helper import (
    OS_SANDBOX_HELPER_SOCKET_ENV,
    OS_SANDBOX_HELPER_TOKEN_ENV,
    OS_SANDBOX_POLICY_FILE_ENV,
    get_os_sandbox_helper_token,
    get_os_sandbox_helper_socket_path,
    get_os_sandbox_policy_file_path,
)
from democrai.core.runtime.foundation.paths import get_base_dir, is_frozen
from democrai.core.runtime.lifecycle.process_supervisor import process_supervisor


def _application_root() -> str:
    if is_frozen():
        return str(Path(get_base_dir()).resolve())
    return str(Path(get_base_dir()).resolve().parent)


def start_engine_orchestrator_process(ctx: Any) -> subprocess.Popen[str] | None:
    if getattr(ctx, "setup_mode", False):
        return None
    if not orchestrator_enabled(getattr(ctx, "config", None)):
        return None
    existing = getattr(ctx, "engine_orchestrator_process", None)
    if existing is not None and existing.poll() is None:
        return existing

    cleanup_orchestrator_socket(getattr(ctx, "config", None))
    env = orchestrator_process_env(parent_pid=os.getpid())
    if bool(getattr(ctx, "dev", False)):
        env["DEMOCRAI_DEV"] = "1"
    config = getattr(ctx, "config", None)
    env[OS_SANDBOX_HELPER_SOCKET_ENV] = get_os_sandbox_helper_socket_path(config)
    env[OS_SANDBOX_POLICY_FILE_ENV] = get_os_sandbox_policy_file_path(config)
    token = get_os_sandbox_helper_token(config)
    if token:
        env[OS_SANDBOX_HELPER_TOKEN_ENV] = token
    current_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = (
        _application_root()
        if not current_pythonpath
        else os.pathsep.join((_application_root(), current_pythonpath))
    )
    command = [
        sys.executable,
        "-m",
        "democrai.core.application.ai.engine.orchestrator.process",
    ]
    process = subprocess.Popen(  # nosec B603
        command,
        stdin=subprocess.DEVNULL,
        env=env,
        text=True,
    )
    process_supervisor.register(process, name="engine-orchestrator")
    ctx.engine_orchestrator_process = process

    timeout = orchestrator_startup_timeout_seconds(getattr(ctx, "config", None))
    target = orchestrator_target(getattr(ctx, "config", None))
    status = EngineOrchestratorClient(target=target).wait_ready(timeout=timeout)
    _apply_os_network_allowlist_to_process(ctx, process.pid)
    logger = getattr(ctx, "logger", None)
    if logger is not None:
        logger.info(
            f"[Bootstrap] Engine orchestrator started pid={process.pid} "
            f"status_pid={status.pid} target={target}"
        )
    return process


def _apply_os_network_allowlist_to_process(ctx: Any, pid: int | None) -> None:
    if pid is None:
        return
    try:
        from democrai.core.infrastructure.sandbox.os.helper import (
            apply_application_network_allowlist_with_helper,
        )
        from democrai.core.infrastructure.sandbox.os.state import (
            is_application_network_allowlist_active,
            is_application_network_allowlist_enabled,
            refresh_application_network_allowlist,
        )
        from democrai.core.infrastructure.sandbox.process_guard import (
            process_guard_bypass_context,
        )

        config = getattr(ctx, "config", None)
        if not is_application_network_allowlist_enabled(config):
            return
        if not is_application_network_allowlist_active():
            return
        allowlist = refresh_application_network_allowlist()
        with process_guard_bypass_context():
            apply_application_network_allowlist_with_helper(
                allowlist,
                pid=int(pid),
                config=config,
            )
    except Exception as exc:
        logger = getattr(ctx, "logger", None)
        if logger is not None:
            logger.error(
                f"[Bootstrap] Engine orchestrator OS allowlist apply failed: {exc}"
            )
