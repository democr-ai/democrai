from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.base.engine import BaseEngine
import democrai.core.application.ai.engine.base.engine as engine_mod


class _Engine(BaseEngine):
    engine_id = "demo"

    @classmethod
    def _install(cls, force=False, node_id=None, source_node_id=None):
        return {
            "force": force,
            "node_id": node_id,
            "source_node_id": source_node_id,
            "status": "installed",
        }

    @classmethod
    def _check_ready(cls, node_id=None):
        return {"ready": True, "message": "ok", "node_id": node_id}

    @classmethod
    def _validate_config(cls, config=None):
        return {"ready": True, "missing_config": [], "message": "", "config": config or {}}


def test_base_engine_manifest_and_support_helpers(monkeypatch):
    monkeypatch.setattr(engine_mod, "get_engine_manifest", lambda _eid: {"manifest_version": "2"})
    assert _Engine.get_manifest_version() == "2"
    assert _Engine.is_supported({}) is True
    assert _Engine.unsupported_reason({}) == ""
    assert _Engine.check_supported({})["supported"] is True
    assert _Engine.support_status({})["supported"] is True


def test_base_engine_check_and_validate_payload_defaults(monkeypatch):
    monkeypatch.setattr(engine_mod, "get_runtime_node_id", lambda: "node-a")
    ready = _Engine.check_ready()
    assert ready["ready"] is True
    assert ready["engine_id"] == "demo"
    assert ready["node_id"] == "node-a"

    cfg = _Engine.check_runtime_config(config={"x": 1})
    assert cfg["ready"] is True
    assert cfg["engine_id"] == "demo"


def test_base_engine_install_local_source_and_remote_paths(monkeypatch):
    calls = []
    monkeypatch.setattr(engine_mod, "engine_env_context", lambda _eid: __import__("contextlib").nullcontext())
    monkeypatch.setattr(engine_mod, "clear_local_engine_env", lambda *_args: calls.append("clear"))
    monkeypatch.setattr(engine_mod, "emit_engine_install_output", lambda *_a, **_k: calls.append("emit"))
    monkeypatch.setattr(engine_mod, "apply_engine_registry_config_updates", lambda **_k: calls.append("config"))
    monkeypatch.setattr(_Engine, "_mark_installed_in_registry", classmethod(lambda cls: calls.append("mark")))
    monkeypatch.setattr(_Engine, "_check_ready_local", classmethod(lambda cls, node_id=None: {"ready": True, "message": "ok", "node_id": node_id}))
    monkeypatch.setattr(engine_mod, "get_runtime_node_id", lambda: "n1")

    out1 = _Engine.install(force=True, node_id="n1", source_node_id="n1")
    assert out1["status"] == "installed"
    assert "clear" in calls and "mark" in calls

    calls.clear()
    out2 = _Engine.install(force=False, node_id="n2", source_node_id="n1")
    assert out2["node_id"] == "n2"


def test_base_engine_install_raises_when_not_ready(monkeypatch):
    monkeypatch.setattr(engine_mod, "engine_env_context", lambda _eid: __import__("contextlib").nullcontext())
    monkeypatch.setattr(_Engine, "_check_ready_local", classmethod(lambda cls, node_id=None: {"ready": False, "message": "bad"}))
    with pytest.raises(RuntimeError):
        _Engine.install()


def test_base_engine_invoke_install_and_helpers(monkeypatch):
    class _Strict(BaseEngine):
        engine_id = "x"

        @classmethod
        def _install(cls, force=False, node_id=None, source_node_id=None):
            return {"ok": force, "node_id": node_id, "source_node_id": source_node_id}

    out = _Strict._invoke_install(force=True, node_id="n", source_node_id="s")
    assert out["ok"] is True
    assert out["node_id"] == "n"
    assert out["source_node_id"] == "s"

    missing = _Engine._default_missing_shared()
    assert missing == []
    monkeypatch.setattr(engine_mod.importlib.util, "find_spec", lambda name: None if name == "missing.mod" else object())
    monkeypatch.setattr(
        _Engine,
        "_command_exists",
        classmethod(lambda cls, cmd: False if cmd == "missingcmd" else True),
    )
    monkeypatch.setattr(_Engine, "get_manifest", classmethod(lambda cls: {"provider": {"dependencies": [{"module": "missing.mod", "label": "Missing"}, {"check_type": "command_any", "commands": "missingcmd,ok"}]}}))
    assert _Engine._default_missing_local() == ["Missing"]
    assert _Engine._missing_modules(("missing.mod", "M")) == ["M"]
    assert _Engine._missing_commands(("missingcmd", "C")) == ["C"]
    assert _Engine._build_ready_payload(missing_shared=[], missing_local=[])["ready"] is True
    assert _Engine._build_supported_payload(supported=True)["supported"] is True


def test_base_engine_registry(monkeypatch):
    rows = []
    class _Query:
        def filter(self, _expr):
            return self
        def all(self):
            return rows
    class _Session:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def query(self, _model):
            return _Query()
        def add(self, row):
            rows.append(row)
        def commit(self):
            return None
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.database",
        SimpleNamespace(SessionLocal=_Session),
    )
    class _Col:
        def __eq__(self, _other):
            return object()

    class _EngineRegistry:
        provider = _Col()

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.database.models",
        SimpleNamespace(EngineRegistry=_EngineRegistry),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.runtime.dependencies.installer_env",
        SimpleNamespace(runtime_env=lambda: {}),
    )
    monkeypatch.setattr(_Engine, "is_supported", classmethod(lambda cls, env=None: True))
    _Engine._mark_installed_in_registry()
    assert rows and rows[0].status == "installed"
