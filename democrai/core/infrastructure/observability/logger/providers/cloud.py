import json
import logging
import traceback
import urllib.request
from logging.handlers import HTTPHandler
from http import HTTPStatus
from typing import List
from urllib.parse import urlparse

from .base import LogProvider
from .local import EnsureExtrasFilter


class JsonHTTPHandler(HTTPHandler):
    """HTTPHandler variant that sends structured JSON log records."""

    def __init__(
        self,
        host: str,
        url: str,
        method: str = "POST",
        secure: bool = False,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ):
        super().__init__(host=host, url=url, method=method, secure=secure)
        self.headers = {} if headers is None else dict(headers)
        self.timeout = timeout

    def mapLogRecord(self, record: logging.LogRecord) -> dict[str, object]:
        payload: dict[str, object] = {
            "timestamp": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "user": getattr(record, "user", "-"),
            "uid": getattr(record, "uid", "-"),
            "clientip": getattr(record, "clientip", "-"),
        }
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))
        return payload

    def emit(self, record: logging.LogRecord) -> None:
        try:
            scheme = "https" if self.secure else "http"
            data = json.dumps(self.mapLogRecord(record)).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                **self.headers,
            }
            request = urllib.request.Request(
                f"{scheme}://{self.host}{self.url}",
                data=data,
                headers=headers,
                method=self.method,
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", HTTPStatus.OK)
                if int(status) >= HTTPStatus.BAD_REQUEST:
                    raise RuntimeError(f"logging_http_error:{int(status)}")
        except Exception:
            self.handleError(record)


class CloudLogProvider(LogProvider):
    """HTTP logging provider backed by the standard library HTTPHandler."""

    def __init__(self, url: str, api_key: str = "", method: str = "POST"):
        self.endpoint = url.strip()
        self.url = self.endpoint
        self.api_key = api_key
        self.method = method.strip().upper()
        if not self.method:
            self.method = "POST"
        self._handler_host, self._handler_url, self._secure = self._parse_url(
            self.endpoint
        )

    def get_handlers(self, name: str) -> List[logging.Handler]:
        handler = JsonHTTPHandler(
            host=self._handler_host,
            url=self._handler_url,
            method=self.method,
            secure=self._secure,
        )
        handler.setLevel(logging.INFO)
        handler.addFilter(EnsureExtrasFilter())
        setattr(handler, "_democrai_logger_provider", "http")
        return [handler]

    @staticmethod
    def _parse_url(url: str) -> tuple[str, str, bool]:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("logging_http_url_invalid")
        host = parsed.hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return host, path, scheme == "https"
