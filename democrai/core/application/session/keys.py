from __future__ import annotations

import secrets


def generate_session_key() -> str:
    """Return an opaque per-client session identifier."""
    return secrets.token_hex(32)
