from typing import List, Optional
from pydantic import BaseModel, Field


class TranscriptionResponse(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    segments: Optional[List[dict]] = None  # Detailed timing if needed


class SpeechUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    input_characters: int = 0
    audio_bytes: int = 0


class SpeechResponse(BaseModel):
    data: bytes
    content_type: str = "audio/mpeg"
    duration: Optional[float] = None
    usage: SpeechUsage = Field(default_factory=SpeechUsage)
    tokens_per_second: float = 0.0


class TTSOptions(BaseModel):
    voice: str
    model: Optional[str] = None
    speed: float = 1.0
    wpm: Optional[int] = None
    pitch: int = 50
    amplitude: int = 100
    word_gap: int = 0
    response_format: str = "wav"
