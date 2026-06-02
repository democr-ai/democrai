from abc import ABC, abstractmethod
from typing import Any


class DataStorageProvider(ABC):
    """Interface for secondary relational data storage."""

    @abstractmethod
    def get_session(self) -> Any:
        """Returns a database session."""
        pass

    @abstractmethod
    def run_migrations(self) -> None:
        """Runs migrations for this domain."""
        pass
