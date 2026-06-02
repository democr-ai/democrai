"""Resolver helpers for selecting the active external knowledge extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from democrai.core.application.knowledge.extractor.bindings import (
    ACTIVE_EXTRACTOR_STATUSES,
)
from democrai.core.application.knowledge.extractor.bindings import resolve_bound_extractor
from democrai.core.application.knowledge.extractor.runtime import extract_with_runtime
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import ExtractorRegistry


def resolve_active_extractor_for_path(path: str | Path) -> dict[str, Any] | None:
    return resolve_active_extractor(path=path)


def resolve_active_extractor(
    *,
    path: str | Path | None = None,
    mime_type: str | None = None,
    filename: str | None = None,
) -> dict[str, Any] | None:
    """Return the extractor explicitly bound to the source MIME type."""
    normalized_mime_type = str(mime_type or "").strip().lower()
    if not normalized_mime_type:
        return None
    return resolve_bound_extractor(mime_type=normalized_mime_type)


def extract_with_active_extractor(
    *,
    path: str | Path | None = None,
    data: bytes | None = None,
    filename: str | None = None,
    mime_type: str | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run the active external extractor for the given path when available."""
    if path is None and data is None:
        raise ValueError("path or data is required")
    resolved = resolve_active_extractor(
        path=path,
        filename=filename,
        mime_type=mime_type,
    )
    if resolved is None:
        return None
    files: list[Any] = []
    if path is not None:
        files.append(path)
    else:
        files.append(
            {
                "bytes": bytes(data or b""),
                "name": str(filename or "inline.bin"),
                "source": str(filename or "inline-bytes"),
                "mime_type": str(mime_type or "").strip() or None,
            }
        )
    config = dict(resolved.get("install_config") or {})
    config.update(dict(resolved.get("config") or {}))
    if config_overrides is not None:
        config.update(config_overrides)
    payload = extract_with_runtime(
        extractor_row_id=resolved["row_id"],
        extractor_id=resolved["extractor_id"],
        config=config,
        files=files,
    )
    payload["resolved_extractor"] = resolved
    return payload


def extract_with_registered_extractor(
    *,
    extractor_id: str,
    path: str | Path | None = None,
    data: bytes | None = None,
    filename: str | None = None,
    mime_type: str | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run one installed extractor directly, bypassing MIME binding resolution."""
    if path is None and data is None:
        raise ValueError("path or data is required")
    if not extractor_id:
        raise ValueError("extractor_id is required")
    resolved = _registered_extractor_payload(extractor_id)
    if resolved is None:
        return None
    files: list[Any] = []
    if path is not None:
        files.append(path)
    else:
        files.append(
            {
                "bytes": bytes(data or b""),
                "name": str(filename or "inline.bin"),
                "source": str(filename or "inline-bytes"),
                "mime_type": str(mime_type or "").strip() or None,
            }
        )
    config = dict(resolved.get("install_config") or {})
    config.update(dict(resolved.get("config") or {}))
    if config_overrides is not None:
        config.update(config_overrides)
    payload = extract_with_runtime(
        extractor_row_id=resolved["row_id"],
        extractor_id=resolved["extractor_id"],
        config=config,
        files=files,
    )
    payload["resolved_extractor"] = resolved
    return payload


def _registered_extractor_payload(extractor_id: str) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = (
            session.query(ExtractorRegistry)
            .filter(ExtractorRegistry.extractor_id == extractor_id)
            .first()
        )
        if row is None:
            return None
        if row.status not in ACTIVE_EXTRACTOR_STATUSES:
            return None
        return {
            "row_id": row.id,
            "name": row.name,
            "extractor_id": row.extractor_id,
            "config": row.config,
            "install_config": row.install_config,
            "status": row.status,
            "priority": row.priority,
            "file_extensions": [
                str(item or "").strip().lower()
                for item in list(row.file_extensions or [])
                if str(item or "").strip()
            ],
            "mime_types": [
                str(item or "").strip().lower()
                for item in list(row.mime_types or [])
                if str(item or "").strip()
            ],
        }
