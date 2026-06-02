from __future__ import annotations

from democrai.core.infrastructure.storage.errors import ProviderConfigError
from democrai.core.infrastructure.storage.observability.providers.base import ObsStorageProvider

from .clickhouse_parts.audit_llm import ClickHouseAuditLLMMixin
from .clickhouse_parts.common import ClickHouseCommonMixin
from .clickhouse_parts.events import ClickHouseEventsMixin
from .clickhouse_parts.outbox import ClickHouseOutboxMixin


class ClickHouseObsStorage(
    ClickHouseCommonMixin,
    ClickHouseEventsMixin,
    ClickHouseAuditLLMMixin,
    ClickHouseOutboxMixin,
    ObsStorageProvider,
):
    """ClickHouse implementation for append-only observability analytics."""

    def __init__(self, connection_url: str):
        if not connection_url:
            raise ProviderConfigError("ClickHouse requires connection_url")
        self.url = connection_url
        self._client = self._build_client(connection_url)
        self.database = self._resolve_database(connection_url)
