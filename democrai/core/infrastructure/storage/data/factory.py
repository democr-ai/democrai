from .providers.sqlite import SqliteDataStorage
from .providers.postgres import PostgresDataStorage
from .providers.supabase import SupabaseDataStorage
from democrai.core.infrastructure.storage.errors import ProviderConfigError
from .providers.base import DataStorageProvider
from typing import Any


def _sqlite_db_path_from_url(raw_url: str | None) -> str | None:
    if not isinstance(raw_url, str):
        return None
    url = raw_url.strip()
    if not url.lower().startswith("sqlite:///"):
        return None
    path = url[len("sqlite:///") :].strip()
    return path or None


class DataStorageProviderFactory:
    """Factory for creating data storage providers."""

    @staticmethod
    def get_provider(
        provider_type: str = "sqlite", **kwargs: Any
    ) -> DataStorageProvider:
        """
        Returns a DataStorageProvider instance.
        """
        if provider_type == "sqlite":
            db_path = kwargs.get("db_path")
            if db_path is None:
                db_path = _sqlite_db_path_from_url(kwargs.get("db_url"))
            return SqliteDataStorage(db_path)
        if provider_type == "postgres":
            db_url = kwargs.get("db_url")
            if db_url is None:
                raise ProviderConfigError("Postgres requires db_url")
            return PostgresDataStorage(db_url)
        if provider_type == "supabase":
            db_url = kwargs.get("db_url")
            if db_url is None:
                raise ProviderConfigError("Supabase requires db_url")
            return SupabaseDataStorage(db_url)
        raise ProviderConfigError(
            f"Unknown data storage provider type: {provider_type}"
        )
