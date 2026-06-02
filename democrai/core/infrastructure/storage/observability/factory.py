from .exporters.otlp import OtlpObsExporter
from .providers.clickhouse import ClickHouseObsStorage
from .providers.postgres import PostgresObsStorage
from .providers.sqlite import SqliteObsStorage
from democrai.core.infrastructure.storage.errors import ProviderConfigError
from .store import ObservabilityStore
from typing import Any
from democrai.core.platform.utils.normalize import normalize_bool


class ObservabilityFactory:
    """Factory for creating observability storage providers."""

    @staticmethod
    def get_provider(
        provider_type: str = "sqlite", **kwargs: Any
    ) -> ObservabilityStore:
        """
        Returns an ObservabilityStore instance.
        Valid types: 'sqlite', 'postgres', 'clickhouse'
        """
        exporters = []
        otlp_enabled = normalize_bool(
            kwargs.get("otlp_enabled", False),
            default=bool(kwargs.get("otlp_enabled", False)),
        )
        if otlp_enabled:
            endpoint = kwargs.get("otlp_endpoint")
            if endpoint is None:
                raise ProviderConfigError("OTLP exporter requires otlp_endpoint")
            exporters.append(
                OtlpObsExporter(
                    endpoint,
                    insecure=normalize_bool(
                        kwargs.get("otlp_insecure", False),
                        default=bool(kwargs.get("otlp_insecure", False)),
                    ),
                    service_name=kwargs.get("otlp_service_name", "democrai"),
                )
            )

        if provider_type == "sqlite":
            db_path = kwargs.get("db_path")
            provider = SqliteObsStorage(db_path)
            return ObservabilityStore(provider=provider, exporters=exporters)
        if provider_type == "postgres":
            url = kwargs.get("connection_url")
            if url is None:
                raise ProviderConfigError("Postgres requires connection_url")
            provider = PostgresObsStorage(url)
            return ObservabilityStore(provider=provider, exporters=exporters)
        if provider_type == "clickhouse":
            url = kwargs.get("connection_url")
            if url is None:
                raise ProviderConfigError("ClickHouse requires connection_url")
            provider = ClickHouseObsStorage(url)
            return ObservabilityStore(provider=provider, exporters=exporters)
        raise ProviderConfigError(
            f"Unknown observability provider type: {provider_type}"
        )
