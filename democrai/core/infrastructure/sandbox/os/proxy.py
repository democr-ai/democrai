from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

from democrai.core.platform.utils.debug import debug_os_sandbox_flow


logger = logging.getLogger(__name__)


def _write_proxy_diagnostic(event: str, **fields: Any) -> None:
    try:
        from democrai.core.runtime.foundation.paths import logs_dir

        path = logs_dir() / "os_sandbox_proxy_debug.log"
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "pid": os.getpid(),
            "event": str(event or "").strip(),
            **fields,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except Exception:
        pass


@dataclass(frozen=True)
class _ProxyEndpointPolicy:
    exact: frozenset[tuple[str, int]]
    wildcard_suffixes: frozenset[tuple[str, int]]

    @property
    def count(self) -> int:
        return len(self.exact) + len(self.wildcard_suffixes)

    def allows(self, host: str, port: int) -> bool:
        resolved_host = str(host or "").strip().lower()
        resolved_port = int(port or 0)
        if (resolved_host, resolved_port) in self.exact:
            return True
        for suffix, allowed_port in self.wildcard_suffixes:
            if resolved_port == allowed_port and resolved_host.endswith("." + suffix):
                return True
        return False


@dataclass(frozen=True)
class _ProxySession:
    session_id: str
    token: str
    endpoints: _ProxyEndpointPolicy


