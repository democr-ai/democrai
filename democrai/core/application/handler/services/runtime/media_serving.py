from __future__ import annotations

import base64
import io
import mimetypes
import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps
from democrai.core.application.auth.service import is_valid_module_name
from democrai.core.platform.utils.runtime_names import is_valid_runtime_asset_owner
from democrai.core.application.handler.services.runtime.cache import (
    media_cache_root,
    safe_join_under,
)
from democrai.core.application.handler.services.runtime.media_authorization import (
    authorize_media_target,
)
from democrai.core.application.handler.services.runtime.media_targets import MediaTarget
from democrai.core.runtime.foundation.app import req_ctx
from democrai.core.runtime.foundation.paths import (
    get_runtime_engine_dirs,
    get_runtime_extractor_dirs,
    get_runtime_module_dirs,
)

ALLOWED_MEDIA_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".bmp",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".ogg",
    ".flac",
    ".mp4",
    ".webm",
    ".mov",
    ".avi",
    ".mkv",
}
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".xls",
    ".xlsx",
    ".eml",
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".html",
    ".htm",
}
RESIZABLE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico"}
MAX_RESIZE_DIMENSION = 4096


async def serve_media_target(
    target: MediaTarget,
    *,
    width: int | None = None,
    height: int | None = None,
):
    if target.kind == "upload_storage_path":
        return await serve_uploaded_media_by_storage_path(
            storage_path=target.storage_path,
            download=False,
        )
    if target.kind == "upload_file_id":
        return await serve_uploaded_media(
            file_id=target.file_id,
            download=False,
        )
    if target.kind == "module_asset":
        return await serve_module_media(
            module_name=target.owner_name,
            file_path=target.relative_path,
            width=width,
            height=height,
        )
    if target.kind == "engine_asset":
        return await serve_engine_media(
            engine_id=target.owner_name,
            file_path=target.relative_path,
            width=width,
            height=height,
        )
    if target.kind == "extractor_asset":
        return await serve_extractor_media(
            extractor_id=target.owner_name,
            file_path=target.relative_path,
            width=width,
            height=height,
        )
    raise HTTPException(status_code=400, detail="Unsupported internal media target")


def _resize_dimensions(width: int | None, height: int | None) -> tuple[int, int]:
    try:
        normalized_width = int(width or 0)
    except (TypeError, ValueError):
        normalized_width = 0
    try:
        normalized_height = int(height or 0)
    except (TypeError, ValueError):
        normalized_height = 0
    if normalized_width < 0 or normalized_height < 0:
        raise HTTPException(status_code=400, detail="Invalid resize dimensions")
    if (
        normalized_width > MAX_RESIZE_DIMENSION
        or normalized_height > MAX_RESIZE_DIMENSION
    ):
        raise HTTPException(status_code=400, detail="Invalid resize dimensions")
    return normalized_width, normalized_height


