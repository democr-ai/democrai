import asyncio
from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.runtime import invocation as invocation_mod
from democrai.core.application.ai.engine.schemas.runtime import (
    EngineMethodResponse,
    EngineStreamFinal,
    EngineUsage,
)


class _Provider:
    engine_row_id = 1
    model_registry_id = 2
    engine_id = "test"
    config = {"model": "m"}

    def __init__(self, error: BaseException | None = None):
        self.error = error

    def _invoke(self, method, payload):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(usage=None)


@pytest.mark.asyncio
async def test_invoke_with_usage_preserves_engine_error_when_usage_record_fails(monkeypatch):
    monkeypatch.setattr(
        invocation_mod,
        "record_usage_or_fail",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("usage_failed")),
    )
    monkeypatch.setattr(invocation_mod, "_log_usage_persistence_failure", lambda: None)

    with pytest.raises(ValueError, match="engine_failed"):
        await invocation_mod.invoke_with_usage(
            _Provider(error=ValueError("engine_failed")),
            "generate_completion",
            {},
        )


@pytest.mark.asyncio
async def test_invoke_with_usage_raises_usage_error_when_engine_succeeds(monkeypatch):
    monkeypatch.setattr(
        invocation_mod,
        "record_usage_or_fail",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("usage_failed")),
    )

    with pytest.raises(RuntimeError, match="usage_failed"):
        await invocation_mod.invoke_with_usage(
            _Provider(),
            "generate_completion",
            {},
        )


@pytest.mark.asyncio
async def test_invoke_with_usage_records_cancelled_request(monkeypatch):
    calls = []
    monkeypatch.setattr(
        invocation_mod,
        "record_usage_or_fail",
        lambda *args, **kwargs: calls.append(kwargs),
    )

    with pytest.raises(asyncio.CancelledError):
        await invocation_mod.invoke_with_usage(
            _Provider(error=asyncio.CancelledError()),
            "generate_completion",
            {},
        )

    assert calls[0]["success"] is False
    assert calls[0]["error"] == "request_cancelled"


@pytest.mark.asyncio
async def test_invoke_stream_with_usage_uses_provider_stream_final_without_duplicate(monkeypatch):
    calls = []
    monkeypatch.setattr(
        invocation_mod,
        "record_usage_or_fail",
        lambda *args, **kwargs: calls.append(kwargs),
    )

    class Provider(_Provider):
        async def _invoke_stream(self, method, payload):
            yield b"audio"
            yield EngineStreamFinal(
                usage=EngineUsage(
                    prompt_tokens=7,
                    completion_tokens=0,
                    total_tokens=7,
                ),
                metadata={"usage_source": "tokenizer"},
            )

    items = [
        item
        async for item in invocation_mod.invoke_stream_with_usage(
            Provider(),
            "synthesize_stream",
            {"text": "hello"},
        )
    ]

    finals = [item for item in items if isinstance(item, EngineStreamFinal)]
    assert items[0] == b"audio"
    assert len(finals) == 1
    assert finals[0].usage.prompt_tokens == 7
    assert finals[0].usage.completion_tokens == 0
    assert finals[0].usage.total_tokens == 7
    assert calls[0]["result"] == items


@pytest.mark.asyncio
async def test_parler_stream_exposes_provider_tokenizer_usage(monkeypatch):
    from engines.parler.engine import ParlerEngine

    async def fake_synthesize(self, text, options):
        return {
            "data": b"audio",
            "usage": {
                "prompt_tokens": 9,
                "completion_tokens": 0,
                "total_tokens": 9,
            },
            "usage_metadata": {
                "usage_source": "tokenizer",
                "usage_calculation": "engines.parler.engine.ParlerEngine._token_count",
            },
        }

    monkeypatch.setattr(ParlerEngine, "synthesize", fake_synthesize)
    engine = object.__new__(ParlerEngine)

    items = [
        item
        async for item in engine.synthesize_stream(
            "hello",
            SimpleNamespace(voice="voice"),
        )
    ]

    assert items[0] == b"audio"
    assert isinstance(items[1], EngineStreamFinal)
    assert items[1].usage.prompt_tokens == 9
    assert items[1].usage.completion_tokens == 0
    assert items[1].usage.total_tokens == 9
    assert items[1].duration_ms > 0
    assert items[1].tokens_per_second > 0
    assert items[1].metadata["usage_source"] == "tokenizer"


