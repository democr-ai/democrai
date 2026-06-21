from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException
from democrai.core.platform.utils.mime_detection import extension_for_mime_type
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import (
    cache_dir,
    fs_exists,
    fs_path,
    fs_read_text,
    fs_stat,
    fs_unlink,
    fs_write_text,
)

DEFAULT_MEDIA_CACHE_TTL_SECONDS = 3600


def media_cache_root() -> Path:
    root = cache_dir() / "media_proxy"
    os.makedirs(fs_path(root), exist_ok=True)
    return root


def media_cache_key(module_name: str, url: str) -> str:
    return hashlib.sha256(f"{module_name}:{url}".encode("utf-8")).hexdigest()


def media_cache_module_dir(module_name: str) -> Path:
    module_dir = media_cache_root() / module_name
    os.makedirs(fs_path(module_dir), exist_ok=True)
    return module_dir


def media_cache_path(
    module_name: str, url: str, content_type: str | None = None
) -> Path:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    if not suffix and content_type:
        suffix = extension_for_mime_type(content_type)
    digest = media_cache_key(module_name, url)
    module_dir = media_cache_module_dir(module_name)
    return module_dir / f"{digest}{suffix}"


def media_cache_metadata_path(module_name: str, url: str) -> Path:
    return (
        media_cache_module_dir(module_name)
        / f"{media_cache_key(module_name, url)}.meta.json"
    )


def media_cache_ttl_seconds() -> int:
    raw = app_ctx().config.get("storage.media.remote_cache.ttl_seconds")
    if raw is None:
        return DEFAULT_MEDIA_CACHE_TTL_SECONDS
    try:
        ttl = int(raw)
    except Exception:
        return DEFAULT_MEDIA_CACHE_TTL_SECONDS
    return max(ttl, 1)


def is_cache_entry_fresh(
    path: Path, ttl_seconds: int, *, now: float | None = None
) -> bool:
    if ttl_seconds <= 0 or not fs_exists(path):
        return False
    current_time = time.time() if now is None else float(now)
    return (current_time - fs_stat(path).st_mtime) < float(ttl_seconds)


def prune_media_cache(
    module_name: str, ttl_seconds: int, *, now: float | None = None
) -> None:
    module_dir = media_cache_module_dir(module_name)
    current_time = time.time() if now is None else float(now)
    for candidate in module_dir.iterdir():
        try:
            is_stale = (current_time - fs_stat(candidate).st_mtime) >= float(ttl_seconds)
        except FileNotFoundError:
            continue
        if not is_stale:
            continue
        try:
            fs_unlink(candidate)
        except FileNotFoundError:
            continue


def read_media_cache_metadata(module_name: str, url: str) -> dict[str, object] | None:
    metadata_path = media_cache_metadata_path(module_name, url)
    if not fs_exists(metadata_path):
        return None
    try:
        return json.loads(fs_read_text(metadata_path, encoding="utf-8"))
    except Exception:
        return None


def write_media_cache_metadata(
    module_name: str, url: str, payload: dict[str, object]
) -> None:
    metadata_path = media_cache_metadata_path(module_name, url)
    fs_write_text(metadata_path, json.dumps(payload, sort_keys=True), encoding="utf-8")


def cached_media_payload(
    module_name: str, url: str, *, ttl_seconds: int, now: float | None = None
) -> dict[str, str] | None:
    metadata = read_media_cache_metadata(module_name, url)
    if not metadata:
        return None
    path_value = metadata.get("path") or ""
    if not path_value:
        return None
    cache_path = Path(path_value)
    if not is_cache_entry_fresh(cache_path, ttl_seconds, now=now):
        return None
    expires_at = fs_stat(cache_path).st_mtime + float(ttl_seconds)
    return {
        "path": str(cache_path),
        "content_type": metadata.get("content_type") or "application/octet-stream",
        "url": url,
        "module_name": module_name,
        "cache_hit": "true",
        "cache_expires_at": str(int(expires_at)),
    }


def safe_join_under(base_dir: str, relative_path: str) -> str:
    base_real = os.path.realpath(base_dir)
    target_real = os.path.realpath(os.path.join(base_real, relative_path))
    if target_real != base_real and not target_real.startswith(base_real + os.sep):
        raise HTTPException(status_code=400, detail="Invalid file path")
    return target_real


def safe_upload_name(filename: str) -> str:
    base = os.path.basename(str(filename or "").strip())
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return sanitized or "document.txt"