class OsSandboxConnectProxy:
    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._host = "127.0.0.1"
        self._port = 0
        self._sessions: dict[str, _ProxySession] = {}

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._handle_client, self._host, 0)
        sockets = self._server.sockets or ()
        if not sockets:
            raise RuntimeError("os_sandbox_proxy_missing_socket")
        self._port = int(sockets[0].getsockname()[1])
        debug_os_sandbox_flow(
            "proxy.server_start",
            host=self._host,
            port=self._port,
        )
        _write_proxy_diagnostic(
            "proxy.server_start",
            host=self._host,
            port=self._port,
        )

    async def close(self) -> None:
        server = self._server
        if server is None:
            return
        server.close()
        await server.wait_closed()
        self._server = None
        self._sessions.clear()
        debug_os_sandbox_flow("proxy.server_stop")

    def create_session(
        self,
        *,
        endpoints: list[dict[str, Any]],
    ) -> dict[str, str]:
        if self._server is None or self._port <= 0:
            raise RuntimeError("os_sandbox_proxy_not_started")
        session_id = secrets.token_urlsafe(24)
        token = secrets.token_urlsafe(32)
        session = _ProxySession(
            session_id=session_id,
            token=token,
            endpoints=_endpoint_policy(endpoints),
        )
        self._sessions[session_id] = session
        debug_os_sandbox_flow(
            "proxy.session_start",
            session_id=session_id,
            endpoint_count=session.endpoints.count,
        )
        _write_proxy_diagnostic(
            "proxy.session_start",
            session_id=session_id,
            endpoint_count=session.endpoints.count,
        )
        return {
            "session_id": session_id,
            "proxy_url": f"http://{token}:x@{self._host}:{self._port}",
        }

    def stop_session(self, session_id: str) -> None:
        resolved = str(session_id or "").strip()
        if not resolved:
            return
        self._sessions.pop(resolved, None)
        debug_os_sandbox_flow("proxy.session_stop", session_id=resolved)
        _write_proxy_diagnostic("proxy.session_stop", session_id=resolved)

    def update_session(
        self,
        session_id: str,
        *,
        endpoints: list[dict[str, Any]],
    ) -> dict[str, str]:
        resolved = str(session_id or "").strip()
        if not resolved:
            raise RuntimeError("os_sandbox_proxy_session_id_required")
        current = self._sessions.get(resolved)
        if current is None:
            raise RuntimeError(f"os_sandbox_proxy_session_not_found:{resolved}")
        updated = _ProxySession(
            session_id=current.session_id,
            token=current.token,
            endpoints=_endpoint_policy(endpoints),
        )
        self._sessions[resolved] = updated
        debug_os_sandbox_flow(
            "proxy.session_update",
            session_id=resolved,
            endpoint_count=updated.endpoints.count,
        )
        _write_proxy_diagnostic(
            "proxy.session_update",
            session_id=resolved,
            endpoint_count=updated.endpoints.count,
        )
        return {
            "session_id": resolved,
            "proxy_url": f"http://{current.token}:x@{self._host}:{self._port}",
        }

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        method = ""
        target = ""
        host = ""
        port = 0
        session_id = ""
        try:
            headers = await self._read_headers(reader)
            request_line, header_values = _parse_headers(headers)
            method, target, _version = request_line.split(" ", 2)
            debug_os_sandbox_flow(
                "proxy.connect_request",
                method=method,
                target=target,
            )
            _write_proxy_diagnostic(
                "proxy.connect_request",
                method=method,
                target=target,
            )
            if method.upper() != "CONNECT":
                await _write_proxy_error(writer, 405, "Method Not Allowed")
                return
            session = self._session_from_headers(header_values)
            session_id = session.session_id
            host, port = _parse_connect_target(target)
            debug_os_sandbox_flow(
                "proxy.connect_session_resolved",
                session_id=session_id,
                host=host,
                port=port,
            )
            _write_proxy_diagnostic(
                "proxy.connect_session_resolved",
                session_id=session_id,
                host=host,
                port=port,
            )
            if not session.endpoints.allows(host, port):
                _log_connect_denied(
                    session_id=session.session_id,
                    host=host,
                    port=port,
                    reason="endpoint_not_allowed",
                )
                await _write_proxy_error(writer, 403, "Forbidden")
                return
            debug_os_sandbox_flow(
                "proxy.connect_upstream_start",
                session_id=session_id,
                host=host,
                port=port,
            )
            _write_proxy_diagnostic(
                "proxy.connect_upstream_start",
                session_id=session_id,
                host=host,
                port=port,
            )
            upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
            debug_os_sandbox_flow(
                "proxy.connect_upstream_opened",
                session_id=session_id,
                host=host,
                port=port,
            )
            _write_proxy_diagnostic(
                "proxy.connect_upstream_opened",
                session_id=session_id,
                host=host,
                port=port,
            )
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            debug_os_sandbox_flow(
                "proxy.connect_allowed",
                session_id=session_id,
                host=host,
                port=port,
            )
            _write_proxy_diagnostic(
                "proxy.connect_allowed",
                session_id=session_id,
                host=host,
                port=port,
            )
            await _tunnel(reader, writer, upstream_reader, upstream_writer)
        except Exception as exc:
            if _is_proxy_auth_error(exc):
                debug_os_sandbox_flow(
                    "proxy.auth_required",
                    method=method,
                    target=target,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                _write_proxy_diagnostic(
                    "proxy.auth_required",
                    method=method,
                    target=target,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                with contextlib.suppress(Exception):
                    await _write_proxy_auth_required(writer)
                return
            debug_os_sandbox_flow(
                "proxy.connect_upstream_failed",
                session_id=session_id,
                method=method,
                target=target,
                host=host,
                port=port,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            _write_proxy_diagnostic(
                "proxy.connect_upstream_failed",
                session_id=session_id,
                method=method,
                target=target,
                host=host,
                port=port,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            debug_os_sandbox_flow(
                "proxy.client_error",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            with contextlib.suppress(Exception):
                await _write_proxy_error(writer, 502, "Bad Gateway")
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _read_headers(self, reader: asyncio.StreamReader) -> bytes:
        data = await reader.readuntil(b"\r\n\r\n")
        if len(data) > 16384:
            raise RuntimeError("os_sandbox_proxy_headers_too_large")
        return data

    def _session_from_headers(self, headers: dict[str, str]) -> _ProxySession:
        token = _proxy_token(headers.get("proxy-authorization", ""))
        if not token:
            raise RuntimeError("os_sandbox_proxy_missing_token")
        for session in self._sessions.values():
            if secrets.compare_digest(session.token, token):
                return session
        raise RuntimeError("os_sandbox_proxy_invalid_token")

def _endpoint_policy(endpoints: list[dict[str, Any]]) -> _ProxyEndpointPolicy:
    exact: set[tuple[str, int]] = set()
    wildcard_suffixes: set[tuple[str, int]] = set()
    for endpoint in endpoints:
        host = str(endpoint.get("host") or "").strip().lower()
        try:
            port = int(endpoint.get("port") or 0)
        except Exception:
            port = 0
        protocol = str(endpoint.get("protocol") or "tcp").strip().lower()
        if not host or port <= 0 or protocol != "tcp":
            continue
        wildcard_suffix = _wildcard_suffix(host)
        if wildcard_suffix is not None:
            wildcard_suffixes.add((wildcard_suffix, port))
            continue
        if "*" not in host:
            exact.add((host, port))
    return _ProxyEndpointPolicy(
        exact=frozenset(exact),
        wildcard_suffixes=frozenset(wildcard_suffixes),
    )


def _wildcard_suffix(host: str) -> str | None:
    value = str(host or "").strip().lower()
    if not value.startswith("*."):
        return None
    suffix = value[2:].strip(".")
    if not suffix or "*" in suffix:
        return None
    labels = [label for label in suffix.split(".") if label]
    if len(labels) < 2:
        return None
    return ".".join(labels)


def _log_connect_denied(
    *,
    session_id: str,
    host: str,
    port: int,
    reason: str,
) -> None:
    logger.warning(
        "[OsSandboxConnectProxy] connect denied session_id=%s host=%s port=%s reason=%s",
        session_id,
        host,
        int(port),
        reason,
    )
    debug_os_sandbox_flow(
        "proxy.connect_denied",
        session_id=session_id,
        host=host,
        port=port,
        reason=reason,
    )


def _parse_headers(data: bytes) -> tuple[str, dict[str, str]]:
    text = data.decode("iso-8859-1")
    lines = text.split("\r\n")
    request_line = lines[0].strip()
    if request_line.count(" ") < 2:
        raise RuntimeError("os_sandbox_proxy_invalid_request")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return request_line, headers


def _parse_connect_target(target: str) -> tuple[str, int]:
    value = str(target or "").strip()
    if value.startswith("["):
        host, _, rest = value[1:].partition("]")
        if not rest.startswith(":"):
            raise RuntimeError("os_sandbox_proxy_invalid_connect_target")
        port = int(rest[1:])
        return host.strip().lower(), port
    host, separator, raw_port = value.rpartition(":")
    if not separator or not host:
        raise RuntimeError("os_sandbox_proxy_invalid_connect_target")
    return host.strip().lower(), int(raw_port)


def _proxy_token(value: str) -> str:
    scheme, _, payload = str(value or "").partition(" ")
    if scheme.lower() != "basic" or not payload:
        return ""
    try:
        decoded = base64.b64decode(payload.strip(), validate=True).decode("utf-8")
    except Exception:
        return ""
    token, _, _password = decoded.partition(":")
    return token.strip()


def _is_proxy_auth_error(exc: Exception) -> bool:
    message = str(exc)
    return message in {
        "os_sandbox_proxy_missing_token",
        "os_sandbox_proxy_invalid_token",
    }


async def _write_proxy_auth_required(writer: asyncio.StreamWriter) -> None:
    body = b"407 Proxy Authentication Required\n"
    writer.write(
        (
            "HTTP/1.1 407 Proxy Authentication Required\r\n"
            'Proxy-Authenticate: Basic realm="democrai-os-sandbox"\r\n'
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        + body
    )
    await writer.drain()


async def _write_proxy_error(
    writer: asyncio.StreamWriter,
    status: int,
    reason: str,
) -> None:
    body = f"{int(status)} {reason}\n".encode("ascii", errors="replace")
    writer.write(
        (
            f"HTTP/1.1 {int(status)} {reason}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        + body
    )
    await writer.drain()


async def _tunnel(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
) -> None:
    async def relay(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
        finally:
            writer.close()

    await asyncio.gather(
        relay(client_reader, upstream_writer),
        relay(upstream_reader, client_writer),
        return_exceptions=True,
    )
