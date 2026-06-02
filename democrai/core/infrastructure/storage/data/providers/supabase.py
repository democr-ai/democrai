from __future__ import annotations

from .postgres import PostgresDataStorage


class SupabaseDataStorage(PostgresDataStorage):
    """Supabase Postgres implementation for secondary data storage."""

    def __init__(self, connection_url: str):
        super().__init__(connection_url)
