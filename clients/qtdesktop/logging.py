from __future__ import annotations

import logging
import os
import sys
from typing import Any


def is_debug_enabled() -> bool:
    return os.getenv("DEMOCRAI_DESKTOP_DEBUG", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class DesktopLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger("democrai.qtdesktop")
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s qtdesktop - %(message)s"
                )
            )
            self._logger.addHandler(handler)
            self._logger.propagate = False
        self._logger.setLevel(logging.DEBUG if is_debug_enabled() else logging.INFO)

    def debug(self, message: Any, *_args: Any, **_kwargs: Any) -> None:
        if is_debug_enabled():
            self._logger.debug(str(message))

    def info(self, message: Any, *_args: Any, **_kwargs: Any) -> None:
        self._logger.info(str(message))

    def warning(self, message: Any, *_args: Any, **_kwargs: Any) -> None:
        self._logger.warning(str(message))

    def error(self, message: Any, *_args: Any, **_kwargs: Any) -> None:
        self._logger.error(str(message))


_LOGGER = DesktopLogger()


def get_logger() -> DesktopLogger:
    return _LOGGER
