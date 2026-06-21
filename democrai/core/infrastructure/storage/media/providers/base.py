from abc import ABC, abstractmethod
from dataclasses import dataclass

from democrai.core.runtime.foundation.paths import (
    fs_is_dir,
    fs_read_bytes,
    fs_rmtree,
    fs_unlink,
)


@dataclass(frozen=True)
class MaterializedMedia:
    """Local filesystem view of a media storage reference."""

    path: str
    temporary: bool = False

    def cleanup(self) -> None:
        if not self.temporary:
            return
        try:
            if fs_is_dir(self.path):
                fs_rmtree(self.path, ignore_errors=True)
            else:
                fs_unlink(self.path, missing_ok=True)
        except OSError:
            pass


class MediaProvider(ABC):
    """Interface for object storage (local disk or cloud)."""

    @abstractmethod
    def save(self, path: str, data: bytes) -> str:
        """Saves data to storage and returns a relative path or URL."""
        pass

    def save_file(self, path: str, source_path: str) -> str:
        """Saves a local file to storage and returns a relative path or URL."""
        return self.save(path, fs_read_bytes(source_path))

    @abstractmethod
    def load(self, path: str) -> bytes:
        """Loads data from storage."""
        pass

    @abstractmethod
    def get_path(
        self,
        path: str,
        *,
        destination_dir: str | None = None,
    ) -> MaterializedMedia:
        """Returns a local filesystem path for a stored file or directory."""
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        """Deletes data from storage."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Returns whether a path exists in storage."""
        pass

    @abstractmethod
    def list(self, prefix: str = "") -> list[str]:
        """Lists stored paths under a prefix."""
        pass

    @abstractmethod
    def get_public_url(self, path: str) -> str:
        """Returns a publicly accessible URL for the asset."""
        pass
