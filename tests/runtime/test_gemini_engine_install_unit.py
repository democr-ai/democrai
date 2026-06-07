from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

import democrai.core.runtime.dependencies.engine_env as engine_env_mod


def test_gemini_install_uses_declared_package_and_clean_target(monkeypatch):
    engine_mod = __import__("engines.gemini.engine", fromlist=["GeminiEngine"])
    calls = []

    monkeypatch.setattr(
        engine_mod,
        "install_python_packages",
        lambda packages, **kwargs: calls.append((packages, kwargs)),
    )

    engine_mod.GeminiEngine._install(force=True)

    assert calls == [
        (
            ["google-genai==2.7.0"],
            {
                "modules": ["google.genai"],
                "extra_pip_args": ["--ignore-installed"],
                "force": True,
            },
        ),
    ]


def test_gemini_manifest_declares_cffi_imports_for_google_auth_crypto():
    from democrai.core.application.ai.engine.manifests import get_engine_manifest

    manifest = get_engine_manifest("gemini")

    assert set(manifest["install"]["allowed_imports"]) == {"cffi", "_cffi_backend"}
    assert set(manifest["runtime"]["allowed_imports"]) == {"cffi", "_cffi_backend"}


def test_gemini_ready_checks_declared_runtime(monkeypatch):
    engine_mod = __import__("engines.gemini.engine", fromlist=["GeminiEngine"])

    monkeypatch.setattr(engine_mod.GeminiEngine, "_missing_modules", lambda *args: [])
    monkeypatch.setattr(
        engine_mod.GeminiEngine,
        "_default_missing_shared",
        classmethod(lambda cls: []),
    )
    monkeypatch.setattr(engine_mod, "_google_genai_version_matches", lambda: True)
    monkeypatch.setattr(engine_mod, "_google_genai_runtime_symbols_available", lambda: True)

    result = engine_mod.GeminiEngine._check_ready()

    assert result["ready"] is True
    assert result["missing_local"] == []


def test_gemini_runtime_symbol_check_requires_client_and_types(monkeypatch):
    engine_mod = __import__("engines.gemini.engine", fromlist=["GeminiEngine"])

    class _Client:
        pass

    class _GenerateContentConfig:
        pass

    def import_module(name):
        if name == "google.genai":
            return SimpleNamespace(Client=_Client)
        if name == "google.genai.types":
            return SimpleNamespace(GenerateContentConfig=_GenerateContentConfig)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(engine_mod.importlib, "import_module", import_module)

    assert engine_mod._google_genai_runtime_symbols_available()


def test_gemini_engine_env_isolates_google_and_websocket_dependencies(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(engine_env_mod, "_ENGINE_LOCAL_PATH_OVERRIDES", {})

    local_env = tmp_path / "engine_env_cache" / "gemini"
    local_cache = local_env / "cache"
    local_config = local_env / "config"
    local_tmp = local_env / "tmp"
    global_env = tmp_path / "venv" / "site-packages"
    _write_package(local_env, "google", value="local_google")
    _write_package(local_env, "google/genai", value="local_genai")
    _write_package(local_env, "httpx", value="local_httpx")
    _write_package(local_env, "websockets", value="local_websockets")
    _write_package(global_env, "google", value="global_google")
    _write_package(global_env, "google/genai", value="global_genai")
    _write_package(global_env, "httpx", value="global_httpx")
    _write_package(global_env, "websockets", value="global_websockets")
    local_cache.mkdir(parents=True)
    local_config.mkdir()
    local_tmp.mkdir()

    google_mod = ModuleType("google")
    google_mod.__file__ = str(global_env / "google" / "__init__.py")
    genai_mod = ModuleType("google.genai")
    genai_mod.__file__ = str(global_env / "google" / "genai" / "__init__.py")
    httpx_mod = ModuleType("httpx")
    httpx_mod.__file__ = str(global_env / "httpx" / "__init__.py")
    websockets_mod = ModuleType("websockets")
    websockets_mod.__file__ = str(global_env / "websockets" / "__init__.py")

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "httpx", httpx_mod)
    monkeypatch.setitem(sys.modules, "websockets", websockets_mod)
    monkeypatch.setattr(sys, "path", [str(global_env)])
    engine_env_mod.set_engine_local_path_overrides(
        "gemini",
        env_path=str(local_env),
        cache_path=str(local_cache),
        config_path=str(local_config),
        tmp_path=str(local_tmp),
    )

    with engine_env_mod.engine_env_context("gemini"):
        engine_env_mod.bootstrap_engine_env()
        engine_env_mod.isolate_engine_imports("gemini")
        google = importlib.import_module("google")
        genai = importlib.import_module("google.genai")
        httpx = importlib.import_module("httpx")
        websockets = importlib.import_module("websockets")
        assert google.VALUE == "local_google"
        assert genai.VALUE == "local_genai"
        assert httpx.VALUE == "local_httpx"
        assert websockets.VALUE == "local_websockets"

    assert sys.modules["google"] is google_mod
    assert sys.modules["google.genai"] is genai_mod
    assert sys.modules["httpx"] is httpx_mod
    assert sys.modules["websockets"] is websockets_mod


def _write_package(root, package_path: str, *, value: str) -> None:
    path = root / package_path
    path.mkdir(parents=True, exist_ok=True)
    (path / "__init__.py").write_text(f"VALUE = {value!r}\n", encoding="utf-8")