@pytest.mark.asyncio
async def test_qwen_tts_stream_exposes_provider_tokenizer_usage(monkeypatch):
    from engines.qwen_tts.engine import QwenTTSEngine

    async def fake_synthesize(self, text, options):
        return {
            "data": b"audio",
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 0,
                "total_tokens": 11,
            },
            "usage_metadata": {
                "usage_source": "tokenizer",
                "usage_calculation": "engines.qwen_tts.engine.QwenTTSEngine._usage_prompt_tokens",
            },
        }

    monkeypatch.setattr(QwenTTSEngine, "synthesize", fake_synthesize)
    engine = object.__new__(QwenTTSEngine)

    items = [
        item
        async for item in engine.synthesize_stream(
            "hello",
            SimpleNamespace(voice="voice"),
        )
    ]

    assert items[0] == b"audio"
    assert isinstance(items[1], EngineStreamFinal)
    assert items[1].usage.prompt_tokens == 11
    assert items[1].usage.completion_tokens == 0
    assert items[1].usage.total_tokens == 11
    assert items[1].duration_ms > 0
    assert items[1].tokens_per_second > 0
    assert items[1].metadata["usage_source"] == "tokenizer"


@pytest.mark.asyncio
async def test_openai_tts_synthesize_reports_speech_usage(monkeypatch):
    from engines.openai_tts import engine as openai_tts_mod
    from engines.openai_tts.engine import OpenAITTSEngine

    calls = []

    class _Speech:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(content=b"audio-bytes")

    class _Audio:
        speech = _Speech()

    class _OpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.audio = _Audio()

    monkeypatch.setattr(
        openai_tts_mod,
        "ensure_import",
        lambda module, *args, **kwargs: SimpleNamespace(AsyncOpenAI=_OpenAI),
    )

    engine = OpenAITTSEngine({"api_key": "secret", "model": "tts-model"})
    result = await engine.synthesize(
        "hello",
        SimpleNamespace(voice="alloy", speed=1.0, response_format="mp3", model=None),
    )

    assert calls == [
        {
            "model": "tts-model",
            "voice": "alloy",
            "input": "hello",
            "speed": 1.0,
            "response_format": "mp3",
        }
    ]
    assert result["data"] == b"audio-bytes"
    assert result["usage"] == {"input_characters": 5, "audio_bytes": 11}
    assert result["usage_metadata"]["usage_source"] == "local"


def test_transcribe_fallback_counts_only_output_tokens():
    usage, metadata = invocation_mod._usage_for_result(
        provider=_Provider(),
        method="transcribe",
        payload={"audio_data": b"not-a-wav"},
        result={
            "text": "hello, world",
            "duration": 120.0,
        },
        duration_ms=1000.0,
        metadata={},
        metadata_from_result=None,
    )

    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 3
    assert usage.total_tokens == 3
    assert metadata["usage_source"] == "calculated"
    assert metadata["usage_calculation"] == "runtime.invocation.text_regex_output_tokens"


def test_yolo_visual_usage_method_counts_tiles_not_pixels():
    from engines.yolo.engine import YoloEngine

    engine = object.__new__(YoloEngine)
    engine._model_weight_mb = 12.0

    result = engine._with_visual_metadata(
        {"xyxy": [[0, 0, 1, 1], [1, 1, 2, 2]], "confidence": [], "class_id": []},
        frame=SimpleNamespace(shape=(1080, 1920, 3)),
        media_kind="image",
        sampled_frame_count=1,
    )

    assert result["usage"] == {
        "prompt_tokens": 8,
        "completion_tokens": 2,
        "total_tokens": 10,
    }
    assert engine._usage_for_method(method="detect", payload={}, result=result) == (8, 2, 10)
    assert result["usage_calculation"] == "engines.yolo.visual_tiles_plus_detections"

    usage, metadata = invocation_mod._usage_for_result(
        provider=engine,
        method="detect",
        payload={},
        result=result,
        duration_ms=1000.0,
        metadata={},
        metadata_from_result=None,
    )
    assert usage.prompt_tokens == 8
    assert usage.completion_tokens == 2
    assert usage.total_tokens == 10
    assert metadata["usage_calculation"] == "engines.yolo.visual_tiles_plus_detections"


