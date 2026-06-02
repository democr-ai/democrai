from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.base import __getattr__ as ai_base_getattr
from democrai.core.application.ai.engine.base.audio import BaseSTTProvider, BaseTTSProvider
from democrai.core.application.ai.engine.base.cv import BaseCvProvider
from democrai.core.application.ai.engine.base.llm import LLMProvider, ai_call_context
from democrai.core.application.ai.engine.schemas.completion import CompletionOptions
from democrai.core.application.ai.engine.schemas.completion import CompletionResponse
from democrai.core.application.ai.engine.schemas.completion import CompletionUsage
from democrai.core.application.ai.engine.schemas.completion import StreamChunk
from democrai.core.application.ai.constants import methods_for_capabilities
from democrai.core.application.ai.models import __getattr__ as ai_models_getattr
from democrai.core.runtime.foundation.app import app_ctx
from democrai.sdk.templates import empty as template_empty
from democrai.sdk.templates import full as template_full
from democrai.core.platform.ui import tags as tags_mod


@pytest.fixture(autouse=True)
def _app_logger():
    ctx = app_ctx()
    previous = getattr(ctx, "logger", None)
    ctx.logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    )
    try:
        yield
    finally:
        ctx.logger = previous


class _CvImpl(BaseCvProvider):
    def detect(self, *_args, **_kwargs):
        return {"ok": True}

    async def get_detections(self, *_args, **_kwargs):
        return []


class _SttImpl(BaseSTTProvider):
    async def transcribe(self, audio_data: bytes, language=None):
        return {"text": "x", "lang": language, "size": len(audio_data)}


class _TtsImpl(BaseTTSProvider):
    async def synthesize(self, text: str, options):
        return {"text": text, "options": options}

    async def synthesize_stream(self, text: str, options):
        del options
        yield text.encode("utf-8")


class _LlmImpl(LLMProvider):
    async def _generate_completion(self, messages, options):
        self.last_completion_call = {"messages": messages, "options": options}
        return CompletionResponse(id="completion-1", content="done")

    async def _generate_stream(self, messages, options):
        self.last_stream_call = {"messages": messages, "options": options}
        yield StreamChunk(id="chunk-1", delta="done")


class _MaxTokenLlmImpl(LLMProvider):
    async def _generate_completion(self, messages, options):
        return CompletionResponse(
            id="completion-1",
            content="done",
            finish_reason="length",
            usage=CompletionUsage(
                prompt_tokens=1,
                completion_tokens=options.max_tokens,
                total_tokens=options.max_tokens + 1,
            ),
        )

    async def _generate_stream(self, messages, options):
        yield StreamChunk(
            id="chunk-1",
            finish_reason="length",
            completion_tokens=options.max_tokens,
            total_tokens=options.max_tokens,
        )


class _EmbeddingLlmImpl(_LlmImpl):
    async def _embed_texts(self, texts):
        return [[float(len(text))] for text in texts]

    async def _rerank(self, query, texts, options=None):
        from democrai.core.application.ai.engine.schemas.completion import RerankResult

        return [
            RerankResult(index=index, text=text, score=float(text == query))
            for index, text in enumerate(texts)
        ]

    async def _classify(self, texts, options=None):
        from democrai.core.application.ai.engine.schemas.completion import ClassificationResult

        return [
            ClassificationResult(label="ok", score=1.0, scores={"ok": 1.0})
            for _text in texts
        ]

    async def _extract_tokens(self, text, options=None):
        from democrai.core.application.ai.engine.schemas.completion import TokenExtractionResult

        return [TokenExtractionResult(token=text, label="TEXT", score=1.0)]


def test_templates_build_component_trees():
    empty_components, empty_dimensions = template_empty.template()
    full_components, full_dimensions = template_full.template()

    assert empty_dimensions == "window"
    assert full_dimensions == "full"
    assert any(c.get("id") == "content_area_host" for c in empty_components)
    assert any(c.get("id") == "main_sidebar" for c in full_components)


