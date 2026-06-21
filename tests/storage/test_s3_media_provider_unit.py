import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.storage.errors import ProviderConfigError
from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.infrastructure.storage.media.providers.s3 import S3MediaProvider


class _FakeBody:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.list_responses = []

    def put_object(self, *, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):
        return {"Body": _FakeBody(self.objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise RuntimeError("missing")
        return {"ok": True}

    def list_objects_v2(self, **kwargs):
        if self.list_responses:
            return self.list_responses.pop(0)
        prefix = kwargs.get("Prefix", "")
        keys = [
            key
            for bucket, key in self.objects
            if bucket == kwargs.get("Bucket") and key.startswith(prefix)
        ]
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}


class _FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self, service_name, **kwargs):
        assert service_name == "s3"
        self.client_kwargs = kwargs
        return self._client


def _install_fake_boto3(monkeypatch: pytest.MonkeyPatch, client: _FakeS3Client) -> None:
    fake_module = SimpleNamespace(
        session=SimpleNamespace(
            Session=lambda **kwargs: _FakeSession(client),
            Config=lambda **kwargs: ("config", kwargs),
        )
    )
    monkeypatch.setitem(sys.modules, "boto3", fake_module)


def test_s3_media_provider_roundtrip_and_public_url(monkeypatch: pytest.MonkeyPatch):
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)

    provider = S3MediaProvider(
        "bucket",
        region="eu-central-1",
        key_prefix="uploads",
        public_base_url="https://cdn.example.com/assets",
    )

    assert provider.save("avatars/user 1.png", b"img") == "avatars/user 1.png"
    assert client.objects[("bucket", "uploads/avatars/user 1.png")] == b"img"
    assert provider.load("avatars/user 1.png") == b"img"
    materialized = provider.get_path("avatars/user 1.png")
    assert materialized.temporary is True
    assert Path(materialized.path).read_bytes() == b"img"
    materialized.cleanup()
    assert (
        provider.get_public_url("avatars/user 1.png")
        == "https://cdn.example.com/assets/uploads/avatars/user%201.png"
    )

    provider.delete("avatars/user 1.png")
    assert client.objects == {}


def test_s3_media_provider_rejects_invalid_paths(monkeypatch: pytest.MonkeyPatch):
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)
    provider = S3MediaProvider("bucket")

    with pytest.raises(ValueError):
        provider.save("../escape.txt", b"nope")

    with pytest.raises(ValueError):
        provider.load("/absolute/path.txt")

    with pytest.raises(ValueError):
        provider.save(".", b"nope")

    assert provider._normalize_prefix(" /uploads/ ") == "uploads/"


def test_s3_media_provider_requires_paired_credentials(monkeypatch: pytest.MonkeyPatch):
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)

    with pytest.raises(ProviderConfigError):
        S3MediaProvider("bucket", access_key="ak")

    with pytest.raises(ProviderConfigError):
        S3MediaProvider("")


def test_s3_media_provider_requires_boto3(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delitem(sys.modules, "boto3", raising=False)

    real_import = __import__

    def _raising_import(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("missing boto3")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _raising_import)

    with pytest.raises(ProviderNotAvailableError):
        S3MediaProvider("bucket")


def test_s3_media_provider_builds_endpoint_and_path_style_urls(monkeypatch: pytest.MonkeyPatch):
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)

    provider = S3MediaProvider(
        "bucket",
        endpoint_url="https://s3.example.com/",
        use_path_style=True,
        key_prefix="nested",
        access_key="ak",
        secret_key="sk",
        session_token="token",
    )
    assert provider.get_public_url("file name.txt") == "https://s3.example.com/bucket/nested/file%20name.txt"

    provider2 = S3MediaProvider(
        "bucket",
        endpoint_url="https://s3.example.com/",
        key_prefix="nested",
    )
    assert provider2.get_public_url("file name.txt") == "https://s3.example.com/nested/file%20name.txt"


def test_s3_media_provider_exists_list_and_default_url(monkeypatch: pytest.MonkeyPatch):
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)
    provider = S3MediaProvider("bucket", key_prefix="k")

    assert provider.exists("missing.txt") is False
    provider.save("z.txt", b"z")
    assert provider.exists("z.txt") is True
    assert provider.get_public_url("z.txt") == "https://bucket.s3.us-east-1.amazonaws.com/k/z.txt"

    client.list_responses = [
        {
            "Contents": [{"Key": "k/b.txt"}, {"Key": ""}],
            "IsTruncated": True,
            "NextContinuationToken": "tok",
        },
        {
            "Contents": [{"Key": "k/a.txt"}],
            "IsTruncated": True,
        },
    ]
    assert provider.list() == ["a.txt", "b.txt"]

    provider_no_prefix = S3MediaProvider("bucket")
    assert provider_no_prefix._normalize_prefix(" / ") == ""
    with pytest.raises(ValueError):
        provider_no_prefix._normalize_path(None)  # type: ignore[arg-type]
    client.list_responses = [{"Contents": [{"Key": "plain.txt"}], "IsTruncated": False}]
    assert provider_no_prefix.list() == ["plain.txt"]


def test_s3_media_provider_get_path_directory(monkeypatch: pytest.MonkeyPatch, tmp_path):
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)
    provider = S3MediaProvider("bucket", key_prefix="k")

    provider.save("models/m/a.bin", b"A")
    provider.save("models/m/sub/b.bin", b"B")

    materialized = provider.get_path("models/m", destination_dir=str(tmp_path))
    root = Path(materialized.path)
    assert materialized.temporary is True
    assert not materialized.path.startswith("\\\\?\\")
    assert root.parent == tmp_path
    assert (root / "a.bin").read_bytes() == b"A"
    assert (root / "sub" / "b.bin").read_bytes() == b"B"
    materialized.cleanup()
    assert not root.exists()


def test_s3_media_provider_get_path_file_keeps_logical_temp_path(monkeypatch: pytest.MonkeyPatch, tmp_path):
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)
    provider = S3MediaProvider("bucket", key_prefix="k")

    provider.save("models/m/long.bin", b"model")

    destination = tmp_path / ("nested-" * 8)
    destination.mkdir()
    materialized = provider.get_path("models/m/long.bin", destination_dir=str(destination))

    assert materialized.temporary is True
    assert not materialized.path.startswith("\\\\?\\")
    assert Path(materialized.path).parent == destination
    assert Path(materialized.path).read_bytes() == b"model"
    materialized.cleanup()


def test_s3_media_provider_build_client_without_region(monkeypatch: pytest.MonkeyPatch):
    captured_kwargs = []
    client = _FakeS3Client()

    class _CaptureSession:
        def __init__(self, **kwargs):
            captured_kwargs.append(kwargs)

        def client(self, service_name, **kwargs):
            assert service_name == "s3"
            return client

    fake_module = SimpleNamespace(
        session=SimpleNamespace(
            Session=lambda **kwargs: _CaptureSession(**kwargs),
            Config=lambda **kwargs: ("config", kwargs),
        )
    )
    monkeypatch.setitem(sys.modules, "boto3", fake_module)
    provider = S3MediaProvider("bucket", region="us-east-1")
    provider.region = ""
    provider._client = provider._build_client(
        access_key=None,
        secret_key=None,
        session_token=None,
    )
    assert captured_kwargs and "region_name" not in captured_kwargs[-1]
