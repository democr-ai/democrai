from __future__ import annotations

from types import SimpleNamespace


def test_edge_tts_install_uses_declared_package(monkeypatch):
    engine_mod = __import__("engines.edge.engine", fromlist=["EdgeEngine"])
    calls = []

    monkeypatch.setattr(
        engine_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)),
    )

    engine_mod.EdgeEngine._install(force=True)

    assert calls == [
        (["edge-tts==7.2.8"], {"modules": ["edge_tts"], "force": True}),
    ]


def test_edge_tts_ready_checks_declared_runtime(monkeypatch):
    engine_mod = __import__("engines.edge.engine", fromlist=["EdgeEngine"])

    monkeypatch.setattr(engine_mod.EdgeEngine, "_missing_modules", lambda *args: [])
    monkeypatch.setattr(
        engine_mod.EdgeEngine,
        "_default_missing_shared",
        classmethod(lambda cls: []),
    )
    monkeypatch.setattr(engine_mod, "_edge_tts_version_matches", lambda: True)
    monkeypatch.setattr(engine_mod, "_edge_tts_runtime_symbols_available", lambda: True)

    result = engine_mod.EdgeEngine._check_ready()

    assert result["ready"] is True
    assert result["missing_local"] == []


def test_edge_tts_runtime_symbol_check_requires_communicate_stream(monkeypatch):
    engine_mod = __import__("engines.edge.engine", fromlist=["EdgeEngine"])

    class _Communicate:
        def __init__(self, *args, **kwargs):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b""}

    monkeypatch.setattr(
        engine_mod,
        "importlib",
        SimpleNamespace(import_module=lambda name: SimpleNamespace(Communicate=_Communicate)),
    )

    assert engine_mod._edge_tts_runtime_symbols_available()
