from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

import democrai.core.runtime.dependencies.engine_env as engine_env_mod


def test_anthropic_install_uses_declared_package_and_clean_target(monkeypatch):
    engine_mod = __import__("engines.anthropic.engine", fromlist=["AnthropicEngine"])
    calls = []

    monkeypatch.setattr(
        engine_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)),
    )

    engine_mod.AnthropicEngine._install(force=True)

    assert calls == [
        (
            ["anthropic==0.105.2"],
            {
                "modules": ["anthropic"],
                "extra_pip_args": ["--ignore-installed"],
                "force": True,
            },
        ),
    ]


def test_anthropic_ready_checks_declared_runtime(monkeypatch):
    engine_mod = __import__("engines.anthropic.engine", fromlist=["AnthropicEngine"])

    monkeypatch.setattr(engine_mod.AnthropicEngine, "_missing_modules", lambda *args: [])
    monkeypatch.setattr(
        engine_mod.AnthropicEngine,
        "_default_missing_shared",
        classmethod(lambda cls: []),
    )
    monkeypatch.setattr(engine_mod, "_anthropic_version_matches", lambda: True)
    monkeypatch.setattr(engine_mod, "_anthropic_runtime_symbols_available", lambda: True)

    result = engine_mod.AnthropicEngine._check_ready()

    assert result["ready"] is True
    assert result["missing_local"] == []


def test_anthropic_runtime_symbol_check_requires_async_client(monkeypatch):
    engine_mod = __import__("engines.anthropic.engine", fromlist=["AnthropicEngine"])

    class _AsyncAnthropic:
        def __init__(self, **kwargs):
            self.messages = SimpleNamespace(create=lambda **payload: None)
            self.messages.stream = lambda **payload: None
            self.models = SimpleNamespace(list=lambda: None)

    monkeypatch.setattr(
        engine_mod.importlib,
        "import_module",
        lambda name: SimpleNamespace(AsyncAnthropic=_AsyncAnthropic),
    )

    assert engine_mod._anthropic_runtime_symbols_available()


def test_anthropic_engine_env_isolates_transport_dependencies(monkeypatch, tmp_path):
    monkeypatch.setattr(engine_env_mod, "_ENGINE_LOCAL_PATH_OVERRIDES", {})

    local_env = tmp_path / "engine_env_cache" / "anthropic"
    local_cache = local_env / "cache"
    local_config = local_env / "config"
    local_tmp = local_env / "tmp"
    global_env = tmp_path / "venv" / "site-packages"
    for package in ("anthropic", "httpx", "httpcore", "anyio", "jiter"):
        _write_package(local_env, package, value=f"local_{package}")
        _write_package(global_env, package, value=f"global_{package}")
    local_cache.mkdir(parents=True)
    local_config.mkdir()
    local_tmp.mkdir()

    global_modules = {}
    for package in ("anthropic", "httpx", "httpcore", "anyio", "jiter"):
        module = ModuleType(package)
        module.__file__ = str(global_env / package / "__init__.py")
        global_modules[package] = module
        monkeypatch.setitem(sys.modules, package, module)
    monkeypatch.setattr(sys, "path", [str(global_env)])
    engine_env_mod.set_engine_local_path_overrides(
        "anthropic",
        env_path=str(local_env),
        cache_path=str(local_cache),
        config_path=str(local_config),
        tmp_path=str(local_tmp),
    )

    with engine_env_mod.engine_env_context("anthropic"):
        engine_env_mod.bootstrap_engine_env()
        engine_env_mod.isolate_engine_imports("anthropic")
        for package in ("anthropic", "httpx", "httpcore", "anyio", "jiter"):
            module = importlib.import_module(package)
            assert module.VALUE == f"local_{package}"

    for package, module in global_modules.items():
        assert sys.modules[package] is module


def _write_package(root, package_path: str, *, value: str) -> None:
    path = root / package_path
    path.mkdir(parents=True, exist_ok=True)
    (path / "__init__.py").write_text(f"VALUE = {value!r}\n", encoding="utf-8")
