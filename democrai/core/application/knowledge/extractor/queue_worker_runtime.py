"""Lifecycle helpers for the standalone extraction queue worker process."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from democrai.core.runtime.foundation.paths import get_base_dir, is_frozen
from democrai.core.runtime.lifecycle.process_supervisor import process_supervisor


def _application_root() -> str:
    if is_frozen():
        return str(Path(get_base_dir()).resolve())
    return str(Path(get_base_dir()).resolve().parent)


def start_extraction_queue_worker_process(ctx: Any) -> subprocess.Popen[str] | None:
    if getattr(ctx, "setup_mode", False):
        return None
    if getattr(ctx, "knowledge_extraction_worker_process", None) is not None:
        process = ctx.knowledge_extraction_worker_process
        if process.poll() is None:
            return process

    env = dict(os.environ)
    current_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = (
        _application_root()
        if not current_pythonpath
        else os.pathsep.join((_application_root(), current_pythonpath))
    )
    command = [
        sys.executable,
        "-m",
        "democrai.core.application.knowledge.extractor.queue_worker_process",
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
    process_supervisor.register(process, name="knowledge-extraction-worker")
    ctx.knowledge_extraction_worker_process = process
    logger = getattr(ctx, "logger", None)
    if logger is not None:
        logger.info(
            f"[Bootstrap] Knowledge extraction worker started pid={process.pid}"
        )
    return process
