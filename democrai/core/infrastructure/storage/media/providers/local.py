import os
import shutil
import tempfile
from typing import Optional
from democrai.core.runtime.foundation.paths import (
    fs_exists,
    fs_is_dir,
    fs_is_file,
    fs_open,
    fs_parent_mkdir,
    fs_path,
    fs_rmtree,
    fs_unlink,
    get_data_dir,
    logical_path,
)
from .base import MaterializedMedia, MediaProvider


class LocalMediaProvider(MediaProvider):
    """Local filesystem implementation of MediaProvider."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.path.join(get_data_dir(), "assets")
        self.base_dir = os.path.realpath(base_dir)
        os.makedirs(fs_path(self.base_dir), exist_ok=True)

    def _resolve_path(self, path: str) -> str:
        if not path or not isinstance(path, str):
            raise ValueError("path must be a non-empty string")
        if os.path.isabs(path):
            raise ValueError("absolute paths are not allowed")

        full_path = os.path.realpath(os.path.join(self.base_dir, path))
        if full_path != self.base_dir and not full_path.startswith(self.base_dir + os.sep):
            raise ValueError("path escapes media base directory")
        return full_path

    def save(self, path: str, data: bytes) -> str:
        full_path = self._resolve_path(path)
        fs_parent_mkdir(full_path)
        with fs_open(full_path, "wb") as f:
            f.write(data)
        return path

    def save_file(self, path: str, source_path: str) -> str:
        full_path = self._resolve_path(path)
        fs_parent_mkdir(full_path)
        with fs_open(source_path, "rb") as source, fs_open(full_path, "wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        return path

    def load(self, path: str) -> bytes:
        full_path = self._resolve_path(path)
        with fs_open(full_path, "rb") as f:
            return f.read()

    def get_path(
        self,
        path: str,
        *,
        destination_dir: str | None = None,
    ) -> MaterializedMedia:
        full_path = self._resolve_path(path)
        if not fs_exists(full_path):
            raise FileNotFoundError(path)
        if fs_is_dir(full_path):
            return MaterializedMedia(path=full_path, temporary=False)
        if destination_dir is not None:
            os.makedirs(fs_path(str(destination_dir)), exist_ok=True)
            suffix = os.path.splitext(full_path)[1] or ".bin"
            handle = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                dir=fs_path(str(destination_dir)),
            )
            try:
                handle.close()
                shutil.copyfile(fs_path(full_path), fs_path(handle.name))
            except Exception:
                try:
                    fs_unlink(handle.name, missing_ok=True)
                except OSError:
                    pass
                raise
            return MaterializedMedia(path=logical_path(handle.name), temporary=True)
        return MaterializedMedia(path=full_path, temporary=False)

    def delete(self, path: str) -> None:
        full_path = self._resolve_path(path)
        if fs_is_dir(full_path):
            fs_rmtree(full_path)
        elif fs_exists(full_path):
            fs_unlink(full_path)

    def exists(self, path: str) -> bool:
        full_path = self._resolve_path(path)
        return fs_exists(full_path)

    def list(self, prefix: str = "") -> list[str]:
        normalized_prefix = str(prefix or "").strip().strip("/\\")
        base_path = self.base_dir
        if normalized_prefix:
            base_path = self._resolve_path(normalized_prefix)
            if not fs_exists(base_path):
                return []

        items: list[str] = []
        if fs_is_file(base_path):
            rel_path = os.path.relpath(base_path, self.base_dir).replace(os.sep, "/")
            return [rel_path]

        for root, _, files in os.walk(fs_path(base_path)):
            root = logical_path(root)
            for filename in files:
                absolute = os.path.join(root, filename)
                rel_path = os.path.relpath(absolute, self.base_dir).replace(os.sep, "/")
                items.append(rel_path)
        items.sort()
        return items

    def get_public_url(self, path: str) -> str:
        # For local dev, this might be a relative path or handled by a static server
        return f"/assets/{path}"
