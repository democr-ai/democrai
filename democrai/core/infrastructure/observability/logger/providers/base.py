import logging
from abc import ABC, abstractmethod
from typing import List


class LogProvider(ABC):
    """Interface for logging providers."""

    @abstractmethod
    def get_handlers(self, name: str) -> List[logging.Handler]:
        """Returns a list of logging handlers for the given logger name."""
        pass
