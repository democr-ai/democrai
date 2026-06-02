from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

from democrai.core.runtime.foundation.app import app_ctx


def _fernet() -> Fernet:
    ctx = app_ctx()
    getter = getattr(getattr(ctx, "config", None), "get", None)
    raw_key = ""
    if callable(getter):
        configured = getter("app.engine_config_encryption_key", "")
        raw_key = configured.strip() if isinstance(configured, str) else ""
    if not raw_key:
        raise RuntimeError("missing_app_engine_config_encryption_key")
    derived = hashlib.sha256(raw_key.encode("utf-8")).digest()
    token_key = base64.urlsafe_b64encode(derived)
    return Fernet(token_key)


def encrypt_config(config: dict[str, Any]) -> str:
    payload = {} if config is None else dict(config)
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return _fernet().encrypt(encoded).decode("utf-8")


def decrypt_config(config_encrypted: str | None) -> dict[str, Any]:
    token = config_encrypted.strip() if isinstance(config_encrypted, str) else ""
    if not token:
        return {}
    try:
        decoded = _fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("invalid_mcp_config_encrypted_payload") from exc
    try:
        parsed = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid_mcp_config_decrypted_payload") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid_mcp_config_decrypted_payload")
    return parsed
