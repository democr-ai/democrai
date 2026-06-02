from __future__ import annotations

import asyncio
import contextvars
import logging
import socket
import threading
from http import client as http_client
from types import TracebackType
from typing import Any
from urllib.parse import urljoin, urlparse

from democrai.core.application.services.external_access import (
    EXTERNAL_RESOURCE_NETWORK,
    ExternalAccessApprovalRequired,
    check_external_access,
)
from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import operation_for_http_method
from democrai.core.application.access_policy.operations import ResourceType
from democrai.core.infrastructure.network.targets import is_network_target_allowed
from democrai.core.platform.utils.identity import to_optional_int

_LOGGER = logging.getLogger(__name__)


_ORIGINALS: dict[str, Any] = {}
_ACTIVE = False
_ACTIVE_COUNT = 0
_ACTIVE_LOCK = threading.Lock()
_STATE: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "network_policy_state",
    default=None,
)


def _state() -> dict[str, Any]:
    current = _STATE.get()
    return current if isinstance(current, dict) else {}


def _subject_name() -> str:
    return str(_state().get("subject_name") or "").strip()


def _subject_type() -> str:
    return str(_state().get("subject_type") or "module").strip() or "module"


def _request_context() -> tuple[int | None, int | None, str | None]:
    current_state = _state()
    return (
        to_optional_int(current_state.get("user_id")),
        to_optional_int(current_state.get("organization_id")),
        str(current_state.get("session_key") or "").strip() or None,
    )


def _request_context_from_runtime() -> tuple[int | None, int | None, str | None]:
    try:
        from democrai.core.runtime.foundation.app import req_ctx

        current = req_ctx()
        return current.user, current.organization_id, current.session_key
    except Exception:
        return None, None, None


def _network_access_allowed(target: str, *, operation: str) -> bool:
    if _configured_remote_service_target_allowed(target):
        return True
    state_access = tuple(_state().get("access") or ())
    try:
        from democrai.core.infrastructure.sandbox import process_guard as process_guard_mod

        process_access = tuple(process_guard_mod._state().get("access") or ())
    except Exception:
        process_access = ()
    for rule in (*state_access, *process_access):
        resource = getattr(rule, "resource", None)
        if resource is None:
            continue
        if resource.resource_type != ResourceType.NETWORK:
            continue
        if resource.operation.value != operation:
            continue
        if is_network_target_allowed(target, [resource.normalized_target]):
            return True
    return False


def _configured_remote_service_target_allowed(target: str) -> bool:
    try:
        from democrai.core.infrastructure.sandbox.os.sources import (
            collect_config_access_targets,
        )
        from democrai.core.runtime.foundation.app import app_ctx
    except Exception:
        return False

    try:
        allowed = tuple(collect_config_access_targets(getattr(app_ctx(), "config", None)))
    except Exception:
        return False
    if not allowed:
        return False
    return is_network_target_allowed(target, allowed)


def _patch_optional_library(
    *,
    label: str,
    importer,
    patcher,
) -> None:
    try:
        imported = importer()
    except ImportError:
        return
    try:
        patcher(imported)
    except Exception as exc:
        _LOGGER.error(
            "network policy_guard: failed to patch %s (%s); aborting network guard activation",
            label,
            exc,
        )
        raise RuntimeError(f"network policy_guard patch failed for {label}") from exc


def _check_url(url: str, *, operation: str = "receive") -> None:
    normalized = str(url or "").strip()
    if not normalized:
        raise PermissionError("network_target_missing")
    if _network_access_allowed(normalized, operation=operation):
        return
    access = check_external_access(
        subject_type=_subject_type(),
        subject_name=_subject_name(),
        resource_type=EXTERNAL_RESOURCE_NETWORK,
        operation=operation,
        target=normalized,
        register_request=True,
    )
    if not access.allowed:
        if bool(getattr(access, "requires_approval", False)):
            raise ExternalAccessApprovalRequired(
                subject_type=_subject_type(),
                subject_name=_subject_name(),
                resource_type=EXTERNAL_RESOURCE_NETWORK,
                operation=operation,
                target=normalized,
                message=access.message,
                code=getattr(access, "code", ""),
            )
        raise PermissionError(access.message)


