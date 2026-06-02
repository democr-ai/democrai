import os
import json
from typing import Any, cast
from democrai.core.infrastructure.storage.kg.providers.base import KGStorageProvider
from democrai.core.infrastructure.storage.kg.providers.ladybug import LadybugKGStorage
from democrai.core.infrastructure.storage.kg.providers.neo4j import Neo4jKGStorage
from democrai.core.infrastructure.storage.kg.providers.sqlite import SQLiteKGStorage
from democrai.core.runtime.foundation.paths import get_data_dir
from democrai.core.infrastructure.database.preferences import get_preference
from democrai.core.infrastructure.storage.errors import ProviderConfigError


class KGStoreFactory:
    @staticmethod
    def get_provider(provider_type: str = "sqlite", **kwargs) -> KGStorageProvider:
        if provider_type == "ladybug":
            db_path = kwargs.get("db_path", os.path.join(get_data_dir(), "kg.lbug"))
            return LadybugKGStorage(cast(str, db_path))
        if provider_type == "sqlite":
            db_path = kwargs.get("db_path", os.path.join(get_data_dir(), "kg.sqlite"))
            return SQLiteKGStorage(cast(str, db_path))
        if provider_type == "neo4j":
            uri = kwargs.get("uri")
            user = kwargs.get("user")
            password = kwargs.get("password")
            if not all([uri, user, password]):
                raise ProviderConfigError("Neo4j requires uri, user, and password.")
            return Neo4jKGStorage(cast(str, uri), cast(str, user), cast(str, password))
        raise ProviderConfigError(f"Unknown KG provider type: {provider_type}")

    @staticmethod
    def get_store(store_type: str = "sqlite", **kwargs) -> KGStorageProvider:
        # Backward-compatible alias.
        return KGStoreFactory.get_provider(store_type, **kwargs)

    @classmethod
    def create_default(cls) -> KGStorageProvider:
        """
        Creates a KGStore based on preferences in democrai.db.
        """
        store_type = get_preference("kg_storage_type", "sqlite")
        params_str = get_preference("kg_storage_params", "{}")
        try:
            params: dict[str, Any] = json.loads(params_str)
        except (json.JSONDecodeError, TypeError):
            params = {}
        if not isinstance(params, dict):
            params = {}

        return cls.get_provider(store_type, **params)
