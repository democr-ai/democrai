from abc import ABC, abstractmethod
from typing import Any


class PersistenceProvider(ABC):
    """Interface for database persistence and migrations."""

    @abstractmethod
    def get_session(self) -> Any:
        """Returns a database session."""
        pass

    @abstractmethod
    def run_migrations(self) -> None:
        """Runs database migrations."""
        pass

    @abstractmethod
    def get_url(self) -> str:
        """Returns the database connection URL."""
        pass
