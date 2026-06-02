from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

from democrai.core.runtime.foundation.app import app_ctx


_ENV_SECRET_PREFIX = "env:v1:"


def _fernet() -> Fernet:
    getter = getattr(getattr(app_ctx(), "config", None), "get", None)
    raw_key = ""
    if callable(getter):
        raw_key = str(getter("app.engine_config_encryption_key", "") or "").strip()
    if not raw_key:
        raise RuntimeError("missing_app_engine_config_encryption_key")
    derived = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def is_encrypted_value(value: str) -> bool:
    return value.startswith(_ENV_SECRET_PREFIX)


def encrypt_value(value: str | None) -> str:
    raw = value or ""
    if not raw:
        return ""
    if is_encrypted_value(raw):
        return raw
    token = _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")
    return f"{_ENV_SECRET_PREFIX}{token}"


def decrypt_value(value: str | None) -> str:
    token = value or ""
    if not token:
        return ""
    if not is_encrypted_value(token):
        return token
    try:
        return _fernet().decrypt(token[len(_ENV_SECRET_PREFIX) :].encode("utf-8")).decode(
            "utf-8"
        )
    except InvalidToken as exc:
        raise ValueError("invalid_environment_encrypted_payload") from exc
