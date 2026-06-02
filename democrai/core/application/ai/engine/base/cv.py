from abc import ABC, abstractmethod
from typing import Any


class BaseCvProvider(ABC):
    """Base class for Computer vision providers."""

    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model")
        self.model_revision = config.get("model_revision")

    @abstractmethod
    def detect(*args, **kwargs) -> Any:
        pass

    @abstractmethod
    async def get_detections(*args, **kwargs) -> Any:
        pass