def _check_target(
    host: str, port: int | None = None, *, operation: str = "connect"
) -> None:
    normalized = str(host or "").strip()
    target = f"{normalized}:{int(port)}" if port is not None else normalized
    if _network_access_allowed(target, operation=operation):
        return
    access = check_external_access(
        subject_type=_subject_type(),
        subject_name=_subject_name(),
        resource_type=EXTERNAL_RESOURCE_NETWORK,
        operation=operation,
        target=target,
        register_request=True,
    )
    if not access.allowed:
        if bool(getattr(access, "requires_approval", False)):
            raise ExternalAccessApprovalRequired(
                subject_type=_subject_type(),
                subject_name=_subject_name(),
                resource_type=EXTERNAL_RESOURCE_NETWORK,
                operation=operation,
                target=target,
                message=access.message,
                code=getattr(access, "code", ""),
            )
        raise PermissionError(access.message)


def _wrap_urlopen(original):
    def wrapper(url, *args, **kwargs):
        url_str = url if isinstance(url, str) else getattr(url, "full_url", str(url))
        _check_url(url_str)
        return original(url, *args, **kwargs)

    return wrapper


def _wrap_http_request(original):
    def wrapper(self_obj, method, url, *args, **kwargs):
        _check_url(
            _resolve_request_url(self_obj, url),
            operation=operation_for_http_method(method),
        )
        return original(self_obj, method, url, *args, **kwargs)

    return wrapper


def _wrap_aiohttp_request(original):
    async def wrapper(self_obj, method, url, *args, **kwargs):
        _check_url(
            _resolve_request_url(self_obj, url),
            operation=operation_for_http_method(method),
        )
        return await original(self_obj, method, url, *args, **kwargs)

    return wrapper


def _resolve_request_url(client: Any, url: Any) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return value
    base_url = str(getattr(client, "base_url", "") or "").strip()
    if not base_url:
        return value
    return urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))


def _wrap_socket_connect(original):
    def wrapper(self_conn, address, *args, **kwargs):
        if isinstance(address, tuple) and address:
            host = address[0]
            port = address[1] if len(address) > 1 else None
            _check_target(str(host), port, operation="connect")
        return original(self_conn, address, *args, **kwargs)

    return wrapper


def _wrap_socket_connect_ex(original):
    def wrapper(self_conn, address, *args, **kwargs):
        if isinstance(address, tuple) and address:
            host = address[0]
            port = address[1] if len(address) > 1 else None
            _check_target(str(host), port, operation="connect")
        return original(self_conn, address, *args, **kwargs)

    return wrapper


def _wrap_socket_sendto(original):
    def wrapper(self_conn, data, address_or_flags, *args, **kwargs):
        address = address_or_flags
        if not isinstance(address_or_flags, tuple) and args:
            address = args[0]
        if isinstance(address, tuple) and address:
            host = address[0]
            port = address[1] if len(address) > 1 else None
            _check_target(str(host), port, operation="send")
        return original(self_conn, data, address_or_flags, *args, **kwargs)

    return wrapper


def _wrap_create_connection(original):
    def wrapper(address, *args, **kwargs):
        if isinstance(address, tuple) and address:
            host = address[0]
            port = address[1] if len(address) > 1 else None
            _check_target(str(host), port, operation="connect")
        return original(address, *args, **kwargs)

    return wrapper


def _wrap_asyncio_open_connection(original):
    async def wrapper(host=None, port=None, *args, **kwargs):
        if host is not None:
            _check_target(str(host), port, operation="connect")
        return await original(host, port, *args, **kwargs)

    return wrapper


