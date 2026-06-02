from __future__ import annotations

from abc import ABC, abstractmethod


class ObsExporter(ABC):
    """Optional side-effect exporter for observability events."""

    @abstractmethod
    def export(self, event_payload: dict) -> None:
        """Exports a serialized event payload."""
