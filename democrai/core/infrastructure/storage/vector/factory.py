import os
import json
from typing import Any, cast
from .base import VectorProvider
from .sqlite_vec_store import SQLiteVecVectorProvider, sqlite_vec_available
from .milvus_store import MilvusVectorProvider
from .pinecone_store import PineconeVectorProvider
from .composite import CompositeVectorStore, WritePolicy, ReadPolicy
from democrai.core.runtime.foundation.paths import get_data_dir
from democrai.core.infrastructure.database.preferences import get_preference
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.infrastructure.storage.errors import (
    ProviderConfigError,
    ProviderNotAvailableError,
)


class VectorStoreFactory:
    @staticmethod
    def _build_local_provider(**kwargs: Any) -> VectorProvider:
        db_path = kwargs.get("db_path", os.path.join(get_data_dir(), "vector.db"))
        index_prefix = kwargs.get("index_prefix", "democrai")

        ok, reason = sqlite_vec_available()
        if not ok:
            raise ProviderNotAvailableError(
                f"sqlite-vec is required for local vector storage but is unavailable: {reason}"
            )
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.info("[Vector] Using sqlite-vec as local vector provider.")
        return SQLiteVecVectorProvider(db_path, index_prefix=index_prefix)

    @staticmethod
    def get_provider(
        provider_type: str = "sqlite-vec", **kwargs: Any
    ) -> VectorProvider:
        if provider_type == "sqlite-vec":
            return VectorStoreFactory._build_local_provider(**kwargs)
        if provider_type == "milvus":
            host = kwargs.get("host", "localhost")
            port = kwargs.get("port", 19530)
            user = kwargs.get("user", "")
            password = kwargs.get("password", "")
            index_prefix = kwargs.get("index_prefix", "democrai")
            return MilvusVectorProvider(
                host,
                port,
                user,
                password,
                index_prefix=index_prefix,
            )
        if provider_type == "pinecone":
            api_key = kwargs.get("api_key", "")
            cloud = kwargs.get("cloud", "aws")
            region = kwargs.get("region", "us-east-1")
            index_prefix = kwargs.get("index_prefix", "democrai")
            if not api_key:
                raise ProviderConfigError(
                    "storage.vector.api_key is required when storage.vector.type=pinecone"
                )
            return PineconeVectorProvider(
                api_key=api_key,
                cloud=cloud,
                region=region,
                index_prefix=index_prefix,
            )
        raise ProviderConfigError(f"Unknown vector provider type: {provider_type}")

    @staticmethod
    def create_composite(
        primary_config: dict[str, Any],
        secondary_config: dict[str, Any],
        **kwargs: Any,
    ) -> CompositeVectorStore:
        primary = VectorStoreFactory.get_provider(
            cast(str, primary_config.get("type", "sqlite-vec")),
            **primary_config.get("params", {}),
        )
        secondary = VectorStoreFactory.get_provider(
            cast(str, secondary_config.get("type", "sqlite-vec")),
            **secondary_config.get("params", {}),
        )

        return CompositeVectorStore(
            primary=primary,
            secondary=secondary,
            write_policy=kwargs.get("write_policy", WritePolicy.DUAL_WRITE),
            read_policy=kwargs.get("read_policy", ReadPolicy.PREFER_PRIMARY),
        )

    @classmethod
    def create_default(cls) -> VectorProvider:
        """
        Creates a VectorProvider based on preferences in democrai.db.
        Initializes a CompositeVectorStore if both primary and secondary are configured.
        """
        provider_type = get_preference("vector_storage_type", "sqlite-vec")
        params_str = get_preference("vector_storage_params", "{}")
        try:
            params: dict[str, Any] = json.loads(params_str)
        except json.JSONDecodeError:
            params = {}

        # Support for composite preference
        is_composite = (
            get_preference("vector_storage_composite", "false").lower() == "true"
        )
        if is_composite:
            primary_cfg = json.loads(
                get_preference(
                    "vector_storage_primary", '{"type":"milvus","params":{}}'
                )
            )
            secondary_cfg = json.loads(
                get_preference(
                    "vector_storage_secondary", '{"type":"sqlite-vec","params":{}}'
                )
            )
            return cls.create_composite(primary_cfg, secondary_cfg)

        return cls.get_provider(provider_type, **params)
