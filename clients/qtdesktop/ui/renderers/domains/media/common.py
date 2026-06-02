from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.parse import urlparse

from PySide6.QtGui import QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget

from .....utils.paths import resolve_resource
from .http import fetch_media_bytes


def _literal(value: Any, fallback: str = "") -> str:
    if isinstance(value, dict) and "literalString" in value:
        return str(value.get("literalString") or "")
    if value is None:
        return fallback
    return str(value)


def _int_value(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _as_media_url(source: str) -> QUrl:
    localized = localize_runtime_media_source(source)
    resolved = localized if localized is not None else resolve_resource(source)
    if resolved.startswith(("http://", "https://")):
        return QUrl(resolved)
    return QUrl.fromLocalFile(resolved)


def _load_internal_media_bytes(source: str, app_instance: Any) -> bytes:
    return fetch_media_bytes(app_instance, source, timeout=15.0)


def _decode_data_image_url(raw: str) -> bytes:
    source = str(raw or "").strip()
    if not source.startswith("data:image/"):
        return b""
    marker = ";base64,"
    idx = source.find(marker)
    if idx < 0:
        return b""
    encoded = source[idx + len(marker) :].strip()
    if not encoded:
        return b""
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception:
        return b""


def load_runtime_image_pixmap(source: str, app_instance: Any) -> QPixmap:
    normalized = resolve_runtime_media_source(str(source or ""), app_instance)
    internal_payload = _load_internal_media_bytes(normalized, app_instance)
    if not internal_payload:
        internal_payload = _decode_data_image_url(normalized)
    if internal_payload:
        pixmap = QPixmap()
        if pixmap.loadFromData(internal_payload):
            return pixmap
        return QPixmap()

    parsed = urlparse(normalized)
    is_remote = parsed.scheme in {"http", "https"}
    localized = localize_runtime_media_source(normalized)
    resolved = normalized if is_remote else (localized or resolve_resource(normalized))
    return QPixmap(resolved)


def _get_current_path(app_instance: Any) -> str:
    store = getattr(app_instance, "store", None)
    if store is not None and hasattr(store, "get"):
        try:
            return str(store.get("/current_path", "/", "global") or "/")
        except Exception:
            return "/"
    return "/"


def _get_current_module_name(app_instance: Any) -> str:
    current_path = _get_current_path(app_instance).strip()
    if not current_path.startswith("/"):
        return ""
    parts = [part for part in current_path.split("/") if part]
    if not parts:
        return ""
    return str(parts[0] or "").strip()


def _current_or_default_module_name(app_instance: Any) -> str:
    return _get_current_module_name(app_instance) or "dashboard"


def _media_proxy_path(module_name: str, target: str) -> str:
    return "/media/proxy?" + urlencode(
        {"module_name": module_name or "dashboard", "url": target}
    )


def _is_proxy_media_source(source: str) -> bool:
    parsed = urlparse(str(source or ""))
    return source.startswith("/media/proxy") or (
        parsed.scheme in {"http", "https"} and parsed.path == "/media/proxy"
    )


def _target_from_media_url(source: str) -> str:
    parsed = urlparse(str(source or "").strip())
    if parsed.scheme in {"http", "https"} and parsed.path.startswith("/media/"):
        target = parsed.path
        if parsed.query:
            target = f"{target}?{parsed.query}"
        return target
    return str(source or "").strip()


def _resolve_engine_asset_source(source: str, app_instance: Any) -> str | None:
    raw = str(source or "").strip()
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
        engine_id = str(parts[engine_idx + 1] or "").strip()
        relative = "/".join(str(part) for part in parts[engine_idx + 2 :])
        return _media_proxy_path(
            _current_or_default_module_name(app_instance),
            f"/media/engine/{engine_id}/{relative}",
        )

    normalized = raw.lstrip("./").replace("\\", "/")
    if not normalized.startswith("engines/"):
        return None
    parts = normalized.split("/", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return None
    return _media_proxy_path(
        _current_or_default_module_name(app_instance),
        f"/media/engine/{parts[1]}/{parts[2]}",
    )


def _resolve_extractor_asset_source(source: str, app_instance: Any) -> str | None:
    raw = str(source or "").strip()
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
        extractor_id = str(parts[extractor_idx + 1] or "").strip()
        relative = "/".join(str(part) for part in parts[extractor_idx + 2 :])
        return _media_proxy_path(
            _current_or_default_module_name(app_instance),
            f"/media/extractors/{extractor_id}/{relative}",
        )

    normalized = raw.lstrip("./").replace("\\", "/")
    if not normalized.startswith("extractors/"):
        return None
    parts = normalized.split("/", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return None
    return _media_proxy_path(
        _current_or_default_module_name(app_instance),
        f"/media/extractors/{parts[1]}/{parts[2]}",
    )


def _resolve_explicit_module_asset_source(
    source: str, app_instance: Any
) -> str | None:
    raw = str(source or "").strip()
    if not raw:
        return None

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        parts = candidate.resolve().parts
        try:
            modules_idx = parts.index("modules")
        except ValueError:
            return None
        if len(parts) <= modules_idx + 2:
            return None
        module_name = str(parts[modules_idx + 1] or "").strip()
        relative = "/".join(str(part) for part in parts[modules_idx + 2 :])
        if not module_name:
            return None
        return _media_proxy_path(
            _current_or_default_module_name(app_instance),
            f"/media/modules/{module_name}/{relative}",
        )

    normalized = raw.lstrip("./").replace("\\", "/")
    if normalized.startswith("modules/"):
        parts = normalized.split("/", 2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            return None
        return _media_proxy_path(
            _current_or_default_module_name(app_instance),
            f"/media/modules/{parts[1]}/{parts[2]}",
        )

    parts = normalized.split("/", 1)
    if len(parts) != 2:
        return None
    module_name, relative = parts
    if not module_name or module_name in {
        "assets",
        "ui",
        "media",
        "static",
        "resources",
        "desktop",
        "engines",
        "extractors",
    }:
        return None
    return _media_proxy_path(
        _current_or_default_module_name(app_instance),
        f"/media/modules/{module_name}/{relative}",
    )


def _resolve_implicit_module_asset_source(source: str, app_instance: Any) -> str | None:
    raw = str(source or "").strip()
    if not raw:
        return None
    normalized = raw.lstrip("./").replace("\\", "/")
    if not normalized.startswith(("ui/", "static/", "resources/")):
        return None
    module_name = _current_or_default_module_name(app_instance)
    return _media_proxy_path(module_name, f"/media/modules/{module_name}/{normalized}")


def _resolve_client_asset_source(source: str) -> str | None:
    raw = str(source or "").strip()
    if not raw:
        return None

    from .....utils.paths import get_assets_dir

    desktop_assets_dir = Path(get_assets_dir())
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        try:
            relative = candidate.resolve().relative_to(desktop_assets_dir.resolve())
        except Exception:
            return None
        resolved = desktop_assets_dir / relative
        if resolved.exists() and resolved.is_file():
            return str(resolved)
        return None

    normalized = raw.lstrip("./").replace("\\", "/")
    if normalized.startswith("clients/qtdesktop/assets/"):
        normalized = normalized[len("clients/qtdesktop/assets/") :]
    elif normalized.startswith("assets/"):
        normalized = normalized[len("assets/") :]
    else:
        return None
    if not normalized or normalized.startswith("../"):
        return None
    resolved = desktop_assets_dir / normalized
    return str(resolved)


def _resolve_upload_storage_path_source(source: str, app_instance: Any) -> str | None:
    normalized = str(source or "").strip().replace("\\", "/")
    if not normalized.startswith("media/"):
        return None
    return _media_proxy_path(
        _current_or_default_module_name(app_instance),
        "/media/uploads/by-storage-path?" + urlencode({"storage_path": normalized}),
    )


def resolve_runtime_media_source(source: str, app_instance: Any) -> str:
    value = str(source or "").strip()
    if not value:
        return ""
    if value.startswith(("data:", "blob:")):
        return value
    if value.startswith(("ric.", "<svg")):
        return value
    if _is_proxy_media_source(value):
        return value

    module_name = _current_or_default_module_name(app_instance)
    parsed = urlparse(value)
    if value.startswith("/media/") or (
        parsed.scheme in {"http", "https"} and parsed.path.startswith("/media/")
    ):
        return _media_proxy_path(module_name, _target_from_media_url(value))
    if parsed.scheme in {"http", "https"}:
        return _media_proxy_path(module_name, value)

    for resolver in (
        _resolve_client_asset_source,
        lambda item: _resolve_upload_storage_path_source(item, app_instance),
        lambda item: _resolve_engine_asset_source(item, app_instance),
        lambda item: _resolve_extractor_asset_source(item, app_instance),
        lambda item: _resolve_explicit_module_asset_source(item, app_instance),
        lambda item: _resolve_implicit_module_asset_source(item, app_instance),
    ):
        resolved = resolver(value)
        if resolved is not None:
            return resolved
    return value


def localize_runtime_media_source(source: str) -> str | None:
    return None


def _is_local_runtime_media_source(source: str) -> bool:
    if localize_runtime_media_source(source) is not None:
        return True
    resolved = str(resolve_resource(source) or "")
    if resolved.startswith("/media/"):
        return True
    parsed = urlparse(resolved)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.path.startswith("/media/")
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    )


def _is_remote_media_source(source: str) -> bool:
    resolved = resolve_resource(source)
    return resolved.startswith(("http://", "https://"))


def _is_internal_proxy_source(source: str) -> bool:
    resolved = str(resolve_resource(source) or "")
    if resolved.startswith("/media/proxy"):
        return True
    parsed = urlparse(resolved)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.path == "/media/proxy"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    )


def _is_allowed_media_source(source: str) -> bool:
    return bool(source) and (
        _is_internal_proxy_source(source)
        or _is_local_runtime_media_source(source)
        or not _is_remote_media_source(source)
    )


def _normalize_media_source(source: str, app_instance: Any) -> str:
    value = resolve_runtime_media_source(source, app_instance)
    if not value.startswith("/media/"):
        return value
    host = str(getattr(app_instance, "host", "127.0.0.1") or "127.0.0.1")
    port = int(getattr(app_instance, "port", 8000) or 8000)
    return f"http://{host}:{port}{value}"


def _build_local_proxy_base_url(app_instance: Any) -> str:
    host = str(getattr(app_instance, "host", "127.0.0.1") or "127.0.0.1")
    port = int(getattr(app_instance, "port", 8000) or 8000)
    return f"http://{host}:{port}"


def _apply_explicit_size(widget: QWidget, width: int, height: int) -> None:
    if width > 0:
        widget.setMinimumWidth(width)
        widget.setMaximumWidth(width)
    if height > 0:
        widget.setMinimumHeight(height)
        widget.setMaximumHeight(height)


def _construct_qt_object(factory: Any, parent: QWidget | None = None) -> Any:
    try:
        return factory(parent) if parent is not None else factory()
    except TypeError:
        instance = factory()
        if parent is not None and hasattr(instance, "setParent"):
            try:
                instance.setParent(parent)
            except Exception:
                pass
        return instance
