import logging
import os
import sys
from typing import Any, List, Optional
import re
from pathlib import Path
from logging.config import dictConfig


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

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"ensure_extras": {"()": EnsureExtrasFilter}},
    "formatters": {"standard": {"format": LOG_FORMAT}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",  # console: INFO+
            "formatter": "standard",
            "filters": ["ensure_extras"],
        },
    },
    "root": {
        "level": "INFO",  # root: INFO+
        "handlers": ["console"],
    },
}


from .providers.base import LogProvider
from .providers.cloud import CloudLogProvider
from .providers.local import LocalFileLogProvider, LOG_FORMAT


class LoggerManager:
    """
    Console globale (root): INFO+
    File per logger: DEBUG+ con rotazione giornaliera tramite LogProviders.
    """

    def __init__(
        self,
        log_dir: str | Path = "logs",
        providers: Optional[List[LogProvider]] = None,
        default_level: int | None = None,
        config: Any | None = None,
    ):
        dictConfig(LOGGING_CONFIG)

        self.base_log_dir = log_dir
        self.default_level = (
            default_level
            if default_level is not None
            else _resolve_log_level("DEMOCRAI_LOG_LEVEL", _default_log_level())
        )
        self._loggers: dict[str, logging.Logger] = {}

        if providers is None:
            self.providers: List[LogProvider] = self._providers_from_config(
                config,
                log_dir=log_dir,
            )
        else:
            self.providers = providers

        # crea i logger core
        self._get_or_create_logger("main")
        self._get_or_create_logger("stream")
        self._get_or_create_logger("ui")

    def _get_or_create_logger(self, name: str) -> logging.Logger:
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(self.default_level)
        logger.propagate = True
        self._remove_managed_handlers(logger)

        # Aggiungi handler da tutti i provider configurati
        for provider in self.providers:
            handlers = provider.get_handlers(name)
            for h in handlers:
                # Evita di aggiungere lo stesso handler più volte se re-inizializzato
                # (anche se qui usiamo una cache _loggers, è buona norma)
                if not any(
                    isinstance(existing_h, type(h)) for existing_h in logger.handlers
                ):
                    logger.addHandler(h)

        self._loggers[name] = logger
        return logger

    @staticmethod
    def _providers_from_config(
        config: Any | None,
        *,
        log_dir: str | Path,
    ) -> List[LogProvider]:
        getter = getattr(config, "get", None)
        provider_name = "local"
        if callable(getter):
            raw_provider = getter("logging.provider", "local")
            if raw_provider is None:
                raw_provider = "local"
            provider_name = str(raw_provider).strip().lower()
        if provider_name in {"", "local"}:
            return [LocalFileLogProvider(log_dir=log_dir)]
        if provider_name == "http":
            if not callable(getter):
                raise ValueError("logging_http_config_missing")
            raw_url = getter("logging.url", "")
            url = "" if raw_url is None else str(raw_url).strip()
            raw_method = getter("logging.method", "POST")
            if raw_method is None:
                raw_method = "POST"
            method = str(raw_method).strip().upper()
            if not url:
                raise ValueError("logging_http_url_required")
            return [CloudLogProvider(url=url, method=method)]
        raise ValueError(f"logging_provider_unknown:{provider_name}")

    @staticmethod
    def _remove_managed_handlers(logger: logging.Logger) -> None:
        for handler in logger.handlers[:]:
            if not getattr(handler, "_democrai_logger_provider", None):
                continue
            try:
                handler.close()
            finally:
                logger.removeHandler(handler)

    def get(
        self,
        name: str | None = None,
        *,
        uid: str | None = None,
        clientip: str | None = None,
        user: str | None = None,
    ) -> logging.LoggerAdapter:
        base = self._get_or_create_logger(name or "main")
        extra = {"uid": uid or "-", "clientip": clientip or "-", "user": user or "-"}
        return logging.LoggerAdapter(base, extra)

    def destroy(self, name: str) -> None:
        if name == "main":
            return
        logger = self._loggers.pop(name, None)
        if not logger:
            return
        for h in logger.handlers[:]:
            try:
                h.close()
            finally:
                logger.removeHandler(h)

    def info(self, message, name=None, uid=None, clientip=None, user=None, **kwargs):
        kwargs.setdefault("stacklevel", 2)
        self.get(name, uid=uid, clientip=clientip, user=user).info(message, **kwargs)

    def warning(self, message, name=None, uid=None, clientip=None, user=None, **kwargs):
        kwargs.setdefault("stacklevel", 2)
        self.get(name, uid=uid, clientip=clientip, user=user).warning(message, **kwargs)

    def error(self, message, name=None, uid=None, clientip=None, user=None, **kwargs):
        kwargs.setdefault("stacklevel", 2)
        if "exc_info" not in kwargs and sys.exc_info()[0] is not None:
            kwargs["exc_info"] = True
        self.get(name, uid=uid, clientip=clientip, user=user).error(message, **kwargs)

    def debug(self, message, name=None, uid=None, clientip=None, user=None, **kwargs):
        kwargs.setdefault("stacklevel", 2)
        self.get(name, uid=uid, clientip=clientip, user=user).debug(message, **kwargs)

    def critical(self, message, name=None, uid=None, clientip=None, user=None, **kwargs):
        kwargs.setdefault("stacklevel", 2)
        self.get(name, uid=uid, clientip=clientip, user=user).critical(message, **kwargs)

    def exception(self, message, name=None, uid=None, clientip=None, user=None, **kwargs):
        kwargs.setdefault("stacklevel", 2)
        kwargs.setdefault("exc_info", True)
        self.get(name, uid=uid, clientip=clientip, user=user).exception(message, **kwargs)


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
