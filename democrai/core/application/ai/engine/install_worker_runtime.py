"""Lifecycle helpers for engine install event consumers."""

from __future__ import annotations

from typing import Any


def start_engine_install_worker_process(ctx: Any) -> None:
    if getattr(ctx, "setup_mode", False):
        return None

    from democrai.core.application.ai.engine.install_events import (
        start_engine_install_consumer,
        start_engine_install_reconcile,
    )

    start_engine_install_consumer()
    start_engine_install_reconcile()
    logger = getattr(ctx, "logger", None)
    if logger is not None:
        logger.info("[Bootstrap] Engine install worker started in-process")
    return None
