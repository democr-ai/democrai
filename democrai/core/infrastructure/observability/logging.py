from __future__ import annotations


class LoggerAdapter:
    """Facade over existing logger implementation."""

    def __init__(self, logger=None) -> None:
        self.logger = logger

    def info(self, message: str, channel: str = "core") -> None:
        if self.logger:
            self.logger.info(message, channel)