def test_ui_tag_constants_are_exposed():
    assert tags_mod.APP_MAIN_LIST_TAG == "appmainlist"
    assert tags_mod.APP_BOTTOM_MAIN_LIST_TAG == "appbottommainlist"
    assert tags_mod.APP_NOTIFICATIONS_TAG == "notifications"
    assert "APP_MAIN_LIST_TAG" in tags_mod.__all__


def test_ai_capability_methods_include_text_operations():
    assert methods_for_capabilities(["embedding"]) == ["embed_texts"]
    assert methods_for_capabilities(["rerank", "classify", "ner"]) == [
        "rerank",
        "classify",
        "extract_tokens",
    ]


@pytest.mark.asyncio
async def test_ai_base_contracts_and_default_methods():
    cv = _CvImpl({"model": "m1", "model_revision": "r1"})
    stt = _SttImpl({"model": "m2", "model_revision": "r2"})
    tts = _TtsImpl({"model": "m3", "model_revision": "r3"})
    llm = _LlmImpl()
    llm.model_name = "demo-llm"

    assert cv.model_name == "m1"
    assert cv.detect()["ok"] is True
    assert (await cv.get_detections()) == []

    assert stt.model_revision == "r2"
    assert (await stt.transcribe(b"abc"))["size"] == 3

    assert (await tts.synthesize("hi", {}))["text"] == "hi"
    chunks = [chunk async for chunk in tts.synthesize_stream("hi", {})]
    assert chunks == [b"hi"]

    assert llm.get_info()["provider"] == "_LlmImpl"
    assert llm.get_info()["model"] == "demo-llm"
    with pytest.raises(NotImplementedError):
        await llm.embed_texts(["a"])
    with pytest.raises(NotImplementedError):
        await llm.rerank("a", ["a"])
    with pytest.raises(NotImplementedError):
        await llm.classify(["a"])
    with pytest.raises(NotImplementedError):
        await llm.extract_tokens("a")
    with pytest.raises(NotImplementedError):
        await llm.download_model("m")


@pytest.mark.asyncio
async def test_llm_provider_records_completion_telemetry(monkeypatch):
    calls = []
    obs_mod = __import__(
        "democrai.core.application.observability.service",
        fromlist=["observability_service"],
    )
    monkeypatch.setattr(
        obs_mod.observability_service,
        "record_ai_model_usage",
        lambda **kwargs: calls.append(kwargs),
    )
    llm = _LlmImpl()
    llm._democrai_provider_name = "provider"
    llm._democrai_engine_name = "engine"
    llm._democrai_model_name = "model"
    llm._democrai_deployment_mode = "local"

    with ai_call_context(
        objective="chat",
        request_kind="unit_completion",
        agent_id="agent",
        metadata={"module_name": "system"},
    ):
        response = await llm.generate_completion([], CompletionOptions())

    assert response.content == "done"
    assert llm.last_completion_call["messages"] == []
    assert calls[0]["objective"] == "chat"
    assert calls[0]["provider"] == "provider"
    assert calls[0]["engine"] == "engine"
    assert calls[0]["model_name"] == "model"
    assert calls[0]["deployment_mode"] == "local"
    assert calls[0]["request_kind"] == "unit_completion"
    assert calls[0]["agent_id"] == "agent"
    assert calls[0]["success"] is True
    assert calls[0]["metadata"] == {"module_name": "system"}


