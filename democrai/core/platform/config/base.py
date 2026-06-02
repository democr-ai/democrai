from abc import ABC, abstractmethod
from typing import Any


class ConfigProvider(ABC):
    """Interface for application configuration management."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieves a configuration value."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Sets a configuration value (volatile or persistent)."""
        pass

    @abstractmethod
    def save(self) -> None:
        """Persists the configuration to a storage medium."""
        pass
