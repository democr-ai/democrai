from __future__ import annotations

import json
import os
import shutil
import time
import contextlib
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from democrai.core.application.services.media_uploads import store_uploaded_media
from democrai.core.infrastructure.storage.media.providers.base import MaterializedMedia
from democrai.core.infrastructure.database.media_uploads import (
    delete_media_upload_by_storage_path,
    update_media_upload_storage_path,
)
from democrai.core.platform.ui.media_sources import resolve_client_media_source
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx
from democrai.core.runtime.foundation.paths import get_data_dir

__all__ = [
    "Media",
    "MaterializedMedia",
    "media_type_from_content_type",
    "require_media_provider",
]

MODEL_MANIFEST_NAME = ".democrai-model-manifest.json"
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_PROGRESS_INTERVAL_SECONDS = 0.75
ProgressCallback = Callable[[dict[str, Any]], None]


@contextlib.contextmanager
def _framework_media_storage_context():
    try:
        from democrai.core.infrastructure.sandbox.process_guard import (
            process_guard_bypass_context,
        )
    except Exception:
        yield
        return
    with process_guard_bypass_context():
        yield


def require_media_provider():
    """Return the active media provider or raise if media is unavailable."""
    media = getattr(app_ctx(), "media", None)
    if media is None:
        raise RuntimeError("media_provider_unavailable")
    return media


def media_type_from_content_type(content_type: str) -> str:
    return content_type.split("/", 1)[0]


