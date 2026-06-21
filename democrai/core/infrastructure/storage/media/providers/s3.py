from __future__ import annotations

import os
import posixpath
import tempfile
from typing import Any
from urllib.parse import quote
from pathlib import Path

from democrai.core.infrastructure.storage.errors import ProviderConfigError
from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.infrastructure.storage.media.providers.base import MaterializedMedia, MediaProvider
from democrai.core.runtime.foundation.paths import fs_open, fs_path, logical_path


class S3MediaProvider(MediaProvider):
    """AWS S3-compatible implementation of MediaProvider."""

    def __init__(
        self,
        bucket_name: str,
        region: str = "us-east-1",
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint_url: str | None = None,
        public_base_url: str | None = None,
        key_prefix: str | None = None,
        session_token: str | None = None,
        use_path_style: bool = False,
    ):
        if not bucket_name:
            raise ProviderConfigError("S3 requires bucket_name")
        if bool(access_key) != bool(secret_key):
            raise ProviderConfigError(
                "S3 access_key and secret_key must be provided together"
            )

        self.bucket_name = bucket_name
        self.region = region or "us-east-1"
        self.endpoint_url = endpoint_url or None
        self.public_base_url = (public_base_url or "").rstrip("/") or None
        self.key_prefix = self._normalize_prefix(key_prefix)
        self.use_path_style = use_path_style
        self._client = self._build_client(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )

    @staticmethod
    def _normalize_prefix(prefix: str | None) -> str:
        if not prefix:
            return ""
        normalized = prefix.strip().strip("/")
        if not normalized:
            return ""
        return f"{normalized}/"

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path or not isinstance(path, str):
            raise ValueError("path must be a non-empty string")
        if path.startswith("/") or path.startswith("\\"):
            raise ValueError("absolute paths are not allowed")
        normalized = posixpath.normpath(path.replace("\\", "/")).strip()
        if normalized in {"", "."}:
            raise ValueError("path must be a non-empty string")
        if normalized.startswith("../") or normalized == "..":
            raise ValueError("path escapes media base directory")
        return normalized

    def _object_key(self, path: str) -> str:
        return f"{self.key_prefix}{self._normalize_path(path)}"

    def _build_client(
        self,
        *,
        access_key: str | None,
        secret_key: str | None,
        session_token: str | None,
    ) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise ProviderNotAvailableError(
                "S3 media provider requires boto3 to be installed"
            ) from exc

        session_kwargs: dict[str, Any] = {}
        if access_key and secret_key:
            session_kwargs["aws_access_key_id"] = access_key
            session_kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            session_kwargs["aws_session_token"] = session_token
        if self.region:
            session_kwargs["region_name"] = self.region

        session = boto3.session.Session(**session_kwargs)
        client_kwargs: dict[str, Any] = {}
        if self.endpoint_url:
            client_kwargs["endpoint_url"] = self.endpoint_url
        if self.use_path_style:
            client_kwargs["config"] = boto3.session.Config(
                s3={"addressing_style": "path"}
            )
        return session.client("s3", **client_kwargs)

    def save(self, path: str, data: bytes) -> str:
        key = self._object_key(path)
        self._client.put_object(Bucket=self.bucket_name, Key=key, Body=data)
        return self._normalize_path(path)

    def save_file(self, path: str, source_path: str) -> str:
        key = self._object_key(path)
        self._client.upload_file(source_path, self.bucket_name, key)
        return self._normalize_path(path)

    def load(self, path: str) -> bytes:
        key = self._object_key(path)
        response = self._client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    def get_path(
        self,
        path: str,
        *,
        destination_dir: str | None = None,
    ) -> MaterializedMedia:
        normalized = self._normalize_path(path)
        if self.exists(normalized):
            suffix = Path(normalized).suffix or ".bin"
            handle = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                dir=fs_path(destination_dir) if destination_dir is not None else None,
            )
            try:
                handle.write(self.load(normalized))
                handle.flush()
            finally:
                handle.close()
            return MaterializedMedia(path=logical_path(handle.name), temporary=True)

        directory_prefix = normalized.rstrip("/")
        files = [
            item
            for item in self.list(directory_prefix)
            if item != directory_prefix and item.startswith(directory_prefix + "/")
        ]
        if not files:
            raise FileNotFoundError(path)

        target_root = Path(
            tempfile.mkdtemp(
                prefix="democrai-media-",
                dir=fs_path(destination_dir) if destination_dir is not None else None,
            )
        )
        for item in files:
            relative_name = item[len(directory_prefix) + 1 :].strip("/")
            if not relative_name:
                continue
            target = target_root / relative_name
            os.makedirs(fs_path(target.parent), exist_ok=True)
            with fs_open(target, "wb") as handle:
                handle.write(self.load(item))
        return MaterializedMedia(path=logical_path(str(target_root)), temporary=True)

    def delete(self, path: str) -> None:
        normalized = self._normalize_path(path)
        key = self._object_key(normalized)
        self._client.delete_object(Bucket=self.bucket_name, Key=key)

        children = [
            self._object_key(item)
            for item in self.list(normalized.rstrip("/") + "/")
            if item != normalized and item.startswith(normalized.rstrip("/") + "/")
        ]
        for offset in range(0, len(children), 1000):
            batch = children[offset : offset + 1000]
            if batch:
                self._client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": [{"Key": item} for item in batch]},
                )

    def exists(self, path: str) -> bool:
        key = self._object_key(path)
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False

    def list(self, prefix: str = "") -> list[str]:
        normalized = self._normalize_path(prefix) if str(prefix or "").strip() else ""
        key_prefix = f"{self.key_prefix}{normalized}" if normalized else self.key_prefix
        continuation_token: str | None = None
        items: list[str] = []
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self.bucket_name,
                "Prefix": key_prefix,
                "MaxKeys": 1000,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = self._client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or []:
                key = str(item.get("Key") or "")
                if not key:
                    continue
                if self.key_prefix and key.startswith(self.key_prefix):
                    key = key[len(self.key_prefix) :]
                items.append(key)
            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break
        items.sort()
        return items

    def get_public_url(self, path: str) -> str:
        key = quote(self._object_key(path), safe="/")
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        if self.endpoint_url:
            base = self.endpoint_url.rstrip("/")
            if self.use_path_style:
                return f"{base}/{self.bucket_name}/{key}"
            return f"{base}/{key}"
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"
