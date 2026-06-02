from __future__ import annotations

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


def resolve_client_ip(headers: Any, client: Any = None) -> Optional[str]:
    forwarded_for = None
    try:
        forwarded_for = headers.get("x-forwarded-for")
    except AttributeError:
        app_ctx().logger.warning(
            "[Auth] Cannot resolve client IP: headers object has no .get()"
        )
    if forwarded_for:
        first = str(forwarded_for).split(",", 1)[0].strip()
        if first:
            return first
    try:
        real_ip = headers.get("x-real-ip")
    except AttributeError:
        real_ip = None
    if real_ip:
        real_ip = str(real_ip).strip()
        if real_ip:
            return real_ip
    host = getattr(client, "host", None)
    return str(host) if host else None


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
