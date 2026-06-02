from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

from democrai.core.runtime.foundation.app import app_ctx


def _fernet() -> Fernet:
    getter = getattr(getattr(app_ctx(), "config", None), "get", None)
    raw_key = ""
    if callable(getter):
        configured = getter("app.engine_config_encryption_key", "")
        raw_key = configured.strip() if isinstance(configured, str) else ""
    if not raw_key:
        raise RuntimeError("missing_app_engine_config_encryption_key")
    derived = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_resume_context(context: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not context:
        return None, None
    encoded = json.dumps(
        dict(context),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode(
        "utf-8",
    )
    digest = hashlib.sha256(encoded).hexdigest()
    return _fernet().encrypt(encoded).decode("utf-8"), digest


def decrypt_resume_context(context_encrypted: str | None) -> dict[str, Any]:
    token = context_encrypted.strip() if isinstance(context_encrypted, str) else ""
    if not token:
        return {}
    try:
        decoded = _fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("invalid_external_access_resume_context") from exc
    try:
        parsed = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid_external_access_resume_context") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid_external_access_resume_context")
    return parsed