def _asset_resize_cache_path(
    *,
    target: MediaTarget,
    source_path: str,
    width: int,
    height: int,
) -> Path:
    relative_path = target.relative_path.replace("\\", "/")
    canonical = f"{target.owner_name}/{relative_path}"
    query_parts = []
    if width > 0:
        query_parts.append(f"width={width}")
    if height > 0:
        query_parts.append(f"height={height}")
    if query_parts:
        canonical = f"{canonical}?{'&'.join(query_parts)}"
    key = (
        base64.urlsafe_b64encode(canonical.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    suffix = Path(source_path).suffix.lower() or ".png"
    cache_dir = (
        media_cache_root()
        / "resized_assets"
        / target.kind
        / target.owner_name
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}{suffix}"


def _save_resized_asset(
    *,
    source_path: str,
    cache_path: Path,
    width: int,
    height: int,
) -> None:
    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        if width > 0 and height > 0:
            resized = ImageOps.fit(
                image,
                (width, height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
        else:
            source_width, source_height = image.size
            if width > 0:
                target_height = max(1, round(source_height * (width / source_width)))
                resized = image.resize((width, target_height), Image.Resampling.LANCZOS)
            else:
                target_width = max(1, round(source_width * (height / source_height)))
                resized = image.resize((target_width, height), Image.Resampling.LANCZOS)

        suffix = cache_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"} and resized.mode in {"RGBA", "LA", "P"}:
            resized = resized.convert("RGB")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        resized.save(
            buffer,
            format=(Image.registered_extensions().get(suffix) or "PNG"),
        )
        cache_path.write_bytes(buffer.getvalue())


def _serve_resized_asset(
    *,
    target: MediaTarget,
    source_path: str,
    width: int,
    height: int,
):
    cache_path = _asset_resize_cache_path(
        target=target,
        source_path=source_path,
        width=width,
        height=height,
    )
    try:
        cache_stat = cache_path.stat()
        source_stat = os.stat(source_path)
        cache_fresh = cache_stat.st_mtime >= source_stat.st_mtime
    except FileNotFoundError:
        cache_fresh = False
    if not cache_fresh:
        try:
            _save_resized_asset(
                source_path=source_path,
                cache_path=cache_path,
                width=width,
                height=height,
            )
        except OSError:
            raise HTTPException(status_code=400, detail="Image resize failed")

    media_type = mimetypes.guess_type(str(cache_path))[0] or "application/octet-stream"
    return FileResponse(
        path=str(cache_path),
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Vary": "Authorization, Cookie, X-JWT",
        },
    )


def _serve_scoped_file(
    *,
    base_dir: str | Path,
    file_path: str,
    target: MediaTarget | None = None,
    width: int | None = None,
    height: int | None = None,
):
    if ".." in file_path or file_path.startswith("/") or file_path.startswith("\\"):
        raise HTTPException(status_code=400, detail="Invalid file path")
    _, ext = os.path.splitext(file_path)
    allowed_extensions = set(ALLOWED_MEDIA_EXTENSIONS)
    allowed_extensions.update(ALLOWED_DOCUMENT_EXTENSIONS)
    if ext.lower() not in allowed_extensions:
        raise HTTPException(status_code=403, detail="Unsupported media type")

    target_path = safe_join_under(str(base_dir), file_path)

    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="Media file not found")

    resize_width, resize_height = _resize_dimensions(width, height)
    asset_path = file_path.strip().replace("\\", "/").lstrip("/")
    _, ext = os.path.splitext(file_path)
    if (
        target is not None
        and (resize_width > 0 or resize_height > 0)
        and ext.lower() in RESIZABLE_IMAGE_EXTENSIONS
        and not asset_path.startswith("protected/")
    ):
        return _serve_resized_asset(
            target=target,
            source_path=target_path,
            width=resize_width,
            height=resize_height,
        )

    return FileResponse(
        path=target_path,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Vary": "Authorization, Cookie, X-JWT",
        },
    )


def media_asset_base_path(target: MediaTarget) -> Path:
    owner_name = target.owner_name
    if target.kind == "module_asset":
        for root in get_runtime_module_dirs():
            module_dir = Path(root) / owner_name
            if module_dir.exists() and module_dir.is_dir():
                return module_dir / "assets"
        raise HTTPException(status_code=404, detail="Module not found")

    if target.kind == "engine_asset":
        for root in get_runtime_engine_dirs():
            engine_base = Path(root) / owner_name
            if engine_base.exists() and engine_base.is_dir():
                return engine_base / "assets"
        raise HTTPException(status_code=404, detail="Engine not found")

    if target.kind == "extractor_asset":
        for root in get_runtime_extractor_dirs():
            extractor_base = Path(root) / owner_name
            if extractor_base.exists() and extractor_base.is_dir():
                return extractor_base / "assets"
        raise HTTPException(status_code=404, detail="Extractor not found")

    raise HTTPException(status_code=400, detail="Unsupported asset target")


async def serve_module_media(
    module_name: str,
    file_path: str,
    *,
    width: int | None = None,
    height: int | None = None,
):
    if not is_valid_module_name(module_name):
        raise HTTPException(status_code=400, detail="Invalid module name")
    normalized_path = file_path.strip().replace("\\", "/").lstrip("/")
    if not normalized_path.startswith("assets/"):
        raise HTTPException(status_code=403, detail="Module media must live under assets/")
    asset_relative_path = normalized_path[len("assets/") :].strip().lstrip("/")
    if not asset_relative_path:
        raise HTTPException(status_code=404, detail="Media file not found")
    target = MediaTarget(
        kind="module_asset",
        requester_module=module_name,
        raw_url=f"/media/modules/{module_name}/{normalized_path}",
        owner_name=module_name,
        relative_path=normalized_path,
    )
    authorize_media_target(target)

    return _serve_scoped_file(
        base_dir=media_asset_base_path(target),
        file_path=asset_relative_path,
        target=target,
        width=width,
        height=height,
    )


async def serve_engine_media(
    engine_id: str,
    file_path: str,
    *,
    width: int | None = None,
    height: int | None = None,
):
    normalized_engine = engine_id
    if not is_valid_runtime_asset_owner(normalized_engine):
        raise HTTPException(status_code=400, detail="Invalid engine id")
    normalized_path = file_path.strip().replace("\\", "/").lstrip("/")
    if not normalized_path.startswith("assets/"):
        raise HTTPException(status_code=403, detail="Engine media must live under assets/")
    asset_relative_path = normalized_path[len("assets/") :].strip().lstrip("/")
    if not asset_relative_path:
        raise HTTPException(status_code=404, detail="Media file not found")
    target = MediaTarget(
        kind="engine_asset",
        requester_module=normalized_engine,
        raw_url=f"/media/engine/{normalized_engine}/{normalized_path}",
        owner_name=normalized_engine,
        relative_path=normalized_path,
    )
    authorize_media_target(target)

    return _serve_scoped_file(
        base_dir=media_asset_base_path(target),
        file_path=asset_relative_path,
        target=target,
        width=width,
        height=height,
    )


async def serve_extractor_media(
    extractor_id: str,
    file_path: str,
    *,
    width: int | None = None,
    height: int | None = None,
):
    normalized_extractor = extractor_id
    if not is_valid_runtime_asset_owner(normalized_extractor):
        raise HTTPException(status_code=400, detail="Invalid extractor id")
    normalized_path = file_path.strip().replace("\\", "/").lstrip("/")
    if not normalized_path.startswith("assets/"):
        raise HTTPException(
            status_code=403, detail="Extractor media must live under assets/"
        )
    asset_relative_path = normalized_path[len("assets/") :].strip().lstrip("/")
    if not asset_relative_path:
        raise HTTPException(status_code=404, detail="Media file not found")
    target = MediaTarget(
        kind="extractor_asset",
        requester_module=normalized_extractor,
        raw_url=f"/media/extractors/{normalized_extractor}/{normalized_path}",
        owner_name=normalized_extractor,
        relative_path=normalized_path,
    )
    authorize_media_target(target)

    return _serve_scoped_file(
        base_dir=media_asset_base_path(target),
        file_path=asset_relative_path,
        target=target,
        width=width,
        height=height,
    )


async def serve_uploaded_media(
    file_id: str,
    download: bool = False,
):
    current = req_ctx()
    ctx = current.app
    if ctx.media is None:
        raise HTTPException(status_code=503, detail="Media storage unavailable")
    authorization = authorize_media_target(
        MediaTarget(
            kind="upload_file_id",
            requester_module="",
            raw_url=f"/media/uploads/{file_id}",
            file_id=file_id,
        )
    )
    record = authorization.upload_record
    try:
        payload = ctx.media.load(record.storage_path)
    except Exception:
        raise HTTPException(status_code=404, detail="Uploaded file content not found")
    return Response(
        content=payload,
        media_type=record.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{record.original_filename}"'
                if download
                else f'inline; filename="{record.original_filename}"'
            ),
            "Cache-Control": "private, max-age=60",
            "X-Storage-Path": record.storage_path,
        },
    )


async def serve_uploaded_media_by_storage_path(
    storage_path: str,
    download: bool = False,
):
    current = req_ctx()
    ctx = current.app
    if ctx.media is None:
        raise HTTPException(status_code=503, detail="Media storage unavailable")
    normalized_path = storage_path
    if not normalized_path:
        raise HTTPException(status_code=400, detail="storage_path is required")
    authorization = authorize_media_target(
        MediaTarget(
            kind="upload_storage_path",
            requester_module="",
            raw_url="/media/uploads/by-storage-path",
            storage_path=normalized_path,
        )
    )
    record = authorization.upload_record
    try:
        payload = ctx.media.load(record.storage_path)
    except Exception:
        raise HTTPException(status_code=404, detail="Uploaded file content not found")
    return Response(
        content=payload,
        media_type=record.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{record.original_filename}"'
                if download
                else f'inline; filename="{record.original_filename}"'
            ),
            "Cache-Control": "private, max-age=60",
        },
    )
