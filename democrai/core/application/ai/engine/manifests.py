from __future__ import annotations

import importlib
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


EngineManifest = dict[str, Any]


def get_engine_roots() -> tuple[Path, ...]:
    from democrai.core.runtime.foundation.app import app_ctx
    from democrai.core.runtime.foundation.paths import get_runtime_engine_dirs

    ctx = app_ctx()
    roots: list[Path] = []
    for runtime_engine_path in getattr(ctx, "runtime_engine_paths", ()):
        roots.append(Path(runtime_engine_path))
    if not roots:
        for raw_path in get_runtime_engine_dirs():
            roots.append(Path(raw_path))
    return tuple(roots)


def _manifest_path(engine_dir: Path) -> Path:
    return engine_dir / "manifest.json"


def _load_manifest(path: Path) -> EngineManifest | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    engine_id = payload.get("id")
    entrypoint = payload.get("entrypoint")
    provider = payload.get("provider")
    if (
        not isinstance(engine_id, str)
        or not engine_id
        or not isinstance(entrypoint, str)
        or not entrypoint
        or not isinstance(provider, dict)
    ):
        return None
    return payload


@lru_cache(maxsize=1)
def list_engine_manifests() -> tuple[EngineManifest, ...]:
    items: list[EngineManifest] = []
    seen_ids: set[str] = set()
    for root in get_engine_roots():
        if not root.exists():
            continue
        for engine_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            manifest = _load_manifest(_manifest_path(engine_dir))
            if manifest is None:
                continue
            engine_id = manifest["id"]
            if engine_id in seen_ids:
                continue
            seen_ids.add(engine_id)
            items.append(manifest)
    return tuple(items)


def get_engine_manifest(engine_id: str) -> EngineManifest | None:
    if not engine_id:
        return None
    for manifest in list_engine_manifests():
        if manifest["id"] == engine_id:
            return dict(manifest)
    return None


def _engine_dir(engine_id: str) -> Path | None:
    if not engine_id:
        return None
    for root in get_engine_roots():
        if not root.exists():
            continue
        for engine_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            manifest = _load_manifest(_manifest_path(engine_dir))
            if manifest is None:
                continue
            if manifest["id"] == engine_id:
                return engine_dir
    return None


def _enforce_sdk_boundary(engine_id: str) -> None:
    engine_dir = _engine_dir(engine_id)
    if engine_dir is None:
        return
    from democrai.core.infrastructure.modules.loading import _collect_forbidden_core_imports

    violations = _collect_forbidden_core_imports(str(engine_dir))
    if violations:
        preview = ", ".join(violations[:5])
        raise RuntimeError(
            "engine_sdk_boundary_violation:"
            f" direct core imports are not allowed in engine '{engine_id}' ({preview})"
        )


def _provider_from_manifest(manifest: dict[str, Any]) -> dict[str, Any] | None:
    provider = manifest.get("provider")
    if not isinstance(provider, dict):
        return None
    provider_id = provider.get("id")
    if not isinstance(provider_id, str) or not provider_id:
        return None
    payload = deepcopy(provider)
    return payload


def get_provider_definition(provider_id: str) -> dict[str, Any] | None:
    if not provider_id:
        return None
    for manifest in list_engine_manifests():
        provider = _provider_from_manifest(manifest)
        if provider is None:
            continue
        if provider["id"] == provider_id:
            return provider
    return None


def list_provider_definitions(*, kind: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for manifest in list_engine_manifests():
        provider = _provider_from_manifest(manifest)
        if provider is None:
            continue
        provider_id = provider["id"]
        if provider_id in seen:
            continue
        if kind and provider.get("kind") != kind:
            continue
        seen.add(provider_id)
        items.append(provider)
    return items


def load_engine_class(engine_id: str) -> type[Any] | None:
    manifest = get_engine_manifest(engine_id)
    if manifest is None:
        return None
    entrypoint = manifest["entrypoint"]
    if ":" not in entrypoint:
        return None
    module_name, class_name = entrypoint.split(":", 1)
    _enforce_sdk_boundary(engine_id)
    module = importlib.import_module(module_name)
    loaded = getattr(module, class_name, None)
    return loaded if isinstance(loaded, type) else None


def sync_engine_manifests_to_registry() -> None:
    from democrai.core.infrastructure.database import SessionLocal
    from democrai.core.infrastructure.database.models import EngineRegistry

    manifests = list_engine_manifests()
    if not manifests:
        return

    with SessionLocal() as session:
        existing = session.query(EngineRegistry).all()
        changed = False
        for manifest in manifests:
            engine_id = manifest["id"]

            exist = [row for row in existing if row.provider == engine_id]
            if len(exist) > 0:
                continue

            # supported = exist[0].status != "unsupported"

            engine_name = manifest.get("name") or engine_id

            if not manifest.get("provider", {}).get("configurable", False):
                session.add(
                    EngineRegistry(
                        name=engine_name,
                        provider=engine_id,
                        config={},
                        status="uninstalled",
                        supported=True,
                    )
                )
                changed = True
        if changed:
            session.commit()
