from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional


class BusProvider(ABC):
    """Interface for bidirectional communication bus."""

    on_message: Optional[Callable[[Any, Dict[str, Any]], None]] = None
    on_disconnect: Optional[Callable[[Any], None]] = None

    @abstractmethod
    def start(self) -> None:
        """Starts the bus listener."""

    @abstractmethod
    def stop(self) -> None:
        """Stops the bus listener."""

    @abstractmethod
    def send(self, client_id: Any, message: Dict[str, Any]) -> None:
        """Sends a message to a specific client."""

    @abstractmethod
    def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcasts a message to all connected clients."""