class Media:
    """Expose the minimal media API for module authors."""

    def __init__(self, sdk) -> None:
        self.sdk = sdk

    @staticmethod
    def _normalize_storage_path(path: str) -> str:
        raw_path = str(path or "").strip()
        if not raw_path:
            raise ValueError("path is required")
        return raw_path

    def add(self, path: str, payload: bytes) -> str:
        """Persist bytes into storage and return the computed stored path."""
        original_name = os.path.basename(self._normalize_storage_path(path))
        resolved_payload = bytes(payload or b"")
        if not resolved_payload:
            raise ValueError("media payload is empty")
        try:
            request_context = req_ctx()
        except LookupError as exc:
            raise RuntimeError("media_add_missing_request_context") from exc
        user_id = request_context.user
        if user_id is None:
            raise RuntimeError("media_add_missing_user_id")
        organization_id = request_context.organization_id
        access_level = request_context.access_level
        upload = store_uploaded_media(
            module_name=str(self.sdk.module_name or "core"),
            original_filename=original_name,
            payload=resolved_payload,
            content_type=None,
            user_id=user_id,
            organization_id=organization_id,
            access_level=access_level,
            uploaded_by=user_id,
        )
        return str(upload.storage_path)

    def add_model(
        self,
        model_id: str,
        *,
        payload: bytes | None = None,
        source_path: str | None = None,
        filename: str | None = None,
    ) -> str:
        """Persist a shared model artifact under models/<id>/..."""
        normalized_model_id = self._normalize_model_id(model_id)
        if payload is None and not str(source_path or "").strip():
            raise ValueError("model source is required")
        if payload is not None and str(source_path or "").strip():
            raise ValueError("provide either payload or source_path")

        if payload is not None:
            target_name = os.path.basename(str(filename or "").strip())
            if not target_name:
                raise ValueError("filename is required when saving model bytes")
            storage_path = f"models/{normalized_model_id}/{target_name}"
            return str(require_media_provider().save(storage_path, bytes(payload)))

        raw_source_path = str(source_path or "").strip()
        normalized_source = self._normalize_storage_path(raw_source_path)
        if raw_source_path.startswith("media/"):
            target_name = os.path.basename(str(filename or "").strip()) or Path(normalized_source).name
            if not target_name:
                raise ValueError("filename is required when saving model media")
            storage_path = f"models/{normalized_model_id}/{target_name}"
            return self.move(raw_source_path, storage_path)

        source = Path(raw_source_path).expanduser()
        if source.is_dir():
            files: list[str] = []
            for candidate in sorted(source.rglob("*")):
                if not candidate.is_file():
                    continue
                relative_name = candidate.relative_to(source).as_posix()
                media_path = f"models/{normalized_model_id}/{relative_name}"
                require_media_provider().save_file(media_path, str(candidate))
                files.append(relative_name)
            manifest_path = f"models/{normalized_model_id}/{MODEL_MANIFEST_NAME}"
            require_media_provider().save(
                manifest_path,
                json.dumps({"kind": "directory", "files": files}).encode("utf-8"),
            )
            return f"models/{normalized_model_id}"

        if not source.is_file():
            raise ValueError("model source path is not readable")

        target_name = os.path.basename(str(filename or "").strip()) or source.name
        if not target_name:
            raise ValueError("filename is required when saving model file")
        storage_path = f"models/{normalized_model_id}/{target_name}"
        return str(require_media_provider().save_file(storage_path, str(source)))

    def add_model_from_source(
        self,
        model_id: str,
        *,
        source: dict,
        filename: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        """Download a remote model source and persist it under shared model storage."""
        normalized_model_id = self._normalize_model_id(model_id)
        resolved_source = source if isinstance(source, dict) else {}
        source_type = str(resolved_source.get("type") or "").strip().lower()
        if source_type == "huggingface":
            return self._add_huggingface_model_from_source(
                normalized_model_id,
                source=resolved_source,
                filename=filename,
                progress_callback=progress_callback,
            )
        if source_type in {"http", "https", "url", "remote_url"}:
            url = str(resolved_source.get("url") or "").strip()
            if not url:
                raise ValueError("url_source_required")
            source_target = self._model_source_target(resolved_source)
            target_name = os.path.basename(str(filename or "").strip()) or os.path.basename(url.split("?", 1)[0]) or "model"
            with _framework_media_storage_context():
                staging_dir = self._model_staging_dir(normalized_model_id)
                try:
                    target = staging_dir / source_target if source_target else staging_dir / target_name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self._download_url_to_file(
                        url,
                        target_path=target,
                        progress_callback=progress_callback,
                        label=target_name,
                    )
                    if source_target:
                        return self.add_model(normalized_model_id, source_path=str(staging_dir))
                    return self.add_model(normalized_model_id, source_path=str(target))
                finally:
                    if staging_dir.exists():
                        shutil.rmtree(staging_dir)
        raise ValueError(f"unsupported_model_source:{source_type or 'unknown'}")

    def _add_huggingface_model_from_source(
        self,
        model_id: str,
        *,
        source: dict,
        filename: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        repo = str(source.get("repo") or source.get("repo_id") or "").strip()
        if not repo:
            raise ValueError("huggingface_repo_required")
        revision = str(source.get("revision") or "main").strip() or "main"
        files = [
            str(item or "").strip().lstrip("/")
            for item in list(source.get("files") or [])
            if str(item or "").strip()
        ]
        token = self._resolve_huggingface_token(source.get("token"))
        should_store_snapshot = bool(source.get("snapshot")) or len(files) != 1
        source_target = self._model_source_target(source)
        target_prefix = str(source.get("target") or "").strip().strip("/\\")
        if not should_store_snapshot:
            remote_path = files[0]
            target_name = os.path.basename(str(filename or "").strip()) or os.path.basename(remote_path) or "model"
            with _framework_media_storage_context():
                staging_dir = self._model_staging_dir(model_id)
                try:
                    target = staging_dir / source_target if source_target else staging_dir / target_name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self._download_huggingface_file_to_path(
                        repo_id=repo,
                        revision=revision,
                        remote_path=remote_path,
                        token=token,
                        target_path=target,
                        progress_callback=progress_callback,
                    )
                    if source_target:
                        return self.add_model(model_id, source_path=str(staging_dir))
                    return self.add_model(model_id, source_path=str(target), filename=target_name)
                finally:
                    if staging_dir.exists():
                        shutil.rmtree(staging_dir)

        with _framework_media_storage_context():
            staging_dir = self._model_staging_dir(model_id)
            try:
                destination = staging_dir / target_prefix if target_prefix else staging_dir
                self._download_huggingface_snapshot(
                    repo_id=repo,
                    destination_path=str(destination),
                    revision=revision,
                    files=files,
                    token=token,
                    progress_callback=progress_callback,
                )
                return self.add_model(model_id, source_path=str(staging_dir))
            finally:
                if staging_dir.exists():
                    shutil.rmtree(staging_dir)

    @staticmethod
    def _model_source_target(source: dict[str, Any]) -> str:
        target = str(source.get("target") or "").strip().replace("\\", "/").strip("/")
        if target.startswith("models/"):
            target = target[len("models/") :]
        if not target or target.startswith("../") or target == ".." or "/../" in target:
            return ""
        return target

    def _download_huggingface_snapshot(
        self,
        *,
        repo_id: str,
        destination_path: str,
        revision: str = "main",
        files: list[str] | None = None,
        token: str | bool | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> list[str]:
        repo = str(repo_id or "").strip()
        if not repo:
            raise ValueError("repo_id is required")
        destination = Path(self._normalize_storage_path(destination_path)).expanduser()
        resolved_revision = str(revision or "main").strip() or "main"
        resolved_token = self._resolve_huggingface_token(token)
        resolved_files = [
            str(item or "").strip().lstrip("/")
            for item in list(files or [])
            if str(item or "").strip()
        ]
        if not resolved_files:
            resolved_files = self._list_huggingface_snapshot_files(
                repo_id=repo,
                revision=resolved_revision,
                token=resolved_token,
            )
        if not resolved_files:
            raise ValueError("huggingface_snapshot_empty")

        destination.mkdir(parents=True, exist_ok=True)
        total_files = len(resolved_files)
        for index, remote_path in enumerate(resolved_files, start=1):
            target = destination / remote_path
            target.parent.mkdir(parents=True, exist_ok=True)
            self._download_huggingface_file_to_path(
                repo_id=repo,
                revision=resolved_revision,
                remote_path=remote_path,
                token=resolved_token,
                target_path=target,
                progress_callback=progress_callback,
                file_index=index,
                total_files=total_files,
            )
        return resolved_files

    def view(self, path: str) -> bytes:
        """Load bytes from storage for direct consumption."""
        storage_path = self._normalize_storage_path(path)
        return bytes(require_media_provider().load(storage_path))

    def get_path(
        self,
        path: str,
        *,
        destination_dir: str | None = None,
    ) -> MaterializedMedia:
        """Return a local filesystem path for path-only consumers."""
        storage_path = self._normalize_storage_path(path)
        return require_media_provider().get_path(
            storage_path,
            destination_dir=destination_dir,
        )

    def move(self, source_path: str, destination_path: str) -> str:
        """Move one stored object to a new storage path."""
        source = self._normalize_storage_path(source_path)
        destination = self._normalize_storage_path(destination_path)
        if source == destination:
            return destination
        payload = self.view(source)
        saved_path = str(require_media_provider().save(destination, payload))
        require_media_provider().delete(source)
        update_media_upload_storage_path(
            old_storage_path=source,
            new_storage_path=saved_path,
            stored_filename=os.path.basename(saved_path),
        )
        return saved_path

    def delete(self, path: str) -> None:
        """Delete one stored object and any matching upload metadata row."""
        storage_path = self._normalize_storage_path(path)
        require_media_provider().delete(storage_path)
        delete_media_upload_by_storage_path(storage_path=storage_path)

    def get_public_url(self, path: str) -> str | None:
        """Return the runtime proxy URL a UI component should consume."""
        resolved = str(path or "").strip()
        if not resolved:
            return None
        normalized = resolve_client_media_source(
            module_name=str(self.sdk.module_name or ""),
            module_path=str(getattr(self.sdk, "module_path", "") or ""),
            value=resolved,
        )
        normalized = str(normalized or "").strip()
        if not normalized:
            return None
        if normalized.startswith("/media/proxy?"):
            return normalized
        module_name = str(self.sdk.module_name or "").strip() or "core"
        return "/media/proxy?" + urlencode(
            {"module_name": module_name, "url": normalized},
            quote_via=quote,
        )

    @staticmethod
    def _normalize_model_id(model_id: str) -> str:
        normalized = "".join(
            char if char.isalnum() or char in {".", "_", "-"} else "_"
            for char in str(model_id or "").strip()
        ).strip("._")
        if not normalized:
            raise ValueError("model_id is required")
        return normalized

    @staticmethod
    def _temp_dir() -> Path:
        path = Path(get_data_dir()) / "tmp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def _model_staging_dir(cls, model_id: str) -> Path:
        path = cls._temp_dir() / f"democrai_model_{cls._normalize_model_id(model_id)}"
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=False)
        return path

    @staticmethod
    def _resolve_huggingface_token(token: str | bool | None) -> str | None:
        if token is False:
            return None
        resolved = (
            str(token or "").strip()
            or os.environ.get("HF_TOKEN", "").strip()
            or os.environ.get("HUGGING_FACE_HUB_TOKEN", "").strip()
        )
        return resolved or None

    @staticmethod
    def _huggingface_headers(token: str | None) -> dict[str, str]:
        headers = {"User-Agent": "democrai-sdk-media"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @classmethod
    def _download_url(cls, url: str, *, token: str | None = None) -> bytes:
        request = Request(url, headers=cls._huggingface_headers(token))
        with urlopen(request) as response:
            return bytes(response.read())

    @classmethod
    def _download_url_to_file(
        cls,
        url: str,
        *,
        target_path: Path,
        token: str | None = None,
        progress_callback: ProgressCallback | None = None,
        label: str | None = None,
        file_index: int | None = None,
        total_files: int | None = None,
    ) -> None:
        request = Request(url, headers=cls._huggingface_headers(token))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(request) as response, open(target_path, "wb") as target:
            total_bytes = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            last_emit = 0.0
            resolved_label = label or target_path.name
            cls._emit_download_progress(
                progress_callback,
                label=resolved_label,
                downloaded_bytes=downloaded,
                total_bytes=total_bytes,
                file_index=file_index,
                total_files=total_files,
            )
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                target.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_emit >= _PROGRESS_INTERVAL_SECONDS:
                    last_emit = now
                    cls._emit_download_progress(
                        progress_callback,
                        label=resolved_label,
                        downloaded_bytes=downloaded,
                        total_bytes=total_bytes,
                        file_index=file_index,
                        total_files=total_files,
                    )
            cls._emit_download_progress(
                progress_callback,
                label=resolved_label,
                downloaded_bytes=downloaded,
                total_bytes=total_bytes,
                file_index=file_index,
                total_files=total_files,
            )

    @staticmethod
    def _emit_download_progress(
        progress_callback: ProgressCallback | None,
        *,
        label: str,
        downloaded_bytes: int,
        total_bytes: int,
        file_index: int | None = None,
        total_files: int | None = None,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(
            {
                "label": label,
                "downloaded_bytes": int(downloaded_bytes),
                "total_bytes": int(total_bytes),
                "file_index": file_index,
                "total_files": total_files,
            }
        )

    @classmethod
    def _list_huggingface_snapshot_files(
        cls,
        *,
        repo_id: str,
        revision: str,
        token: str | None,
    ) -> list[str]:
        repo_path = "/".join(quote(part, safe="") for part in repo_id.split("/"))
        url = (
            f"https://huggingface.co/api/models/{repo_path}"
            f"?revision={quote(revision, safe='')}&blobs=true"
        )
        payload = json.loads(cls._download_url(url, token=token).decode("utf-8"))
        siblings = payload.get("siblings") if isinstance(payload, dict) else []
        return [
            str(item.get("rfilename") or "").strip().lstrip("/")
            for item in list(siblings or [])
            if isinstance(item, dict) and str(item.get("rfilename") or "").strip()
        ]

    @classmethod
    def _download_huggingface_file(
        cls,
        *,
        repo_id: str,
        revision: str,
        remote_path: str,
        token: str | None,
    ) -> bytes:
        repo_path = "/".join(quote(part, safe="") for part in repo_id.split("/"))
        file_path = "/".join(quote(part, safe="") for part in remote_path.split("/"))
        url = (
            f"https://huggingface.co/{repo_path}/resolve/"
            f"{quote(revision, safe='')}/{file_path}"
        )
        return cls._download_url(url, token=token)

    @classmethod
    def _download_huggingface_file_to_path(
        cls,
        *,
        repo_id: str,
        revision: str,
        remote_path: str,
        token: str | None,
        target_path: Path,
        progress_callback: ProgressCallback | None = None,
        file_index: int | None = None,
        total_files: int | None = None,
    ) -> None:
        repo_path = "/".join(quote(part, safe="") for part in repo_id.split("/"))
        file_path = "/".join(quote(part, safe="") for part in remote_path.split("/"))
        url = (
            f"https://huggingface.co/{repo_path}/resolve/"
            f"{quote(revision, safe='')}/{file_path}"
        )
        cls._download_url_to_file(
            url,
            target_path=target_path,
            token=token,
            progress_callback=progress_callback,
            label=remote_path,
            file_index=file_index,
            total_files=total_files,
        )
