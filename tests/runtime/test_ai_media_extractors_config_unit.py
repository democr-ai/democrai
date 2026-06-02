from __future__ import annotations

import pytest

from extractors.ai_audio.extractor import AIAudioExtractor
from extractors.ai_image.extractor import AIImageExtractor


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
