from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from democrai.core.application.ai.engine.orchestrator.config import (
    EngineOrchestratorConfig,
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
    orchestrator_config = EngineOrchestratorConfig.load(getattr(ctx, "config", None))
    if not orchestrator_config.enabled:
        return None
    existing = getattr(ctx, "engine_orchestrator_process", None)
    if existing is not None and existing.poll() is None:
        return existing

    orchestrator_config.cleanup_socket()
    env = EngineOrchestratorConfig.process_env(parent_pid=os.getpid())
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
    from democrai.core.infrastructure.sandbox.os.core_relaunch import (
        sandbox_safe_devnull_stdin,
    )

    process = subprocess.Popen(  # nosec B603
        command,
        stdin=sandbox_safe_devnull_stdin(),
        env=env,
        text=True,
    )
    process_supervisor.register(process, name="engine-orchestrator")
    ctx.engine_orchestrator_process = process

    timeout = orchestrator_config.startup_timeout_seconds
    from democrai.core.infrastructure.ai.engine.invocation.orchestrator import (
        EngineOrchestratorProviderResolver,
    )

    provider = EngineOrchestratorProviderResolver(
        config=getattr(ctx, "config", None)
    ).provider()
    try:
        status = provider.wait_ready(timeout=timeout)
    except Exception as exc:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"engine_orchestrator_process_exited:code={exit_code}"
            ) from exc
        raise
    exit_code = process.poll()
    if exit_code is not None:
        raise RuntimeError(f"engine_orchestrator_process_exited:code={exit_code}")
    _apply_os_network_allowlist_to_process(ctx, process.pid)
    logger = getattr(ctx, "logger", None)
    if logger is not None:
        logger.info(
            f"[Bootstrap] Engine orchestrator started pid={process.pid} "
            f"status_pid={status.pid}"
        )
    return process


def _apply_os_network_allowlist_to_process(ctx: Any, pid: int | None) -> None:
    if pid is None:
        return
    try:
        from democrai.core.infrastructure.sandbox.os.helper import (
            apply_application_network_allowlist_with_helper,
        )
        from democrai.core.infrastructure.sandbox.os.factory import get_helper_backend
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
        if not getattr(get_helper_backend(), "supports_pid_enforcement", False):
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
