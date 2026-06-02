"""MIME type binding helpers for knowledge extractors."""

from __future__ import annotations

from typing import Any

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    ExtractorMimeTypeBinding,
    ExtractorRegistry,
)


ACTIVE_EXTRACTOR_STATUSES = {"active", "installed"}


def normalize_mime_type(value: str | None) -> str:
    return str(value or "").strip().lower()


def normalize_extractor_id(value: str | None) -> str:
    return str(value or "").strip().lower()


def _row_mime_types(row: ExtractorRegistry) -> list[str]:
    return [
        normalize_mime_type(item)
        for item in list(row.mime_types or [])
        if normalize_mime_type(item)
    ]


def _row_status(row: ExtractorRegistry) -> str:
    return row.status


def _serialize_registry_row(row: ExtractorRegistry) -> dict[str, Any]:
    return {
        "row_id": row.id,
        "name": row.name,
        "extractor_id": row.extractor_id,
        "config": row.config,
        "install_config": row.install_config,
        "status": _row_status(row),
        "priority": row.priority,
        "file_extensions": [
            str(item or "").strip().lower()
            for item in list(row.file_extensions or [])
            if str(item or "").strip()
        ],
        "mime_types": _row_mime_types(row),
    }


def _compatible_rows(
    rows: list[ExtractorRegistry],
    *,
    mime_type: str,
    installed_only: bool,
) -> list[ExtractorRegistry]:
    compatible: list[ExtractorRegistry] = []
    for row in rows:
        if not row.extractor_id:
            continue
        if mime_type not in _row_mime_types(row):
            continue
        if installed_only and _row_status(row) not in ACTIVE_EXTRACTOR_STATUSES:
            continue
        compatible.append(row)
    compatible.sort(
        key=lambda item: (
            item.name,
            item.extractor_id,
        )
    )
    return compatible


def _binding_map(bindings: list[ExtractorMimeTypeBinding]) -> dict[str, str]:
    return {
        normalize_mime_type(row.mime_type): row.extractor_id
        for row in bindings
        if normalize_mime_type(row.mime_type) and row.extractor_id
    }


def list_configurable_mime_bindings() -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.query(ExtractorRegistry).all()
        bindings = session.query(ExtractorMimeTypeBinding).all()

    configured = _binding_map(bindings)
    mime_types = sorted(
        {
            mime_type
            for row in rows
            for mime_type in _row_mime_types(row)
            if mime_type
        }
    )

    result: list[dict[str, Any]] = []
    for mime_type in mime_types:
        options = [
            {
                "label": row.name,
                "value": row.extractor_id,
            }
            for row in _compatible_rows(rows, mime_type=mime_type, installed_only=True)
        ]
        configured_extractor_id = configured.get(mime_type, "")
        if configured_extractor_id and not any(
            option["value"] == configured_extractor_id for option in options
        ):
            configured_extractor_id = ""
        result.append(
            {
                "id": mime_type,
                "mime_type": mime_type,
                "configured_extractor_id": configured_extractor_id,
                "extractor_options": [{"label": "Not configured", "value": ""}, *options],
                "configured": bool(configured_extractor_id),
            }
        )
    return result


def list_ingestible_mime_types() -> list[str]:
    return [
        str(row["mime_type"])
        for row in list_configurable_mime_bindings()
        if row.get("configured")
    ]


def set_mime_type_binding(*, mime_type: str, extractor_id: str | None) -> dict[str, Any] | None:
    normalized_mime_type = normalize_mime_type(mime_type)
    normalized_extractor_id = normalize_extractor_id(extractor_id)
    if not normalized_mime_type:
        raise ValueError("mime_type_required")

    with SessionLocal() as session:
        binding = (
            session.query(ExtractorMimeTypeBinding)
            .filter(ExtractorMimeTypeBinding.mime_type == normalized_mime_type)
            .first()
        )
        if not normalized_extractor_id:
            if binding is not None:
                session.delete(binding)
                session.commit()
            return None

        extractor = (
            session.query(ExtractorRegistry)
            .filter(ExtractorRegistry.extractor_id == normalized_extractor_id)
            .first()
        )
        if extractor is None:
            raise ValueError("extractor_not_found")
        if _row_status(extractor) not in ACTIVE_EXTRACTOR_STATUSES:
            raise ValueError("extractor_not_installed")
        if normalized_mime_type not in _row_mime_types(extractor):
            raise ValueError("extractor_mime_type_not_supported")

        if binding is None:
            binding = ExtractorMimeTypeBinding(
                mime_type=normalized_mime_type,
                extractor_id=normalized_extractor_id,
            )
            session.add(binding)
        else:
            binding.extractor_id = normalized_extractor_id
        session.commit()
        session.refresh(binding)
        return {
            "id": binding.id,
            "mime_type": binding.mime_type,
            "extractor_id": binding.extractor_id,
        }


def resolve_bound_extractor(*, mime_type: str | None) -> dict[str, Any] | None:
    normalized_mime_type = normalize_mime_type(mime_type)
    if not normalized_mime_type:
        return None

    with SessionLocal() as session:
        binding = (
            session.query(ExtractorMimeTypeBinding)
            .filter(ExtractorMimeTypeBinding.mime_type == normalized_mime_type)
            .first()
        )
        if binding is None:
            return None
        row = (
            session.query(ExtractorRegistry)
            .filter(ExtractorRegistry.extractor_id == binding.extractor_id)
            .first()
        )
        if row is None:
            return None
        if _row_status(row) not in ACTIVE_EXTRACTOR_STATUSES:
            return None
        if normalized_mime_type not in _row_mime_types(row):
            return None
        payload = _serialize_registry_row(row)
        payload["mime_match"] = True
        payload["extension_match"] = False
        return payload
