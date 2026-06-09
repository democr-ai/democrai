from __future__ import annotations

import pytest

from extractors.ai_audio.extractor import AIAudioExtractor
from extractors.ai_audio.extractor import _transcription_payload
from extractors.ai_image.extractor import AIImageExtractor
from democrai.core.application.ai.engine.schemas.runtime import EngineMethodResponse
from democrai.sdk.extractors import ExtractorSource


def test_ai_image_numeric_config_uses_defaults_for_blank_values():
    extractor = AIImageExtractor(
        {
            "temperature": "",
            "top_p": " ",
            "max_tokens": "",
            "chunk_size": "",
            "chunk_overlap": "",
        }
    )

    assert extractor._temperature() == 0.0
    assert extractor._top_p() == 1.0
    assert extractor._max_tokens() == 900
    assert extractor._chunk_size() == 1200
    assert extractor._chunk_overlap() == 150


def test_ai_image_numeric_config_reports_invalid_values():
    extractor = AIImageExtractor({"temperature": "hot"})

    with pytest.raises(ValueError, match="invalid_ai_image_temperature"):
        extractor._temperature()


def test_ai_audio_chunk_config_uses_defaults_for_blank_values():
    extractor = AIAudioExtractor({"chunk_size": "", "chunk_overlap": " "})

    assert extractor._chunk_size() == 1200
    assert extractor._chunk_overlap() == 150


def test_ai_audio_chunk_config_reports_invalid_values():
    extractor = AIAudioExtractor({"chunk_size": "large"})

    with pytest.raises(ValueError, match="invalid_ai_audio_chunk_size"):
        extractor._chunk_size()


def test_ai_audio_transcription_payload_unwraps_engine_method_response():
    payload = _transcription_payload(
        EngineMethodResponse(
            result={
                "text": "hello audio",
                "language": "en",
                "duration": 1.5,
                "segments": [{"start": 0, "end": 1.5}],
            },
        )
    )

    assert {key: payload[key] for key in ("text", "language", "duration", "segments")} == {
        "text": "hello audio",
        "language": "en",
        "duration": 1.5,
        "segments": [{"start": 0, "end": 1.5}],
    }


def test_ai_audio_transcription_payload_unwraps_serialized_envelope():
    payload = _transcription_payload(
        {
            "__model__": "EngineMethodResponse",
            "value": {
                "result": {
                    "text": "nested transcript",
                    "language": "",
                    "segments": None,
                },
                "stats": {"total_tokens": 2},
            },
        }
    )

    assert {key: payload[key] for key in ("text", "language", "duration", "segments")} == {
        "text": "nested transcript",
        "language": None,
        "duration": None,
        "segments": [],
    }


def test_ai_audio_empty_transcription_returns_empty_result(monkeypatch):
    extractor = AIAudioExtractor({})

    async def _empty_transcription(_source):
        return {"text": "", "language": "en", "duration": 0.5, "segments": []}

    monkeypatch.setattr(extractor, "_transcribe_audio", _empty_transcription)

    result = extractor._extract_source(
        ExtractorSource(
            name="silence.wav",
            source="media/silence.wav",
            mime_type="audio/wav",
            data=b"audio",
        )
    )

    assert result.markdown_content == ""
    assert result.chunks == []
    assert result.structure["empty_transcription"] is True
