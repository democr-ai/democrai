import pytest

from democrai.core.infrastructure.database.factory import PersistenceProviderFactory
from democrai.core.infrastructure.database.providers.postgres import PostgresPersistenceProvider
from democrai.core.infrastructure.database.providers.sqlite import SqlitePersistenceProvider
from democrai.core.infrastructure.storage.errors import ProviderConfigError


def test_database_factory_returns_sqlite_provider():
    provider = PersistenceProviderFactory.get_provider("sqlite")
    assert isinstance(provider, SqlitePersistenceProvider)


def test_database_factory_requires_postgres_url():
    with pytest.raises(ProviderConfigError, match="db_url"):
        PersistenceProviderFactory.get_provider("postgres")


def test_database_factory_returns_postgres_provider():
    pytest.importorskip("psycopg2")
    provider = PersistenceProviderFactory.get_provider(
        "postgres", db_url="postgresql://u:p@localhost:5432/db"
    )
    assert isinstance(provider, PostgresPersistenceProvider)


def test_database_factory_rejects_unknown_provider():
    with pytest.raises(ProviderConfigError, match="Unknown persistence provider type"):
        PersistenceProviderFactory.get_provider("oracle")


def test_database_factory_all_branches_without_external_driver(monkeypatch: pytest.MonkeyPatch):
    from democrai.core.infrastructure.database import factory as mod

    monkeypatch.setattr(mod, "SqlitePersistenceProvider", lambda db_path=None: ("sqlite", db_path))
    monkeypatch.setattr(mod, "PostgresPersistenceProvider", lambda db_url: ("postgres", db_url))

    assert mod.PersistenceProviderFactory.get_provider("sqlite", db_path="main.db") == (
        "sqlite",
        "main.db",
    )
    assert mod.PersistenceProviderFactory.get_provider(
        "postgres", db_url="postgresql://u:p@h/db"
    ) == ("postgres", "postgresql://u:p@h/db")
    with pytest.raises(ProviderConfigError):
        mod.PersistenceProviderFactory.get_provider("postgres")
    with pytest.raises(ProviderConfigError):
        mod.PersistenceProviderFactory.get_provider("unknown")
