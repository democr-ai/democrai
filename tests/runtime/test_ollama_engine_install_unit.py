from __future__ import annotations

from types import SimpleNamespace


def test_ollama_install_uses_declared_package(monkeypatch):
    engine_mod = __import__("engines.ollama.engine", fromlist=["OllamaEngine"])
    calls = []

    monkeypatch.setattr(
        engine_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)),
    )

    engine_mod.OllamaEngine._install(force=True)

    assert calls == [
        (["ollama==0.6.2"], {"modules": ["ollama"], "force": True}),
    ]


def test_ollama_ready_checks_declared_runtime(monkeypatch):
    engine_mod = __import__("engines.ollama.engine", fromlist=["OllamaEngine"])

    monkeypatch.setattr(engine_mod.OllamaEngine, "_missing_modules", lambda *args: [])
    monkeypatch.setattr(
        engine_mod.OllamaEngine,
        "_default_missing_shared",
        classmethod(lambda cls: []),
    )
    monkeypatch.setattr(engine_mod, "_ollama_version_matches", lambda: True)
    monkeypatch.setattr(engine_mod, "_ollama_runtime_symbols_available", lambda: True)

    result = engine_mod.OllamaEngine._check_ready()

    assert result["ready"] is True
    assert result["missing_local"] == []


def test_ollama_runtime_symbol_check_requires_async_client(monkeypatch):
    engine_mod = __import__("engines.ollama.engine", fromlist=["OllamaEngine"])

    class _AsyncClient:
        def __init__(self, **kwargs):
            pass

        async def list(self):
            return {}

        async def show(self, **kwargs):
            return {}

        async def chat(self, **kwargs):
            return {}

        async def embed(self, **kwargs):
            return {}

    monkeypatch.setattr(
        engine_mod,
        "importlib",
        SimpleNamespace(import_module=lambda name: SimpleNamespace(AsyncClient=_AsyncClient)),
    )

    assert engine_mod._ollama_runtime_symbols_available()
