from __future__ import annotations

import os
from typing import Any

from ..logging import get_logger


def shutdown_window_runtime(window: Any) -> None:
    """Stop timers/queues/socket safely during window close."""
    try:
        window.reconnect_timer.stop()
    except Exception:
        get_logger().debug("ERROR RECONNECT desktop/runtime/lifecycle@shutdown")

    try:
        window._inbound_drain_timer.stop()
        window._inbound_queue.clear()
    except Exception:
        get_logger().debug("ERROR INBOUND TIMER desktop/runtime/lifecycle@shutdown")

    try:
        window._property_flush_timer.stop()
    except Exception:
        get_logger().debug("ERROR PROPERTY TIMER desktop/runtime/lifecycle@shutdown")

    try:
        window.client.abort()
    except Exception:
        get_logger().debug("ERROR CLIENT ABORT desktop/runtime/lifecycle@shutdown")