def enable_network_policy(
    *,
    subject_name: str,
    subject_type: str = "module",
    access: list[AccessManifestRule] | tuple[AccessManifestRule, ...] | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
    session_key: str | None = None,
) -> contextvars.Token:
    global _ACTIVE, _ACTIVE_COUNT
    parent_state = _state()
    (
        runtime_user_id,
        runtime_organization_id,
        runtime_session_key,
    ) = _request_context_from_runtime()
    resolved_subject_name = (
        str(subject_name or "").strip()
        or str(parent_state.get("subject_name") or "").strip()
    )
    resolved_subject_type = (
        str(subject_type or "").strip()
        or str(parent_state.get("subject_type") or "module").strip()
    )
    resolved_user_id = (
        user_id
        if user_id is not None
        else parent_state.get("user_id")
        if parent_state.get("user_id") is not None
        else runtime_user_id
    )
    resolved_organization_id = (
        organization_id
        if organization_id is not None
        else parent_state.get("organization_id")
        if parent_state.get("organization_id") is not None
        else runtime_organization_id
    )
    resolved_session_key = (
        str(session_key or "").strip()
        or parent_state.get("session_key")
        or runtime_session_key
    )
    token = _STATE.set(
        {
            "subject_name": resolved_subject_name,
            "subject_type": resolved_subject_type or "module",
            "access": (*tuple(parent_state.get("access") or ()), *tuple(access or ())),
            "user_id": to_optional_int(resolved_user_id),
            "organization_id": to_optional_int(resolved_organization_id),
            "session_key": str(resolved_session_key or "").strip() or None,
        }
    )
    with _ACTIVE_LOCK:
        _ACTIVE_COUNT += 1
        if _ACTIVE:
            return token
        _ACTIVE = True

    import urllib.request

    _ORIGINALS["urllib.request.urlopen"] = urllib.request.urlopen
    urllib.request.urlopen = _wrap_urlopen(urllib.request.urlopen)

    try:
        _patch_optional_library(
            label="requests.sessions.Session.request",
            importer=lambda: __import__("requests.sessions", fromlist=["dummy"]),
            patcher=lambda requests_sessions: (
                _ORIGINALS.__setitem__(
                    "requests.sessions.Session.request",
                    requests_sessions.Session.request,
                ),
                setattr(
                    requests_sessions.Session,
                    "request",
                    _wrap_http_request(requests_sessions.Session.request),
                ),
            ),
        )
        _patch_optional_library(
            label="httpx.Client.request/httpx.AsyncClient.request",
            importer=lambda: __import__("httpx"),
            patcher=lambda httpx: (
                _ORIGINALS.__setitem__("httpx.Client.request", httpx.Client.request),
                _ORIGINALS.__setitem__(
                    "httpx.AsyncClient.request",
                    httpx.AsyncClient.request,
                ),
                setattr(
                    httpx.Client, "request", _wrap_http_request(httpx.Client.request)
                ),
                setattr(
                    httpx.AsyncClient,
                    "request",
                    _wrap_aiohttp_request(httpx.AsyncClient.request),
                ),
            ),
        )
        _patch_optional_library(
            label="aiohttp.ClientSession._request",
            importer=lambda: __import__("aiohttp"),
            patcher=lambda aiohttp: (
                _ORIGINALS.__setitem__(
                    "aiohttp.ClientSession._request",
                    aiohttp.ClientSession._request,
                ),
                setattr(
                    aiohttp.ClientSession,
                    "_request",
                    _wrap_aiohttp_request(aiohttp.ClientSession._request),
                ),
            ),
        )

        _ORIGINALS["socket.socket.connect"] = socket.socket.connect
        socket.socket.connect = _wrap_socket_connect(socket.socket.connect)
        _ORIGINALS["socket.socket.connect_ex"] = socket.socket.connect_ex
        socket.socket.connect_ex = _wrap_socket_connect_ex(socket.socket.connect_ex)
        _ORIGINALS["socket.socket.sendto"] = socket.socket.sendto
        socket.socket.sendto = _wrap_socket_sendto(socket.socket.sendto)
        _ORIGINALS["socket.create_connection"] = socket.create_connection
        socket.create_connection = _wrap_create_connection(socket.create_connection)
        _ORIGINALS["asyncio.open_connection"] = asyncio.open_connection
        asyncio.open_connection = _wrap_asyncio_open_connection(asyncio.open_connection)
        _ORIGINALS[
            "http.client.HTTPConnection.__init__"
        ] = http_client.HTTPConnection.__init__
        _ORIGINALS[
            "http.client.HTTPSConnection.__init__"
        ] = http_client.HTTPSConnection.__init__

        def _http_init_wrapper(original, scheme):
            def wrapper(self_conn, host, *args, **kwargs):
                port = kwargs.get("port")
                if port is None and args:
                    port = args[0]
                target = str(host or "").strip()
                if port is not None and ":" not in target.rsplit("]", 1)[-1]:
                    target = f"{target}:{int(port)}"
                _check_url(f"{scheme}://{target}", operation="connect")
                return original(self_conn, host, *args, **kwargs)

            return wrapper

        http_client.HTTPConnection.__init__ = _http_init_wrapper(
            http_client.HTTPConnection.__init__, "http"
        )
        http_client.HTTPSConnection.__init__ = _http_init_wrapper(
            http_client.HTTPSConnection.__init__, "https"
        )
    except Exception:
        disable_network_policy(token)
        raise
    return token


