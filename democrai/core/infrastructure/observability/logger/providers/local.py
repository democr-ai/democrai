import logging
import os
import re
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import List, Union
from .base import LogProvider


def normalize_logger_name(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]", "_", name.lower()).replace(".", "_")


class EnsureExtrasFilter(logging.Filter):
    REQUIRED = {"clientip": "-", "user": "-", "uid": "-"}

    def filter(self, record: logging.LogRecord) -> bool:
        for k, v in self.REQUIRED.items():
            if not hasattr(record, k):
                setattr(record, k, v)
        return True


LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "%(clientip)-15s %(user)-12s uid=%(uid)s "
    "%(filename)s:%(lineno)d %(funcName)s - %(message)s"
)


class LocalFileLogProvider(LogProvider):
    """Local file logging provider with rotation."""

    def __init__(
        self,
        log_dir: Union[str, Path] = "logs",
        backup_count: int = 14,
        when: str = "midnight",
        interval: int = 1,
        utc: bool = False,
        level: int | None = None,
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.backup_count = backup_count
        self.when = when
        self.interval = interval
        self.utc = utc
        self.level = (
            level
            if level is not None
            else _resolve_log_level("DEMOCRAI_FILE_LOG_LEVEL", _default_log_level())
        )

    def get_handlers(self, name: str) -> List[logging.Handler]:
        filename = self.log_dir / f"{normalize_logger_name(name)}.log"
        h = TimedRotatingFileHandler(
            filename,
            when=self.when,
            interval=self.interval,
            backupCount=self.backup_count,
            encoding="utf-8",
            utc=self.utc,
        )
        h.setLevel(self.level)
        h.setFormatter(logging.Formatter(LOG_FORMAT))
        h.addFilter(EnsureExtrasFilter())
        setattr(h, "_democrai_logger_provider", "local")
        return [h]


def _resolve_log_level(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if not raw:
        return default
    return getattr(logging, raw.upper(), default)


def _default_log_level() -> int:
    if (
        getattr(sys, "frozen", False)
        or hasattr(sys, "nuitka_binary_dir")
        or "__compiled__" in globals()
    ):
        return logging.INFO
    return logging.DEBUG
