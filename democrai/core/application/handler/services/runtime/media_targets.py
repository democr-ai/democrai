from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

from fastapi import HTTPException


@dataclass(frozen=True)
class MediaTarget:
    kind: str
    requester_module: str
    raw_url: str
    owner_name: str | None = None
    relative_path: str | None = None
    file_id: str | None = None
    storage_path: str | None = None
    remote_url: str | None = None


def parse_media_proxy_target(*, module_name: str, url: str) -> MediaTarget:
    requester_module = module_name
    if not requester_module:
        raise HTTPException(status_code=400, detail="module_name is required")

    raw_url = url
    if not raw_url:
        raise HTTPException(status_code=400, detail="url is required")

    parsed = urlparse(raw_url)
    raw_path = parsed.path

    if not parsed.scheme and raw_path.startswith("/media/"):
        if raw_path.startswith("/media/uploads/by-storage-path"):
            values = parse_qs(parsed.query).get("storage_path")
            storage_path = values[0] if values else ""
            if not storage_path:
                raise HTTPException(status_code=400, detail="storage_path is required")
            return MediaTarget(
                kind="upload_storage_path",
                requester_module=requester_module,
                raw_url=raw_url,
                storage_path=storage_path,
            )

        if raw_path.startswith("/media/uploads/"):
            file_id = unquote(raw_path[len("/media/uploads/") :]).strip()
            if not file_id:
                raise HTTPException(status_code=400, detail="file_id is required")
            file_parts = [
                part for part in file_id.replace("\\", "/").split("/") if part
            ]
            if "\\" in file_id or ".." in file_parts:
                raise HTTPException(status_code=400, detail="Invalid media path")
            return MediaTarget(
                kind="upload_file_id",
                requester_module=requester_module,
                raw_url=raw_url,
                file_id=file_id,
            )

        if raw_path.startswith("/media/modules/"):
            remainder = raw_path[len("/media/modules/") :].strip()
            owner_name, separator, relative_path = remainder.partition("/")
            owner_name = unquote(owner_name).strip()
            relative_path = unquote(relative_path).strip()
            if not owner_name:
                raise HTTPException(
                    status_code=400, detail="module media owner is required"
                )
            if not separator or not relative_path:
                raise HTTPException(
                    status_code=400, detail="module media path is required"
                )
            path_parts = [
                part for part in relative_path.replace("\\", "/").split("/") if part
            ]
            if "\\" in relative_path or ".." in path_parts:
                raise HTTPException(status_code=400, detail="Invalid media path")
            return MediaTarget(
                kind="module_asset",
                requester_module=requester_module,
                raw_url=raw_url,
                owner_name=owner_name,
                relative_path=relative_path,
            )

        if raw_path.startswith("/media/engine/"):
            remainder = raw_path[len("/media/engine/") :].strip()
            owner_name, separator, relative_path = remainder.partition("/")
            owner_name = unquote(owner_name).strip()
            relative_path = unquote(relative_path).strip()
            if not owner_name:
                raise HTTPException(
                    status_code=400, detail="engine media owner is required"
                )
            if not separator or not relative_path:
                raise HTTPException(
                    status_code=400, detail="engine media path is required"
                )
            path_parts = [
                part for part in relative_path.replace("\\", "/").split("/") if part
            ]
            if "\\" in relative_path or ".." in path_parts:
                raise HTTPException(status_code=400, detail="Invalid media path")
            return MediaTarget(
                kind="engine_asset",
                requester_module=requester_module,
                raw_url=raw_url,
                owner_name=owner_name,
                relative_path=relative_path,
            )

        if raw_path.startswith("/media/extractors/"):
            remainder = raw_path[len("/media/extractors/") :].strip()
            owner_name, separator, relative_path = remainder.partition("/")
            owner_name = unquote(owner_name).strip()
            relative_path = unquote(relative_path).strip()
            if not owner_name:
                raise HTTPException(
                    status_code=400, detail="extractor media owner is required"
                )
            if not separator or not relative_path:
                raise HTTPException(
                    status_code=400, detail="extractor media path is required"
                )
            path_parts = [
                part for part in relative_path.replace("\\", "/").split("/") if part
            ]
            if "\\" in relative_path or ".." in path_parts:
                raise HTTPException(status_code=400, detail="Invalid media path")
            return MediaTarget(
                kind="extractor_asset",
                requester_module=requester_module,
                raw_url=raw_url,
                owner_name=owner_name,
                relative_path=relative_path,
            )

        raise HTTPException(status_code=404, detail="Unsupported internal media path")

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid remote media URL")

    return MediaTarget(
        kind="remote",
        requester_module=requester_module,
        raw_url=raw_url,
        remote_url=raw_url,
    )
