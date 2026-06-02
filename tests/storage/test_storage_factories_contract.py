import pytest

from democrai.core.infrastructure.storage.data.factory import DataStorageProviderFactory
from democrai.core.infrastructure.storage.kg.factory import KGStoreFactory
from democrai.core.infrastructure.storage.media.factory import MediaProviderFactory
from democrai.core.infrastructure.storage.observability.factory import ObservabilityFactory
from democrai.core.infrastructure.storage.vector.factory import VectorStoreFactory
from democrai.core.infrastructure.storage.vector.sqlite_vec_store import sqlite_vec_available
from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError


def test_factories_expose_unified_get_provider():
    assert callable(DataStorageProviderFactory.get_provider)
    assert callable(MediaProviderFactory.get_provider)
    assert callable(ObservabilityFactory.get_provider)
    assert callable(KGStoreFactory.get_provider)
    assert callable(VectorStoreFactory.get_provider)


def test_kg_factory_alias_is_backward_compatible(monkeypatch):
    from democrai.core.infrastructure.storage.kg import factory

    monkeypatch.setattr(
        factory,
        "LadybugKGStorage",
        lambda db_path=None: ("ladybug", db_path),
    )
    p1 = KGStoreFactory.get_provider("ladybug", db_path="kg.lbug")
    p2 = KGStoreFactory.get_store("ladybug", db_path="kg.lbug")
    assert p1 == p2


def test_vector_factory_contract_local_provider():
    has_vec, _ = sqlite_vec_available()
    if has_vec:
        provider = VectorStoreFactory.get_provider("sqlite-vec")
        assert provider is not None
        return

    with pytest.raises(ProviderNotAvailableError):
        VectorStoreFactory.get_provider("sqlite-vec")
