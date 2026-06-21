import pytest

import democrai.core.infrastructure.storage.media.providers.local as local_media_mod
from democrai.core.infrastructure.storage.media.providers.local import LocalMediaProvider


def test_local_media_provider_rejects_path_escape(tmp_path):
    provider = LocalMediaProvider(str(tmp_path / "assets"))

    with pytest.raises(ValueError):
        provider.save("../escape.txt", b"nope")

    with pytest.raises(ValueError):
        provider.load("../escape.txt")

    with pytest.raises(ValueError):
        provider.delete("/tmp/escape.txt")


def test_local_media_provider_saves_loads_deletes_and_validates_paths(tmp_path):
    provider = LocalMediaProvider(str(tmp_path / "assets"))

    assert provider.save("nested/file.txt", b"demo") == "nested/file.txt"
    assert provider.load("nested/file.txt") == b"demo"
    materialized = provider.get_path("nested/file.txt")
    assert materialized.path.replace("\\", "/").endswith("nested/file.txt")
    assert materialized.temporary is False
    assert provider.get_public_url("nested/file.txt") == "/assets/nested/file.txt"

    provider.delete("nested/file.txt")
    provider.delete("nested/file.txt")

    with pytest.raises(ValueError, match="non-empty string"):
        provider.save("", b"x")

    with pytest.raises(ValueError, match="absolute paths are not allowed"):
        provider.load("/tmp/file.txt")


def test_local_media_provider_list_and_default_base_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(local_media_mod, "get_data_dir", lambda: str(tmp_path / "data"))
    provider = LocalMediaProvider()
    assert provider.base_dir.replace("\\", "/").endswith("/data/assets")

    provider.save("a/one.txt", b"1")
    provider.save("a/two.txt", b"2")
    provider.save("b/three.txt", b"3")

    assert provider.exists("a/one.txt") is True
    assert provider.exists("missing.txt") is False
    assert provider.list() == ["a/one.txt", "a/two.txt", "b/three.txt"]
    assert provider.list("a") == ["a/one.txt", "a/two.txt"]
    assert provider.list("a/one.txt") == ["a/one.txt"]
    assert provider.list("not-there") == []
    assert provider.get_path("a").temporary is False


def test_local_media_provider_keeps_return_paths_logical_for_nested_files(tmp_path):
    provider = LocalMediaProvider(str(tmp_path / "assets"))
    long_name = ("segment-" * 12) + "file.txt"
    storage_path = f"deep/nested/{long_name}"
    source = tmp_path / "source" / long_name
    source.parent.mkdir(parents=True)
    source.write_bytes(b"payload")

    assert provider.save_file(storage_path, str(source)) == storage_path
    assert provider.load(storage_path) == b"payload"
    assert provider.exists(storage_path) is True
    assert provider.list("deep") == [storage_path]

    destination_dir = tmp_path / "materialized" / ("nested-" * 8)
    materialized = provider.get_path(storage_path, destination_dir=str(destination_dir))
    assert materialized.temporary is True
    assert not materialized.path.startswith("\\\\?\\")
    assert materialized.path.startswith(str(destination_dir))
    assert provider.delete(storage_path) is None
