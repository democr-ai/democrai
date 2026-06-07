from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_engine_install_smoke_uses_engine_runtime_invoke(monkeypatch):
    helper = __import__("engines.install.runtime_check", fromlist=["EngineSmokeSpec"])
    calls = []

    class _Runtime:
        def invoke(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(result=[[1.0, 2.0, 3.0]])

    def _import_module(name):
        if name == "democrai.core.application.ai.engine.runtime":
            return SimpleNamespace(get_engine_runtime=lambda: _Runtime())
        raise AssertionError(name)

    monkeypatch.setattr(helper.importlib, "import_module", _import_module)

    result = helper.run_smoke(
        "onnx",
        helper.EngineSmokeSpec(
            method="embed_texts",
            config={"model": "smoke-model"},
            payload={"texts": ["hello"]},
            validate=lambda value: {"items": len(value.result)},
            engine_row_id=12,
            model_registry_id=34,
        ),
    )

    assert result["status"] == "passed"
    assert result["method"] == "embed_texts"
    assert result["result_type"] == "SimpleNamespace"
    assert result["validation"] == {"items": 1}
    assert calls == [
        {
            "engine_row_id": 12,
            "model_registry_id": 34,
            "engine_id": "onnx",
            "config": {"model": "smoke-model"},
            "method": "embed_texts",
            "payload": {"texts": ["hello"]},
        }
    ]


def test_engine_install_check_remote_without_smoke_does_not_invoke_runtime(monkeypatch):
    helper = __import__("engines.install.runtime_check", fromlist=["run_install_check"])
    monkeypatch.setattr(helper, "bootstrap_paths", lambda _root: None)
    monkeypatch.setattr(helper, "bootstrap_app_context", lambda: None)
    monkeypatch.setattr(
        helper,
        "check_ready",
        lambda _engine_id: {"ready": True, "message": "ready"},
    )
    monkeypatch.setattr(
        helper,
        "run_smoke",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no smoke")),
    )
    lines = []
    monkeypatch.setattr(
        helper,
        "print",
        lambda *args, **_kwargs: lines.append("".join(str(item) for item in args)),
        raising=False,
    )

    result = helper.run_install_check(
        engine_id="openai",
        result_prefix="RESULT=",
        cuda_mode="auto",
        root=Path("."),
        verify_runtime=lambda _cuda: {"openai": "2.40.0"},
        smoke=None,
        install=lambda _cuda, _engine: {"status": "installed"},
    )

    assert result == 0
    assert lines
    assert (
        '"smoke": {"reason": "remote_or_config_only_engine", "status": "skipped"}'
        in lines[0]
    )
