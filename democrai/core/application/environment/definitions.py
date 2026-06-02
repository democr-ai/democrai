from __future__ import annotations

import re
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

from democrai.core.runtime.foundation.app import app_ctx


ENVIRONMENT_SUBJECT_GLOBAL = "global"
ENVIRONMENT_SUBJECT_MODULE = "module"
ENVIRONMENT_SUBJECT_ENGINE = "engine"
ENVIRONMENT_SUBJECT_EXTRACTOR = "extractor"

VALID_SUBJECT_KINDS = {
    ENVIRONMENT_SUBJECT_GLOBAL,
    ENVIRONMENT_SUBJECT_MODULE,
    ENVIRONMENT_SUBJECT_ENGINE,
    ENVIRONMENT_SUBJECT_EXTRACTOR,
}

_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_RESERVED_PREFIXES = ("DEMOCRAI_",)
_RESERVED_NAMES = {"PATH", "PYTHONPATH", "LD_PRELOAD", "LD_LIBRARY_PATH"}


@dataclass(frozen=True)
class EnvironmentVariableDefinition:
    subject_kind: str
    subject: str
    name: str
    label: str = ""
    description: str = ""
    required: bool = False
    secret: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_subject_kind(value: str) -> str:
    if not isinstance(value, str) or value not in VALID_SUBJECT_KINDS:
        raise ValueError("invalid_environment_subject_kind")
    return value


def verify_subject(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_environment_subject")
    return value


def verify_env_name(value: str) -> str:
    if not isinstance(value, str) or not value or not _ENV_NAME_RE.match(value):
        raise ValueError("invalid_environment_variable_name")
    if value in _RESERVED_NAMES or any(
        value.startswith(prefix) for prefix in _RESERVED_PREFIXES
    ):
        raise ValueError("reserved_environment_variable_name")
    return value


def _definition_store() -> dict[tuple[str, str, str], EnvironmentVariableDefinition]:
    ctx = app_ctx()
    store = getattr(ctx, "environment_variable_definitions", None)
    if not isinstance(store, dict):
        store = {}
        ctx.environment_variable_definitions = store
    return store


def _definition_from_raw(
    *,
    subject_kind: str,
    subject: str,
    raw: dict[str, Any],
) -> EnvironmentVariableDefinition:
    if not isinstance(raw, dict):
        raise ValueError("invalid_environment_definition")
    name = verify_env_name(raw["name"])
    label = raw.get("label", name)
    description = raw.get("description", "")
    required = raw.get("required", False)
    secret = raw.get("secret", True)
    if not isinstance(label, str) or not label:
        raise ValueError("invalid_environment_definition_label")
    if not isinstance(description, str):
        raise ValueError("invalid_environment_definition_description")
    if not isinstance(required, bool):
        raise ValueError("invalid_environment_definition_required")
    if not isinstance(secret, bool):
        raise ValueError("invalid_environment_definition_secret")
    return EnvironmentVariableDefinition(
        subject_kind=verify_subject_kind(subject_kind),
        subject=verify_subject(subject),
        name=name,
        label=label,
        description=description,
        required=required,
        secret=secret,
    )


def register_environment_definitions(
    *,
    subject_kind: str,
    subject: str,
    definitions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> None:
    if definitions is None:
        return
    if not isinstance(definitions, (list, tuple)):
        raise ValueError("invalid_environment_definitions")
    store = _definition_store()
    for raw in definitions:
        definition = _definition_from_raw(
            subject_kind=subject_kind,
            subject=subject,
            raw=raw,
        )
        store[(definition.subject_kind, definition.subject, definition.name)] = definition


def list_environment_definitions(
    *,
    subject_kind: str | None = None,
    subject: str | None = None,
) -> list[dict[str, Any]]:
    kind_filter = verify_subject_kind(subject_kind) if subject_kind is not None else None
    subject_filter = verify_subject(subject) if subject is not None else None
    rows: list[dict[str, Any]] = []
    for definition in _definition_store().values():
        if kind_filter and definition.subject_kind != kind_filter:
            continue
        if subject_filter and definition.subject != subject_filter:
            continue
        rows.append(definition.to_dict())
    rows.sort(key=lambda item: (item["subject_kind"], item["subject"], item["name"]))
    return rows


def _manifest_environment(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("environment")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("invalid_environment_manifest")
    return raw


def sync_environment_definitions_from_runtime() -> None:
    store = _definition_store()
    store.clear()

    ctx = app_ctx()
    modules = getattr(ctx, "modules", None)
    if modules is not None and hasattr(modules, "get_all_modules"):
        for module in modules.get_all_modules():
            register_environment_definitions(
                subject_kind=ENVIRONMENT_SUBJECT_MODULE,
                subject=module.name,
                definitions=_manifest_environment(module._manifest),
            )

    from democrai.core.application.ai.engine.manifests import list_engine_manifests
    from democrai.core.application.knowledge.extractor.manifests import list_extractor_manifests

    for manifest in list_engine_manifests():
        register_environment_definitions(
            subject_kind=ENVIRONMENT_SUBJECT_ENGINE,
            subject=manifest["id"],
            definitions=_manifest_environment(manifest),
        )

    for manifest in list_extractor_manifests():
        register_environment_definitions(
            subject_kind=ENVIRONMENT_SUBJECT_EXTRACTOR,
            subject=manifest["id"],
            definitions=_manifest_environment(manifest),
        )