@pytest.mark.asyncio
async def test_llm_provider_records_stream_telemetry(monkeypatch):
    calls = []
    obs_mod = __import__(
        "democrai.core.application.observability.service",
        fromlist=["observability_service"],
    )
    monkeypatch.setattr(
        obs_mod.observability_service,
        "record_ai_model_usage",
        lambda **kwargs: calls.append(kwargs),
    )
    llm = _LlmImpl()

    with ai_call_context(objective="chat", request_kind="unit_stream"):
        chunks = [chunk async for chunk in llm.generate_stream([], CompletionOptions())]

    assert llm.last_stream_call == {"messages": [], "options": CompletionOptions()}
    assert calls[0]["request_kind"] == "unit_stream"
    assert calls[0]["success"] is True
    assert calls[0]["metadata"] == {"chunks": 1}


@pytest.mark.asyncio
async def test_llm_provider_logs_max_output_tokens(monkeypatch):
    errors = []
    app_ctx().logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda message, **_kwargs: errors.append(message),
    )
    llm = _MaxTokenLlmImpl()
    llm._democrai_provider_name = "provider"

    await llm.generate_completion([], CompletionOptions(max_tokens=4))
    chunks = [
        chunk async for chunk in llm.generate_stream([], CompletionOptions(max_tokens=4))
    ]

    assert any(chunk.finish_reason == "length" for chunk in chunks)
    assert errors == [
        "[LLM] output reached max tokens provider tok: 4 comp_tokens: 4 reason: length\n"
    ]


@pytest.mark.asyncio
async def test_llm_provider_records_non_generation_telemetry(monkeypatch):
    calls = []
    obs_mod = __import__(
        "democrai.core.application.observability.service",
        fromlist=["observability_service"],
    )
    monkeypatch.setattr(
        obs_mod.observability_service,
        "record_ai_model_usage",
        lambda **kwargs: calls.append(kwargs),
    )
    llm = _EmbeddingLlmImpl()

    assert await llm.embed_texts(["ab"]) == [[2.0]]
    assert (await llm.rerank("a", ["a"]))[0].score == 1.0
    assert (await llm.classify(["x"]))[0].label == "ok"
    assert (await llm.extract_tokens("x"))[0].label == "TEXT"

    assert [call["request_kind"] for call in calls] == [
        "embedding",
        "rerank",
        "classification",
        "token_extraction",
    ]
    assert calls[0]["metadata"]["input_count"] == 1


def test_dynamic_getattr_for_ai_modules(monkeypatch):
    fake_catalog = SimpleNamespace(
        engine_model_source_modes=lambda: ["remote"],
        get_engine_model=lambda *_a, **_k: {"id": "x"},
        list_engine_models=lambda *_a, **_k: [],
        resolve_engine_model=lambda *_a, **_k: {"id": "y"},
    )
    fake_hw = SimpleNamespace(HardwareValidator=type("HardwareValidator", (), {}))
    fake_audio = SimpleNamespace(BaseSTTProvider=BaseSTTProvider, BaseTTSProvider=BaseTTSProvider)
    fake_cv = SimpleNamespace(BaseCvProvider=BaseCvProvider)
    fake_llm = SimpleNamespace(LLMProvider=LLMProvider)
    fake_engine = SimpleNamespace(BaseEngine=type("BaseEngine", (), {}))

    def _fake_import(module_name, package):
        mapping = {
            ".catalog": fake_catalog,
            ".hardware_compatibility": fake_hw,
            ".audio": fake_audio,
            ".cv": fake_cv,
            ".llm": fake_llm,
            ".engine": fake_engine,
        }
        return mapping[module_name]

    monkeypatch.setattr("democrai.core.application.ai.models.import_module", _fake_import)
    monkeypatch.setattr("democrai.core.application.ai.engine.base.import_module", _fake_import)

    assert ai_models_getattr("HardwareValidator").__name__ == "HardwareValidator"
    assert ai_models_getattr("get_engine_model")()["id"] == "x"
    with pytest.raises(AttributeError):
        ai_models_getattr("missing")

    assert ai_base_getattr("BaseCvProvider") is BaseCvProvider
    assert ai_base_getattr("LLMProvider") is LLMProvider
    with pytest.raises(AttributeError):
        ai_base_getattr("missing")