def disable_network_policy(token: contextvars.Token | None = None) -> None:
    global _ACTIVE, _ACTIVE_COUNT
    if token is not None:
        try:
            _STATE.reset(token)
        except Exception:
            _STATE.set(None)
    else:
        _STATE.set(None)
    if not _ACTIVE:
        return
    with _ACTIVE_LOCK:
        if _ACTIVE_COUNT > 0:
            _ACTIVE_COUNT -= 1
        if _ACTIVE_COUNT > 0:
            return

    import urllib.request

    if "urllib.request.urlopen" in _ORIGINALS:
        urllib.request.urlopen = _ORIGINALS["urllib.request.urlopen"]
    try:
        import requests.sessions

        if "requests.sessions.Session.request" in _ORIGINALS:
            requests.sessions.Session.request = _ORIGINALS[
                "requests.sessions.Session.request"
            ]
    except Exception:
        pass
    try:
        import httpx

        if "httpx.Client.request" in _ORIGINALS:
            httpx.Client.request = _ORIGINALS["httpx.Client.request"]
        if "httpx.AsyncClient.request" in _ORIGINALS:
            httpx.AsyncClient.request = _ORIGINALS["httpx.AsyncClient.request"]
    except Exception:
        pass
    try:
        import aiohttp

        if "aiohttp.ClientSession._request" in _ORIGINALS:
            aiohttp.ClientSession._request = _ORIGINALS[
                "aiohttp.ClientSession._request"
            ]
    except Exception:
        pass
    if "socket.socket.connect" in _ORIGINALS:
        socket.socket.connect = _ORIGINALS["socket.socket.connect"]
    if "socket.socket.connect_ex" in _ORIGINALS:
        socket.socket.connect_ex = _ORIGINALS["socket.socket.connect_ex"]
    if "socket.socket.sendto" in _ORIGINALS:
        socket.socket.sendto = _ORIGINALS["socket.socket.sendto"]
    if "socket.create_connection" in _ORIGINALS:
        socket.create_connection = _ORIGINALS["socket.create_connection"]
    if "asyncio.open_connection" in _ORIGINALS:
        asyncio.open_connection = _ORIGINALS["asyncio.open_connection"]
    if "http.client.HTTPConnection.__init__" in _ORIGINALS:
        http_client.HTTPConnection.__init__ = _ORIGINALS[
            "http.client.HTTPConnection.__init__"
        ]
    if "http.client.HTTPSConnection.__init__" in _ORIGINALS:
        http_client.HTTPSConnection.__init__ = _ORIGINALS[
            "http.client.HTTPSConnection.__init__"
        ]
    _ORIGINALS.clear()
    _ACTIVE = False
    _STATE.set(None)


class network_policy_context:
    def __init__(
        self,
        *,
        subject_name: str,
        subject_type: str = "module",
        access: list[AccessManifestRule] | tuple[AccessManifestRule, ...] | None = None,
        user_id: int | None = None,
        organization_id: int | None = None,
        session_key: str | None = None,
    ) -> None:
        self.subject_name = subject_name
        self.subject_type = subject_type
        self.access = tuple(access or ())
        self.user_id = user_id
        self.organization_id = organization_id
        self.session_key = session_key
        self._token: contextvars.Token | None = None

    def __enter__(self) -> "network_policy_context":
        self._token = enable_network_policy(
            subject_name=self.subject_name,
            subject_type=self.subject_type,
            access=self.access,
            user_id=self.user_id,
            organization_id=self.organization_id,
            session_key=self.session_key,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        disable_network_policy(self._token)

