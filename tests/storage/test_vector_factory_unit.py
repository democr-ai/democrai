import asyncio

import pytest

from democrai.core.infrastructure.storage.errors import (
    ProviderConfigError,
    ProviderNotAvailableError,
)
from democrai.core.infrastructure.storage.vector.factory import VectorStoreFactory
import democrai.core.infrastructure.storage.vector.sqlite_vec_store as sqlite_vec_mod
from democrai.core.infrastructure.storage.vector.sqlite_vec_store import SQLiteVecVectorProvider


def test_vector_factory_rejects_unknown_provider():
    with pytest.raises(ProviderConfigError, match="Unknown vector provider type"):
        VectorStoreFactory.get_provider("foobar")


def test_vector_factory_raises_when_sqlite_vec_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.vector.factory.sqlite_vec_available",
        lambda: (False, "missing extension"),
    )

    with pytest.raises(ProviderNotAvailableError, match="sqlite-vec is required"):
        VectorStoreFactory.get_provider("sqlite-vec")


def test_vector_factory_returns_sqlite_vec_provider(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.vector.factory.sqlite_vec_available",
        lambda: (True, None),
    )
    db_path = str(tmp_path / "vector.db")
    provider = VectorStoreFactory.get_provider("sqlite-vec", db_path=db_path)
    assert isinstance(provider, SQLiteVecVectorProvider)
    assert provider.db_path == db_path
    assert provider.index_prefix == "democrai"


def test_vector_factory_returns_pinecone_provider(monkeypatch: pytest.MonkeyPatch):
    import democrai.core.infrastructure.storage.vector.factory as factory_mod

    calls = []

    class _FakePineconeProvider:
        def __init__(self, api_key, *, cloud="aws", region="us-east-1", index_prefix="democrai"):
            calls.append((api_key, cloud, region, index_prefix))

    monkeypatch.setattr(factory_mod, "PineconeVectorProvider", _FakePineconeProvider)
    provider = factory_mod.VectorStoreFactory.get_provider(
        "pinecone",
        api_key="pc-key",
        cloud="aws",
        region="us-east-1",
        index_prefix="demo",
    )
    assert isinstance(provider, _FakePineconeProvider)
    assert calls == [("pc-key", "aws", "us-east-1", "demo")]


def test_sqlite_vec_loader_and_provider_cover_error_paths(monkeypatch: pytest.MonkeyPatch):
    class _Conn:
        def __init__(self):
            self.calls = []

        def enable_load_extension(self, value):
            self.calls.append(("enable", value))

        def load_extension(self, path):
            self.calls.append(("load", path))

    monkeypatch.setattr(sqlite_vec_mod.sqlite_vec, "loadable_path", lambda: "/vec0")
    conn = _Conn()
    ok, err = sqlite_vec_mod._load_sqlite_vec_on_connection(conn)
    assert ok is True and err is None
    assert conn.calls == [("enable", True), ("load", "/vec0"), ("enable", False)]

    class _FailingConn(_Conn):
        def load_extension(self, path):
            self.calls.append(("load", path))
            raise RuntimeError("boom")

    failing_conn = _FailingConn()
    ok, err = sqlite_vec_mod._load_sqlite_vec_on_connection(failing_conn)
    assert ok is False
    assert "boom" in err
    assert failing_conn.calls == [("enable", True), ("load", "/vec0"), ("enable", False)]

    provider = SQLiteVecVectorProvider(":memory:")
    info = asyncio.run(provider.info())
    assert info.name == "sqlite-vec-embedded"
