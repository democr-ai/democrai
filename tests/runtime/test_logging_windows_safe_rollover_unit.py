from __future__ import annotations

import logging
import time

from democrai.core.infrastructure.observability.logger.providers import local as local_mod


def test_windows_safe_rollover_swallows_concurrent_error(tmp_path, monkeypatch):
    path = tmp_path / "main.log"
    handler = local_mod._WindowsSafeTimedRotatingFileHandler(
        str(path), when="midnight", backupCount=3, encoding="utf-8"
    )
    try:
        # Simulate a sibling process holding/rotating the file (Windows WinError 32).
        monkeypatch.setattr(
            local_mod._BaseTimedRotatingFileHandler,
            "doRollover",
            lambda self: (_ for _ in ()).throw(PermissionError(32, "in use")),
        )
        handler.rolloverAt = 1  # mark a rollover as due

        handler.doRollover()  # must not raise

        assert handler.rolloverAt > int(time.time())  # timer advanced → no per-record retry
        assert handler.stream is not None  # reopened → logging continues
        handler.emit(
            logging.LogRecord("n", logging.INFO, __file__, 1, "after rollover", (), None)
        )
    finally:
        handler.close()


def test_default_provider_handler_is_windows_safe():
    assert local_mod.TimedRotatingFileHandler is local_mod._WindowsSafeTimedRotatingFileHandler
