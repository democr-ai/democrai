from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from democrai.core.runtime.foundation.paths import get_runtime_module_dirs


MEDIA_COMPONENT_FIELDS: dict[str, tuple[str, ...]] = {
    "Image": ("url",),
    "Video": ("source", "poster"),
    "Audio": ("source", "poster"),
    "PdfViewer": ("source_path", "url"),
}

_DIRECT_MEDIA_PREFIXES = (
    "/media/proxy?",
    "/media/modules/",
    "/media/engine/",
    "/media/extractors/",
    "/media/uploads/",
    "data:",
)
_DIRECT_MEDIA_TOKENS = ("ric.", "<svg")


def media_fields_for_component(component_type: str) -> tuple[str, ...]:
    resolved_type = component_type.strip() if isinstance(component_type, str) else ""
    return MEDIA_COMPONENT_FIELDS.get(resolved_type, ())


def resolve_client_media_source(
    *,
    module_name: str,
    value: str,
    module_path: str | None = None,
) -> str:
    raw = value.strip() if isinstance(value, str) else ""
    if not raw:
        return ""

    for resolver in (
        _resolve_passthrough_source,
        lambda item: _resolve_remote_source(module_name=module_name, value=item),
        _resolve_media_storage_source,
        _resolve_engine_asset_source,
        _resolve_extractor_asset_source,
        lambda item: _resolve_module_asset_source(
            module_name=module_name,
            value=item,
            module_path=module_path,
        ),
    ):
        resolved = resolver(raw)
        if resolved is not None:
            return resolved
    return raw


def rewrite_builder_media_sources(
    builder: Any,
    *,
    module_name: str,
    module_path: str | None = None,
) -> None:
    for component in getattr(builder, "_components", []):
        raw_component_type = getattr(component, "type", None)
        component_type = raw_component_type if isinstance(raw_component_type, str) else ""
        fields = media_fields_for_component(component_type)
        if not fields:
            continue
        props = getattr(component, "props", None)
        if not isinstance(props, dict):
            continue
        for field_name in fields:
            if field_name not in props:
                continue
            _rewrite_media_prop(
                props,
                field_name,
                module_name=module_name,
                module_path=module_path,
            )


def _rewrite_media_prop(
    props: dict[str, Any],
    field_name: str,
    *,
    module_name: str,
    module_path: str | None = None,
) -> None:
    raw_value = props.get(field_name)
    if isinstance(raw_value, dict) and "literalString" in raw_value:
        literal = raw_value.get("literalString")
        raw_value["literalString"] = resolve_client_media_source(
            module_name=module_name,
            value=literal if isinstance(literal, str) else "",
            module_path=module_path,
        )
        return
    if isinstance(raw_value, str):
        props[field_name] = resolve_client_media_source(
            module_name=module_name,
            value=raw_value,
            module_path=module_path,
        )


def _resolve_passthrough_source(value: str) -> str | None:
    if value.startswith(_DIRECT_MEDIA_PREFIXES):
        return value
    if value.startswith(_DIRECT_MEDIA_TOKENS):
        return value
    return None


def _resolve_remote_source(*, module_name: str, value: str) -> str | None:
    if "/media/proxy?" in value:
        return value
    if not value.startswith(("http://", "https://")):
        return None
    return "/media/proxy?" + urlencode({"module_name": module_name, "url": value})


def _resolve_media_storage_source(value: str) -> str | None:
    if not value.startswith("media/"):
        return None
    return "/media/uploads/by-storage-path?" + urlencode({"storage_path": value})


def _resolve_module_asset_source(
    *,
    module_name: str,
    value: str,
    module_path: str | None = None,
) -> str | None:
    relative_path = _module_relative_media_path(
        module_name=module_name,
        value=value,
        module_path=module_path,
    )
    if not relative_path:
        return None
    return f"/media/modules/{module_name}/{quote(relative_path, safe='/')}"


def _resolve_engine_asset_source(value: str) -> str | None:
    raw = value.strip() if isinstance(value, str) else ""
    if not raw:
        return None

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        parts = candidate.resolve().parts
        try:
            engine_idx = parts.index("engines")
        except ValueError:
            return None
        if len(parts) <= engine_idx + 2:
            return None
        engine_id = parts[engine_idx + 1].strip().lower()
        relative_path = "/".join(parts[engine_idx + 2 :])
        if not engine_id or not relative_path:
            return None
        return f"/media/engine/{quote(engine_id)}/{quote(relative_path, safe='/')}"

    normalized = raw.lstrip("./").replace("\\", "/")
    if not normalized.startswith("engines/"):
        return None
    parts = normalized.split("/", 2)
    if len(parts) < 3:
        return None
    _, engine_id, relative_path = parts
    if not engine_id or not relative_path:
        return None
    return f"/media/engine/{quote(engine_id.lower())}/{quote(relative_path, safe='/')}"


def _resolve_extractor_asset_source(value: str) -> str | None:
    raw = value.strip() if isinstance(value, str) else ""
    if not raw:
        return None

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        parts = candidate.resolve().parts
        try:
            extractor_idx = parts.index("extractors")
        except ValueError:
            return None
        if len(parts) <= extractor_idx + 2:
            return None
        extractor_id = parts[extractor_idx + 1].strip().lower()
        relative_path = "/".join(parts[extractor_idx + 2 :])
        if not extractor_id or not relative_path:
            return None
        return (
            f"/media/extractors/{quote(extractor_id)}/"
            f"{quote(relative_path, safe='/')}"
        )

    normalized = raw.lstrip("./").replace("\\", "/")
    if not normalized.startswith("extractors/"):
        return None
    parts = normalized.split("/", 2)
    if len(parts) < 3:
        return None
    _, extractor_id, relative_path = parts
    if not extractor_id or not relative_path:
        return None
    return (
        f"/media/extractors/{quote(extractor_id.lower())}/"
        f"{quote(relative_path, safe='/')}"
    )


def _module_relative_media_path(
    *,
    module_name: str,
    value: str,
    module_path: str | None = None,
) -> str | None:
    raw = value.strip() if isinstance(value, str) else ""
    if not raw:
        return None

    module_base = _find_module_base(module_name=module_name, module_path=module_path)
    if not module_base:
        return None

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        try:
            relative = candidate.resolve().relative_to(module_base.resolve())
            return relative.as_posix()
        except Exception:
            return None

    normalized = raw.lstrip("./").replace("\\", "/")
    if not normalized or normalized.startswith("../"):
        return None
    candidate = module_base / normalized
    if not candidate.exists() or not candidate.is_file():
        return None
    return normalized


def _find_module_base(module_name: str, module_path: str | None = None) -> Path | None:
    if isinstance(module_path, str) and module_path:
        candidate = Path(module_path).expanduser()
        if candidate.exists():
            return candidate

    normalized = module_name.strip() if isinstance(module_name, str) else ""
    if not normalized:
        return None

    for root in (Path(path) for path in get_runtime_module_dirs()):
        candidate = root / normalized
        if candidate.exists():
            return candidate
    return None
