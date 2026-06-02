from democrai.core.infrastructure.database.providers.sqlite import SqlitePersistenceProvider
from democrai.core.infrastructure.database.providers.postgres import PostgresPersistenceProvider
from democrai.core.infrastructure.storage.errors import ProviderConfigError
from democrai.core.infrastructure.database.providers.base import PersistenceProvider


def _sqlite_db_path_from_url(raw_url: str | None) -> str | None:
    if not isinstance(raw_url, str):
        return None
    url = raw_url.strip()
    if not url.lower().startswith("sqlite:///"):
        return None
    path = url[len("sqlite:///") :].strip()
    if path == "":
        return None
    return path


class PersistenceProviderFactory:
    """Factory for creating persistence providers."""

    @staticmethod
    def get_provider(provider_type: str = "sqlite", **kwargs) -> PersistenceProvider:
        """
        Returns a PersistenceProvider instance.
        Valid types: 'sqlite', 'postgres'
        """
        if provider_type == "sqlite":
            db_path = kwargs.get("db_path")
            if db_path is None:
                db_path = _sqlite_db_path_from_url(kwargs.get("db_url"))
            return SqlitePersistenceProvider(db_path)
        if provider_type == "postgres":
            db_url = kwargs.get("db_url")
            if db_url is None:
                raise ProviderConfigError("Postgres requires db_url")
            return PostgresPersistenceProvider(db_url)
        raise ProviderConfigError(
            f"Unknown persistence provider type: {provider_type}"
        )
