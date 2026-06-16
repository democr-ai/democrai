from __future__ import annotations

import ipaddress
from typing import Any, Optional

from fastapi import Request, WebSocket

from democrai.core.application.auth.jwt import decode_access_token
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import app_ctx


def decode_token_if_present(token: Optional[str]) -> Optional[dict[str, Any]]:
    if not token:
        return None
    if bool(getattr(app_ctx(), "setup_mode", False)):
        return None
    return decode_access_token(token, log_expired=False)


def decode_token_claims_unverified(token: Optional[str]) -> Optional[dict[str, Any]]:
    """Decode JWT claims without verifying signature or expiry. Use only for non-auth purposes (e.g. logging user_id on expired token)."""
    if not token:
        return None
    try:
        import jwt as pyjwt
        return pyjwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
            algorithms=["HS256", "RS256"],
        )
    except Exception:
        return None


def resolve_request_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    x_jwt = request.headers.get("X-JWT")
    if x_jwt:
        return str(x_jwt).strip() or None
    from .cookies import auth_cookie_name

    cookie_token = request.cookies.get(auth_cookie_name())
    if cookie_token:
        return cookie_token
    return None


def resolve_websocket_token(ws: WebSocket) -> Optional[str]:
    auth_header = ws.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    query_token = ws.query_params.get("token") or ws.query_params.get("jwt")
    if query_token:
        return query_token
    from .cookies import auth_cookie_name

    cookie_token = ws.cookies.get(auth_cookie_name())
    if cookie_token:
        return cookie_token
    return None


def _header_value(headers: Any, name: str) -> str:
    try:
        value = headers.get(name)
    except AttributeError:
        app_ctx().logger.warning(
            "[Auth] Cannot resolve client IP: headers object has no .get()"
        )
        return ""
    return str(value or "").strip()


def _direct_client_ip(client: Any = None) -> Optional[str]:
    host = getattr(client, "host", None)
    resolved = str(host or "").strip()
    return resolved or None


def _valid_ip_header(value: str) -> str:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return ""
    return value


def _forwarded_for_chain(headers: Any) -> list[str]:
    forwarded_for = _header_value(headers, "x-forwarded-for")
    if not forwarded_for:
        return []
    chain: list[str] = []
    for item in forwarded_for.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        valid = _valid_ip_header(candidate)
        if valid:
            chain.append(valid)
    return chain


def _forwarded_client_ip(headers: Any, *, validate: bool = False) -> Optional[str]:
    forwarded_for = _header_value(headers, "x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            resolved = _valid_ip_header(first) if validate else first
            if resolved:
                return resolved
    real_ip = _header_value(headers, "x-real-ip")
    if validate and real_ip:
        return _valid_ip_header(real_ip) or None
    return real_ip or None


def _http_config_value(key: str, default: Any = None) -> Any:
    config = getattr(app_ctx(), "config", None)
    if config is None:
        return default
    return config.get(key, default)


def _trusted_proxy_networks() -> list[Any]:
    raw = _http_config_value("http.client_ip.trusted_proxies", [])
    if raw is None:
        values: list[Any] = []
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = [item.strip() for item in str(raw).split(",")]
    networks: list[Any] = []
    for value in values:
        candidate = str(value or "").strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted_proxy(peer_ip: str | None) -> bool:
    if not peer_ip:
        return False
    try:
        address = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(address in network for network in _trusted_proxy_networks())


def _client_ip_from_trusted_proxy_chain(headers: Any, direct_ip: str | None) -> Optional[str]:
    chain = _forwarded_for_chain(headers)
    if direct_ip:
        chain.append(direct_ip)
    for candidate in reversed(chain):
        if not _is_trusted_proxy(candidate):
            return candidate
    if chain:
        return chain[0]
    real_ip = _header_value(headers, "x-real-ip")
    return _valid_ip_header(real_ip) or direct_ip


def resolve_client_ip(headers: Any, client: Any = None) -> Optional[str]:
    mode = str(_http_config_value("http.client_ip.mode", "always_trust") or "").strip().lower()
    direct_ip = _direct_client_ip(client)
    if mode == "never":
        return direct_ip
    if mode == "trusted_proxy":
        if _is_trusted_proxy(direct_ip):
            return _client_ip_from_trusted_proxy_chain(headers, direct_ip)
        return direct_ip
    return _forwarded_client_ip(headers) or direct_ip


def auth_payload_to_response(payload: Optional[dict[str, Any]]) -> dict[str, Any]:
    user_id = None if not payload else to_optional_int(payload.get("user_id"))
    if not payload or user_id is None:
        return {
            "authenticated": False,
            "user": None,
            "role": "Guest",
            "permissions": [],
            "organization_id": None,
            "access_level": None,
        }

    from democrai.core.application.auth.service import get_user_permissions

    try:
        permissions = get_user_permissions(user_id)
    except Exception as exc:
        app_ctx().logger.error(
            f"[Auth] Failed to load permissions for user {user_id}: {exc}"
        )
        raise RuntimeError(
            f"Cannot load permissions for user {user_id}: service unavailable"
        ) from exc

    return {
        "authenticated": True,
        "user": str(user_id),
        "user_id": user_id,
        "role": payload.get("role") or "User",
        "permissions": permissions,
        "organization_id": to_optional_int(payload.get("organization_id")),
        "access_level": payload.get("access_level"),
    }
