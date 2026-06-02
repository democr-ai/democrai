from __future__ import annotations

import os
import signal

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def install_shutdown_signal_handlers(app: QApplication) -> None:
    """Install responsive Ctrl+C handlers for desktop Qt loop."""
    keepalive = QTimer(app)
    keepalive.setInterval(100)
    keepalive.timeout.connect(lambda: None)
    keepalive.start()

    shutdown_state = {"count": 0}

    def _request_shutdown(_signum, _frame) -> None:
        shutdown_state["count"] += 1
        if shutdown_state["count"] == 1:
            QTimer.singleShot(0, lambda: app.exit(130))
        else:
            os._exit(130)

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_shutdown)
