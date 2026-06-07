from __future__ import annotations

from types import SimpleNamespace


def test_openai_sdk_engines_install_declared_package(monkeypatch):
    modules = [
        __import__("engines.openai.engine", fromlist=["OpenAIEngine"]),
        __import__("engines.openai_compatible.engine", fromlist=["OpenAICompatibleEngine"]),
        __import__("engines.openai_tts.engine", fromlist=["OpenAITTSEngine"]),
        __import__("engines.openai_whisper.engine", fromlist=["OpenAIWhisperEngine"]),
    ]
    classes = [
        modules[0].OpenAIEngine,
        modules[1].OpenAICompatibleEngine,
        modules[2].OpenAITTSEngine,
        modules[3].OpenAIWhisperEngine,
    ]
    calls = []

    for module in modules:
        monkeypatch.setattr(
            module,
            "install_python_packages",
            lambda packages, **kwargs: calls.append((packages, kwargs)),
        )

    for engine_cls in classes:
        engine_cls._install(force=True)

    assert calls == [
        (["openai==2.40.0"], {"modules": ["openai"], "force": True}),
        (["openai==2.40.0"], {"modules": ["openai"], "force": True}),
        (["openai==2.40.0"], {"modules": ["openai"], "force": True}),
        (["openai==2.40.0"], {"modules": ["openai"], "force": True}),
    ]


def test_openai_sdk_engines_ready_checks_declared_runtime(monkeypatch):
    cases = [
        (
            __import__("engines.openai.engine", fromlist=["OpenAIEngine"]),
            "OpenAIEngine",
            "_openai_version_matches",
            "_openai_runtime_symbols_available",
        ),
        (
            __import__("engines.openai_compatible.engine", fromlist=["OpenAICompatibleEngine"]),
            "OpenAICompatibleEngine",
            "_openai_version_matches",
            "_openai_runtime_symbols_available",
        ),
        (
            __import__("engines.openai_tts.engine", fromlist=["OpenAITTSEngine"]),
            "OpenAITTSEngine",
            "_openai_version_matches",
            "_openai_tts_runtime_symbols_available",
        ),
        (
            __import__("engines.openai_whisper.engine", fromlist=["OpenAIWhisperEngine"]),
            "OpenAIWhisperEngine",
            "_openai_version_matches",
            "_openai_stt_runtime_symbols_available",
        ),
    ]

    for module, class_name, version_name, symbols_name in cases:
        engine_cls = getattr(module, class_name)
        monkeypatch.setattr(engine_cls, "_missing_modules", lambda *args: [])
        monkeypatch.setattr(engine_cls, "_default_missing_shared", classmethod(lambda cls: []))
        monkeypatch.setattr(module, version_name, lambda: True)
        monkeypatch.setattr(module, symbols_name, lambda *args, **kwargs: True)

        result = engine_cls._check_ready()

        assert result["ready"] is True
        assert result["missing_local"] == []


def test_openai_sdk_symbol_check_requires_client_resources(monkeypatch):
    openai_mod = __import__("engines.openai.engine", fromlist=["OpenAIEngine"])

    class _OpenAI:
        def __init__(self, **kwargs):
            self.responses = object()
            self.embeddings = object()

    monkeypatch.setattr(
        openai_mod,
        "importlib",
        SimpleNamespace(import_module=lambda name: SimpleNamespace(AsyncOpenAI=_OpenAI)),
    )

    assert openai_mod._openai_runtime_symbols_available(
        responses=True,
        chat=False,
        embeddings=True,
        audio_speech=False,
        audio_transcriptions=False,
    )