def test_yolo_visual_usage_is_recorded_for_persistence(monkeypatch):
    from engines.yolo.engine import YoloEngine

    engine = object.__new__(YoloEngine)
    engine._model_weight_mb = 12.0
    engine.engine_row_id = 11
    engine.model_registry_id = 22
    engine.engine_id = "yolo"
    engine.config = {"model": "yolo11s.pt"}
    result = engine._with_visual_metadata(
        {"xyxy": [[0, 0, 1, 1], [1, 1, 2, 2]], "confidence": [], "class_id": []},
        frame=SimpleNamespace(shape=(1080, 1920, 3)),
        media_kind="image",
        sampled_frame_count=1,
    )
    response = invocation_mod._method_response(
        provider=engine,
        method="detect",
        payload={},
        result=result,
        duration_ms=1000.0,
        metadata={},
        metadata_from_result=None,
    )
    assert isinstance(response, EngineMethodResponse)

    calls = []
    import democrai.core.application.observability.service as observability_mod

    monkeypatch.setattr(
        observability_mod.observability_service,
        "record_ai_model_usage",
        lambda **kwargs: calls.append(kwargs) or {"id": 1},
    )

    invocation_mod.record_usage_or_fail(
        engine,
        method="detect",
        result=response,
        duration_ms=1000.0,
        success=True,
        error=None,
        metadata={},
    )

    assert calls[0]["prompt_tokens"] == 8
    assert calls[0]["completion_tokens"] == 2
    assert calls[0]["total_tokens"] == 10
    assert calls[0]["metadata"]["usage_calculation"] == "engines.yolo.visual_tiles_plus_detections"


@pytest.mark.asyncio
async def test_whisper_transcribe_exposes_provider_tokenizer_usage(monkeypatch):
    from engines.whisper import engine as whisper_mod
    from engines.whisper.engine import WhisperEngine

    class WhisperModel:
        def __init__(self, *args, **kwargs):
            self.hf_tokenizer = object()
            self.model = SimpleNamespace(is_multilingual=True)

        def transcribe(self, audio_file, *, language, beam_size):
            assert language == "it"
            assert beam_size == 5
            return (
                [SimpleNamespace(text="ciao"), SimpleNamespace(text=" mondo")],
                SimpleNamespace(language="it", duration=1.5),
            )

    class Tokenizer:
        def __init__(self, tokenizer, multilingual, *, task, language):
            assert multilingual is True
            assert task == "transcribe"
            assert language == "it"

        def encode(self, text):
            assert text == "ciao mondo"
            return [1, 2]

    def fake_ensure_import(module, *, dependency_key=None):
        if module == "faster_whisper":
            return SimpleNamespace(WhisperModel=WhisperModel)
        if module == "faster_whisper.tokenizer":
            return SimpleNamespace(Tokenizer=Tokenizer)
        raise AssertionError(module)

    monkeypatch.setattr(whisper_mod, "ensure_import", fake_ensure_import)

    engine = WhisperEngine({"model": "base", "language": "it"})
    result = await engine.transcribe(b"audio")

    assert result["text"] == "ciao mondo"
    assert result["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 2,
        "total_tokens": 2,
    }
    assert result["usage_metadata"]["usage_source"] == "tokenizer"


def test_qwen_tts_uses_provider_processor_tokenizer(monkeypatch):
    from engines.qwen_tts import engine as qwen_mod
    from engines.qwen_tts.engine import QwenTTSEngine

    tokenizer = object()

    class Qwen3TTSModel:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return SimpleNamespace(
                processor=SimpleNamespace(tokenizer=tokenizer),
            )

    def fake_ensure_import(module, *, dependency_key=None):
        if module == "torch":
            return SimpleNamespace(
                bfloat16=object(),
                float32=object(),
                cuda=SimpleNamespace(is_available=lambda: False),
            )
        if module == "qwen_tts":
            return SimpleNamespace(Qwen3TTSModel=Qwen3TTSModel)
        if module == "soundfile":
            return object()
        raise AssertionError(module)

    monkeypatch.setattr(qwen_mod, "ensure_import", fake_ensure_import)
    monkeypatch.setattr(
        QwenTTSEngine,
        "_patch_sox_transformer_if_needed",
        lambda self: None,
    )

    engine = QwenTTSEngine({"model": "qwen/model", "tokenizer_ref": "qwen/tokenizer"})

    assert engine.tokenizer is tokenizer
