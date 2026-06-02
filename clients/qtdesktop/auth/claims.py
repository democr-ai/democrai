from __future__ import annotations

import base64
import json


def decode_jwt_claims(token: str) -> dict:
    """
    Lightweight JWT payload decode for desktop UI permissions.
    No signature validation here: server-side auth remains authoritative.
    """
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + padding)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def extract_auth_identity(token: str | None) -> tuple[str, list[str]]:
    """Extract normalized `(role, permissions)` tuple from an optional JWT.

        role, perms = extract_auth_identity(token)
    """
    if not token:
        return "Guest", []
    payload = decode_jwt_claims(token)
    role = payload.get("role") or "Guest"
    perms = payload.get("permissions") or []
    if not isinstance(perms, list):
        perms = []
    return str(role), [str(p) for p in perms]


def extract_token_expiry(token: str | None) -> int | None:
    """Returns JWT `exp` as UNIX seconds when present and valid."""
    if not token:
        return None
    payload = decode_jwt_claims(token)
    exp = payload.get("exp")
    try:
        parsed = int(exp)
        if parsed > 0:
            return parsed
    except Exception:
        return None
    return None
