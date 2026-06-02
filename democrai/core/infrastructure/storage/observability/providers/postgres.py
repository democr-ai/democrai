from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from democrai.core.infrastructure.storage.observability.providers.base import ObsStorageProvider
from democrai.core.infrastructure.storage.observability.providers.sqlalchemy_obs_provider import (
    SQLAlchemyObsProviderMixin,
)


class PostgresObsStorage(SQLAlchemyObsProviderMixin, ObsStorageProvider):
    """Postgres implementation for observability event storage."""

    def __init__(self, connection_url: str):
        self.url = connection_url
        self.engine = create_engine(connection_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def _session(self):
        session = self.SessionLocal()
        session.info["skip_observability_audit"] = True
        return session
