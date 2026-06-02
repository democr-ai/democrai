from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

from democrai.core.application.ai.engine.manifests import get_provider_definition
from democrai.core.runtime.foundation.app import app_ctx


_ENGINE_SECRET_PREFIX = "enc:v1:"


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
    return value.startswith(_ENGINE_SECRET_PREFIX)


def encrypt_value(value: str) -> str:
    if not value:
        return ""
    if is_encrypted_value(value):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_ENGINE_SECRET_PREFIX}{token}"


def decrypt_value(value: str) -> str:
    if not is_encrypted_value(value):
        return value
    token = value[len(_ENGINE_SECRET_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("invalid_engine_config_encrypted_payload") from exc


def encrypted_keys_for_provider(provider: str) -> list[str]:
    definition = get_provider_definition(provider) or {}
    raw = definition.get("encrypted_keys")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def decrypt_provider_config(provider: str, config: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(config or {})
    for key in encrypted_keys_for_provider(provider):
        if key not in payload:
            continue
        payload[key] = decrypt_value(payload.get(key))
    return payload


def encrypt_provider_config(
    provider: str,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(config or {})
    for key in encrypted_keys_for_provider(provider):
        if key not in payload:
            continue
        payload[key] = encrypt_value(payload.get(key))
    return payload
