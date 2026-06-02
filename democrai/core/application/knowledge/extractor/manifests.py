"""Manifest discovery utilities for installable knowledge extractors."""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


ExtractorManifest = dict[str, Any]


def get_extractor_roots() -> tuple[Path, ...]:
    from democrai.core.runtime.foundation.app import app_ctx
    from democrai.core.runtime.foundation.paths import get_runtime_extractor_dirs

    ctx = app_ctx()
    roots: list[Path] = []
    for raw_path in getattr(ctx, "runtime_extractor_paths", ()) or ():
        roots.append(Path(str(raw_path)))
    if not roots:
        for raw_path in get_runtime_extractor_dirs():
            roots.append(Path(raw_path))
    return tuple(roots)


def _manifest_path(extractor_dir: Path) -> Path:
    return extractor_dir / "manifest.json"


def _load_manifest(path: Path) -> ExtractorManifest | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    extractor_id = str(payload.get("id") or "").strip().lower()
    entrypoint = str(payload.get("entrypoint") or "").strip()
    file_extensions = payload.get("file_extensions")
    mime_types = payload.get("mime_types")
    if not extractor_id or not entrypoint or not isinstance(file_extensions, list):
        return None
    normalized_extensions = [
        str(item or "").strip().lower()
        for item in file_extensions
        if str(item or "").strip()
    ]
    if not normalized_extensions:
        return None
    normalized_mime_types = [
        str(item or "").strip().lower()
        for item in list(mime_types or [])
        if str(item or "").strip()
    ]
    payload["id"] = extractor_id
    payload["entrypoint"] = entrypoint
    payload["file_extensions"] = normalized_extensions
    payload["mime_types"] = normalized_mime_types
    return payload


@lru_cache(maxsize=1)
def list_extractor_manifests() -> tuple[ExtractorManifest, ...]:
    """Return every valid extractor manifest found on disk."""
    items: list[ExtractorManifest] = []
    seen_ids: set[str] = set()
    for root in get_extractor_roots():
        if not root.exists():
            continue
        for extractor_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            manifest = _load_manifest(_manifest_path(extractor_dir))
            if manifest is None:
                continue
            extractor_id = manifest["id"]
            if extractor_id in seen_ids:
                continue
            seen_ids.add(extractor_id)
            items.append(manifest)
    return tuple(items)


def get_extractor_manifest(extractor_id: str) -> ExtractorManifest | None:
    """Return the manifest for one extractor identifier, if present."""
    normalized = str(extractor_id or "").strip().lower()
    if not normalized:
        return None
    for manifest in list_extractor_manifests():
        if manifest["id"] == normalized:
            return deepcopy(manifest)
    return None


def _extractor_dir(extractor_id: str) -> Path | None:
    normalized = str(extractor_id or "").strip().lower()
    if not normalized:
        return None
    for root in get_extractor_roots():
        if not root.exists():
            continue
        for extractor_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            manifest = _load_manifest(_manifest_path(extractor_dir))
            if manifest is None:
                continue
            if manifest["id"] == normalized:
                return extractor_dir
    return None


def _enforce_sdk_boundary(extractor_id: str) -> None:
    extractor_dir = _extractor_dir(extractor_id)
    if extractor_dir is None:
        return
    from democrai.core.infrastructure.modules.loading import _collect_forbidden_core_imports

    violations = _collect_forbidden_core_imports(str(extractor_dir))
    if violations:
        preview = ", ".join(violations[:5])
        raise RuntimeError(
            "extractor_sdk_boundary_violation:"
            f" direct core imports are not allowed in extractor '{extractor_id}' ({preview})"
        )


def load_extractor_class(extractor_id: str) -> type[Any] | None:
    """Load and return the extractor class declared by a manifest."""
    manifest = get_extractor_manifest(extractor_id)
    if manifest is None:
        return None
    entrypoint = manifest["entrypoint"]
    if ":" not in entrypoint:
        return None
    module_name, class_name = entrypoint.split(":", 1)
    _enforce_sdk_boundary(extractor_id)
    module = importlib.import_module(module_name)
    loaded = getattr(module, class_name, None)
    return loaded if isinstance(loaded, type) else None


def sync_extractor_manifests_to_registry() -> None:
    """Synchronize extractor manifests into the shared runtime registry."""
    from democrai.core.infrastructure.database import SessionLocal
    from democrai.core.infrastructure.database.models import ExtractorRegistry

    manifests = list_extractor_manifests()
    if not manifests:
        return
    with SessionLocal() as session:
        existing = {
            row.extractor_id: row
            for row in session.query(ExtractorRegistry).all()
        }
        changed = False
        for manifest in manifests:
            extractor_id = manifest["id"]
            extractor_name = str(manifest.get("name") or extractor_id).strip() or extractor_id
            row = existing.get(extractor_id)
            if row is None:
                session.add(
                    ExtractorRegistry(
                        name=extractor_name,
                        extractor_id=extractor_id,
                        config={},
                        install_config={},
                        status="uninstalled",
                        supported=True,
                        file_extensions=list(manifest.get("file_extensions") or []),
                        mime_types=list(manifest.get("mime_types") or []),
                        priority=int(manifest.get("priority") or 0),
                    )
                )
                changed = True
                continue
            updated_extensions = list(manifest.get("file_extensions") or [])
            updated_mime_types = list(manifest.get("mime_types") or [])
            updated_priority = int(manifest.get("priority") or 0)
            if list(row.file_extensions or []) != updated_extensions:
                row.file_extensions = updated_extensions
                changed = True
            if list(row.mime_types or []) != updated_mime_types:
                row.mime_types = updated_mime_types
                changed = True
            if row.priority != updated_priority:
                row.priority = updated_priority
                changed = True
            if row.name != extractor_name:
                row.name = extractor_name
                changed = True
        if changed:
            session.commit()
