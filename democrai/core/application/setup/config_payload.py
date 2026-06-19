from __future__ import annotations

import copy
import os
import secrets
from typing import Any

import yaml

from democrai.core.application.auth.jwt import ALGORITMS_LENGTH, DEFAULT_ALGORITHM
from democrai.core.platform.config.yaml_config import YamlConfigProvider
from democrai.core.platform.utils.timezone import get_system_timezone_name
from democrai.core.runtime.bootstrap.config_validation import (
    ConfigValidationResult,
    validate_config_provider,
)
from democrai.core.runtime.foundation.paths import get_base_dir, get_data_dir

LOCAL_TEMPLATE_NAME = "config.example.yaml"
DISTRIBUTED_TEMPLATE_NAME = "config.distributed.example.yaml"
EXAMPLE_JWT_SECRET = "change-me-with-a-long-random-secret"
EXAMPLE_ENGINE_CONFIG_ENCRYPTION_KEY = "local-encryption-key"


def template_path(template_name: str) -> str:
    if template_name == "local":
        filename = LOCAL_TEMPLATE_NAME
    elif template_name == "distributed":
        filename = DISTRIBUTED_TEMPLATE_NAME
    else:
        raise ValueError(f"Unsupported template {template_name!r}")
    return os.path.join(get_base_dir(), filename)


def list_template_paths() -> dict[str, str]:
    return {
        "local": "assets/config.example.yaml",
        "distributed": "assets/config.distributed.example.yaml",
    }


def load_config_payload(config_path: str) -> dict[str, Any]:
    provider = YamlConfigProvider(config_path)
    payload = getattr(provider, "_config", {}) or {}
    return copy.deepcopy(payload)


def load_yaml_payload_bytes(raw: bytes | bytearray | None) -> dict[str, Any]:
    payload = yaml.safe_load(bytes(raw or b"")) or {}
    return copy.deepcopy(payload if isinstance(payload, dict) else {})


def ensure_runtime_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    normalized.setdefault("app", {})
    normalized.setdefault("auth", {})
    if normalized["app"].get("engine_config_encryption_key") in (
        None,
        "",
        EXAMPLE_ENGINE_CONFIG_ENCRYPTION_KEY,
    ):
        normalized["app"]["engine_config_encryption_key"] = secrets.token_urlsafe(32)
    if normalized["auth"].get("jwt_secret") in (None, "", EXAMPLE_JWT_SECRET):
        alg = normalized["auth"].get("jwt_algorithm", DEFAULT_ALGORITHM)
        normalized["auth"]["jwt_secret"] = secrets.token_urlsafe(ALGORITMS_LENGTH[alg])
    return normalized


class DictConfigProvider:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        value: Any = self._data
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


def build_local_setup_config(media_path: str | None = None) -> dict[str, Any]:
    payload = ensure_runtime_secrets(load_config_payload(template_path("local")))
    payload.setdefault("app", {})
    payload["app"]["timezone"] = get_system_timezone_name()
    payload.setdefault("storage", {}).setdefault("media", {})
    payload["storage"]["media"]["type"] = "local"
    payload["storage"]["media"]["path"] = media_path or os.path.join(
        get_data_dir(), "assets"
    )
    return payload


def validate_distributed_setup_config(
    config_path: str | None,
) -> tuple[dict[str, Any], ConfigValidationResult]:
    payload = ensure_runtime_secrets(load_config_payload(config_path)) if config_path else {}
    result = validate_config_provider(
        DictConfigProvider(payload),
        config_path=config_path or "<memory>",
    )
    return payload, result


def validate_distributed_setup_payload(
    payload: dict[str, Any] | None,
    *,
    source_label: str = "<uploaded-config>",
) -> tuple[dict[str, Any], ConfigValidationResult]:
    normalized_payload = ensure_runtime_secrets(payload or {})
    result = validate_config_provider(
        DictConfigProvider(normalized_payload),
        config_path=source_label,
    )
    return normalized_payload, result


def apply_config_payload(config_provider: Any, payload: dict[str, Any]) -> None:
    if hasattr(config_provider, "_config"):
        config_provider._config = copy.deepcopy(payload)
        return

    def _walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_prefix = f"{prefix}.{key}" if prefix else key
                _walk(child_prefix, child)
            return
        config_provider.set(prefix, value)

    _walk("", payload)
