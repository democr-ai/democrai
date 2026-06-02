from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import app_ctx


@dataclass(frozen=True)
class ExtractedAuth:
    user: int | None = None
    role: Any = None
    organization_id: int | None = None
    access_level: Any = None
    error: str | None = None


def extract_auth_state(msg: dict) -> ExtractedAuth:
    if bool(getattr(app_ctx(), "setup_mode", False)):
        return ExtractedAuth()

    from democrai.core.application.auth.jwt import decode_access_token_result

    jwt_token = msg.get("jwt")
    if jwt_token:
        result = decode_access_token_result(jwt_token)
        if result.payload:
            payload = result.payload
            user_id = to_optional_int(payload.get("user_id"))
            organization_id = to_optional_int(payload.get("organization_id"))
            return ExtractedAuth(
                user=user_id,
                role=payload.get("role"),
                organization_id=organization_id,
                access_level=payload.get("access_level"),
            )
        return ExtractedAuth(error=result.error)
    return ExtractedAuth()


def extract_auth(msg: dict):
    auth = extract_auth_state(msg)
    return auth.user, auth.role, auth.organization_id, auth.access_level


def session_scope_key(network, bus, client_id) -> str:
    key = (id(bus), client_id)
    session_key = network._client_session_keys.get(key)
    if session_key:
        return f"session:{session_key}"

    authenticated = network._authenticated_clients.get(key)
    if authenticated:
        user_id = to_optional_int(authenticated[0])
        if user_id is not None:
            return f"user:{user_id}"
    return f"client:{id(bus)}:{client_id}"


def push_notifications_update(bus, client_id, *, count: int) -> None:
    bus.send(
        client_id,
        {
            "type": "notifications_update",
            "notificationsUpdate": {"count": count},
        },
    )


def push_external_access_approved(bus, client_id, *, module_name: str, target: str) -> None:
    bus.send(
        client_id,
        {
            "type": "external_access_approved",
            "externalAccessApproved": {
                "module_name": module_name,
                "target": target,
            },
        },
    )
