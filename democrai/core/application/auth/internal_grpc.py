from __future__ import annotations

from typing import Any

import grpc

from democrai.core.application.auth.jwt import create_internal_service_token
from democrai.core.application.auth.jwt import decode_internal_service_token


AUTHORIZATION_METADATA_KEY = "authorization"


def internal_service_auth_metadata(
    *,
    audience: str,
    scopes: list[str] | tuple[str, ...] | None = None,
) -> tuple[tuple[str, str], ...]:
    token = create_internal_service_token(audience=audience, scopes=scopes)
    return ((AUTHORIZATION_METADATA_KEY, f"Bearer {token}"),)


def _bearer_token(context: Any) -> str:
    metadata = getattr(context, "invocation_metadata", None)
    items = metadata() if callable(metadata) else []
    for key, value in list(items or []):
        if str(key).lower() != AUTHORIZATION_METADATA_KEY:
            continue
        raw = str(value or "").strip()
        if raw.lower().startswith("bearer "):
            return raw.split(" ", 1)[1].strip()
    return ""


async def require_internal_service_auth(
    context: Any,
    *,
    audience: str,
    scopes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    token = _bearer_token(context)
    claims = (
        decode_internal_service_token(
            token,
            audience=audience,
            required_scopes=scopes,
        )
        if token
        else None
    )
    if claims is None:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "internal_service_auth_required")
    return claims
