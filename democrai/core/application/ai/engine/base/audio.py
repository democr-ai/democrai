from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from democrai.core.application.ai.engine.schemas.audio import (
    SpeechResponse,
    TranscriptionResponse,
    TTSOptions,
)


class BaseSTTProvider(ABC):
    """Base class for Speech-to-Text providers."""

    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model")
        self.model_revision = config.get("model_revision")

    @abstractmethod
    async def transcribe(
        self, audio_data: bytes, language: Optional[str] = None
    ) -> TranscriptionResponse:
        pass


class BaseTTSProvider(ABC):
    """Base class for Text-to-Speech providers."""

    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model")
        self.model_revision = config.get("model_revision")

    @abstractmethod
    async def synthesize(self, text: str, options: TTSOptions) -> SpeechResponse:
        pass

    @abstractmethod
    async def synthesize_stream(
        self, text: str, options: TTSOptions
    ) -> AsyncGenerator[bytes, None]:
        pass
