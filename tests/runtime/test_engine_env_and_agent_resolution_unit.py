import asyncio
import importlib
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from democrai.core.application.ai.models import selection_policy as selection_policy_mod
import democrai.core.platform.agents.runtime as runtime_mod
from democrai.core.platform.agents import skills_io as skills_io_mod
from democrai.core.runtime.dependencies import ai_bootstrap as ai_bootstrap_mod
from democrai.core.runtime.dependencies import engine_env as engine_env_mod
from democrai.core.runtime.dependencies import extractor_env as extractor_env_mod
from democrai.core.runtime.dependencies.installer_env import RUNTIME_ENV_JSON_ENV


def test_selection_policy_helpers(monkeypatch):
    monkeypatch.setattr(
        selection_policy_mod,
        "get_provider_definition",
        lambda name: {"deployment": "local"} if name == "a" else {"deployment": "remote"},
    )
    model = SimpleNamespace(provider="a", name="m1", capabilities=["chat", "image_to_text"])
    provider = SimpleNamespace(real_provider=SimpleNamespace())
    annotated = selection_policy_mod.annotate_provider(provider, model_info=model, engine_name="eng")
    assert annotated._democrai_provider_name == "a"
    assert annotated.real_provider._democrai_deployment_mode == "local"
    assert selection_policy_mod.provider_capabilities(model) == {"chat", "image_to_text"}
    assert selection_policy_mod.is_local_provider("a") is True
    assert selection_policy_mod.effective_policy_mode({"default_deployment": "hybrid"}, objective="x", prefer_local=True) == "local"
    assert selection_policy_mod.effective_policy_mode({"default_deployment": "hybrid"}, objective="x", prefer_local=False) == "cloud"
    assert selection_policy_mod.effective_policy_mode({"default_deployment": "hybrid"}, objective="x", prefer_local=None) == "hybrid"

    hv = SimpleNamespace(recommend_local_llm_engines=lambda **_k: ["a", "b"])
    assert selection_policy_mod.engine_fit_score("a", {"chat"}, hardware_validator=hv) == 40
    assert selection_policy_mod.engine_fit_score("b", {"chat"}, hardware_validator=hv) == 32
    assert selection_policy_mod.engine_fit_score("c", {"chat"}, hardware_validator=hv) == 16


def test_engine_env_paths_and_context(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(engine_env_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_env_mod, "cache_dir", lambda: tmp_path)
    for key in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(key, raising=False)
    dirty_path = os.pathsep.join(["/home/fabio/Android/Sdk/platform-tools", "/random/bin"])
    monkeypatch.setenv("PATH", dirty_path)
    with engine_env_mod.engine_env_context("ENGINEA"):
        assert engine_env_mod.get_current_engine_id() == "enginea"
        assert engine_env_mod.has_engine_env_context() is True
        local = engine_env_mod.get_engine_local_env_path()
        assert local.exists()
        cache = engine_env_mod.get_engine_local_cache_path()
        config = engine_env_mod.get_engine_local_config_path()
        assert os.environ["XDG_CACHE_HOME"] == str(cache / "xdg")
        assert os.environ["XDG_CONFIG_HOME"] == str(config)
        path_entries = os.environ["PATH"].split(os.pathsep)
        assert "/home/fabio/Android/Sdk/platform-tools" not in path_entries
        venv = engine_env_mod.get_engine_venv_path()
        assert str(venv / ("Scripts" if os.name == "nt" else "bin")) in path_entries
        assert str(venv) in path_entries
        assert "/usr/bin" not in path_entries
        assert "/bin" not in path_entries
        with engine_env_mod.engine_env_context("enginea", env={"DEMO_ENGINE_FLAG": "1"}):
            assert os.environ["DEMO_ENGINE_FLAG"] == "1"
            with engine_env_mod.engine_env_context("enginea"):
                assert os.environ["DEMO_ENGINE_FLAG"] == "1"
            with engine_env_mod.engine_env_context("engineb"):
                assert "DEMO_ENGINE_FLAG" not in os.environ
        assert "DEMO_ENGINE_FLAG" not in os.environ
    assert engine_env_mod.has_engine_env_context() is False
    assert "XDG_CACHE_HOME" not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ
    assert os.environ["PATH"] == dirty_path

    monkeypatch.setenv("HF_HOME", "/home/fabio/.cache/huggingface")
    monkeypatch.setenv("TORCH_HOME", "/home/fabio/.cache/torch")
    monkeypatch.setenv("CUDA_HOME", "/usr/local/cuda")
    with engine_env_mod.engine_env_context("engineb"):
        assert "HF_HOME" not in os.environ
        assert "TORCH_HOME" not in os.environ
        assert "CUDA_HOME" not in os.environ
    assert os.environ["HF_HOME"] == "/home/fabio/.cache/huggingface"
    assert os.environ["TORCH_HOME"] == "/home/fabio/.cache/torch"
    assert os.environ["CUDA_HOME"] == "/usr/local/cuda"


def test_engine_env_context_allows_runtime_env_json_under_guard(tmp_path: Path, monkeypatch):
    from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

    monkeypatch.setattr(engine_env_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_env_mod, "cache_dir", lambda: tmp_path)
    payload = '{"os": "linux"}'

    with process_guard_context(subject="onnx", subject_kind="engine", access=()):
        with engine_env_mod.engine_env_context("onnx", env={RUNTIME_ENV_JSON_ENV: payload}):
            assert os.environ[RUNTIME_ENV_JSON_ENV] == payload

    assert RUNTIME_ENV_JSON_ENV not in os.environ


def test_engine_env_bootstrap_and_clear(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(engine_env_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_env_mod, "cache_dir", lambda: tmp_path)
    original_sys_path = list(__import__("sys").path)

    with engine_env_mod.engine_env_context("e1"):
        root = engine_env_mod.get_engine_local_env_path()
        (root / ".success").write_text("ok", encoding="utf-8")
        boot = engine_env_mod.bootstrap_engine_env()
        venv = root / ".venv"
        site_packages = engine_env_mod.get_engine_venv_site_packages_path()
        assert boot == venv
        assert str(site_packages) in __import__("sys").path
        engine_env_mod.clear_local_engine_env()
        assert not root.exists()
    assert __import__("sys").path == original_sys_path


def test_engine_env_context_restores_module_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(engine_env_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_env_mod, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        engine_env_mod,
        "_ENGINE_ENV_ROOT",
        tmp_path / "engine_env_cache",
    )
    local_root = tmp_path / "engine_env_cache" / "whisper"
    local_root.mkdir(parents=True)
    app_module_path = tmp_path / "venv" / "site-packages" / "google" / "protobuf" / "__init__.py"
    app_module_path.parent.mkdir(parents=True)
    app_module_path.write_text("", encoding="utf-8")
    local_module_path = local_root / "google" / "protobuf" / "__init__.py"
    local_module_path.parent.mkdir(parents=True)
    local_module_path.write_text("", encoding="utf-8")
    local_only_path = local_root / "engine_only" / "__init__.py"
    local_only_path.parent.mkdir(parents=True)
    local_only_path.write_text("", encoding="utf-8")

    app_google = ModuleType("google")
    app_google.__path__ = [str(app_module_path.parent.parent)]
    app_protobuf = ModuleType("google.protobuf")
    app_protobuf.__file__ = str(app_module_path)
    local_google = ModuleType("google")
    local_google.__path__ = [str(local_module_path.parent.parent)]
    local_protobuf = ModuleType("google.protobuf")
    local_protobuf.__file__ = str(local_module_path)
    local_only = ModuleType("engine_only")
    local_only.__file__ = str(local_only_path)

    monkeypatch.setitem(sys.modules, "google", app_google)
    monkeypatch.setitem(sys.modules, "google.protobuf", app_protobuf)

    with engine_env_mod.engine_env_context("whisper"):
        sys.modules["google"] = local_google
        sys.modules["google.protobuf"] = local_protobuf
        sys.modules["engine_only"] = local_only
        assert sys.modules["google.protobuf"] is local_protobuf

    assert sys.modules["google"] is app_google
    assert sys.modules["google.protobuf"] is app_protobuf
    assert "engine_only" not in sys.modules


def test_engine_env_error_and_activation_branches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(engine_env_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(engine_env_mod, "cache_dir", lambda: tmp_path)

    with pytest.raises(RuntimeError, match="engine_env_context_missing"):
        engine_env_mod.get_engine_local_env_path(None)

    with engine_env_mod.engine_env_context("e2"):
        root = engine_env_mod.get_engine_local_env_path()
        venv = root / ".venv"
        site_packages = engine_env_mod.get_engine_venv_site_packages_path()
        assert engine_env_mod.activate_local_engine_env() == venv
        assert str(site_packages) in __import__("sys").path


def test_engine_env_paths_can_be_resolved_without_creating_dirs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        engine_env_mod,
        "_ENGINE_ENV_ROOT",
        tmp_path / "engine_env_cache",
    )

    root = engine_env_mod.get_engine_local_env_path("probe", create=False)
    cache = engine_env_mod.get_engine_local_cache_path("probe", create=False)
    config = engine_env_mod.get_engine_local_config_path("probe", create=False)
    tmp = engine_env_mod.get_engine_local_tmp_path("probe", create=False)
    python = engine_env_mod.get_engine_venv_python_path("probe", create=False)

    assert root == tmp_path / "engine_env_cache" / "probe"
    assert cache == root / "cache"
    assert config == root / "config"
    assert tmp == root / "tmp"
    assert python.parent == root / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    assert not root.exists()


def test_engine_env_root_uses_cache_dir_on_macos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(engine_env_mod, "_ENGINE_ENV_ROOT", None)
    monkeypatch.setattr(engine_env_mod.sys, "platform", "darwin")
    monkeypatch.setattr(engine_env_mod, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(engine_env_mod, "data_dir", lambda: tmp_path / "data")

    assert (
        engine_env_mod.get_engine_local_env_path("onnx", create=False)
        == tmp_path / "cache" / "engine_env_cache" / "onnx"
    )
    assert ai_bootstrap_mod.ensure_engine_env_base() == (
        tmp_path / "cache" / "engine_env_cache"
    )


def test_engine_env_root_uses_data_dir_off_macos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(engine_env_mod, "_ENGINE_ENV_ROOT", None)
    monkeypatch.setattr(engine_env_mod.sys, "platform", "linux")
    monkeypatch.setattr(engine_env_mod, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(engine_env_mod, "data_dir", lambda: tmp_path / "data")

    assert (
        engine_env_mod.get_engine_local_env_path("onnx", create=False)
        == tmp_path / "data" / "engine_env_cache" / "onnx"
    )


def test_extractor_env_paths_and_context(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(extractor_env_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        extractor_env_mod,
        "_EXTRACTOR_ENV_ROOT",
        tmp_path / "extractor_env_cache",
    )
    for key in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "HF_HOME"):
        monkeypatch.delenv(key, raising=False)

    with extractor_env_mod.extractor_env_context("DOCLING"):
        assert extractor_env_mod.get_current_extractor_id() == "docling"
        assert extractor_env_mod.has_extractor_env_context() is True
        local = extractor_env_mod.get_extractor_local_env_path()
        cache = extractor_env_mod.get_extractor_local_cache_path()
        config = extractor_env_mod.get_extractor_local_config_path()
        assert local == tmp_path / "extractor_env_cache" / "docling"
        assert os.environ["XDG_CACHE_HOME"] == str(cache / "xdg")
        assert os.environ["XDG_CONFIG_HOME"] == str(config)
        assert os.environ["HF_HOME"] == str(cache / "huggingface")
        assert os.environ["HF_HUB_CACHE"] == str(cache / "huggingface" / "hub")
        assert os.environ["TORCH_HOME"] == str(cache / "torch")
        venv = extractor_env_mod.get_extractor_venv_path()
        assert str(venv / ("Scripts" if os.name == "nt" else "bin")) in os.environ["PATH"].split(os.pathsep)
        with extractor_env_mod.extractor_env_context(
            "docling",
            env={"DEMO_EXTRACTOR_FLAG": "1"},
        ):
            assert os.environ["DEMO_EXTRACTOR_FLAG"] == "1"
            with extractor_env_mod.extractor_env_context("docling"):
                assert os.environ["DEMO_EXTRACTOR_FLAG"] == "1"
        assert "DEMO_EXTRACTOR_FLAG" not in os.environ

    assert extractor_env_mod.has_extractor_env_context() is False
    assert "XDG_CACHE_HOME" not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ

    with pytest.raises(RuntimeError, match="extractor_env_context_missing"):
        extractor_env_mod.get_extractor_local_env_path(None)

    original_sys_path = list(__import__("sys").path)
    with extractor_env_mod.extractor_env_context("docling"):
        root = extractor_env_mod.get_extractor_venv_site_packages_path()
        extractor_env_mod.isolate_extractor_imports()
        assert str(root) in __import__("sys").path
    assert __import__("sys").path == original_sys_path


def test_extractor_env_root_uses_cache_dir_on_macos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(extractor_env_mod, "_EXTRACTOR_ENV_ROOT", None)
    monkeypatch.setattr(extractor_env_mod.sys, "platform", "darwin")
    monkeypatch.setattr(extractor_env_mod, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(extractor_env_mod, "data_dir", lambda: tmp_path / "data")

    assert (
        extractor_env_mod.get_extractor_local_env_path("docling")
        == tmp_path / "cache" / "extractor_env_cache" / "docling"
    )


def test_extractor_env_root_uses_data_dir_off_macos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(extractor_env_mod, "_EXTRACTOR_ENV_ROOT", None)
    monkeypatch.setattr(extractor_env_mod.sys, "platform", "linux")
    monkeypatch.setattr(extractor_env_mod, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(extractor_env_mod, "data_dir", lambda: tmp_path / "data")

    assert (
        extractor_env_mod.get_extractor_local_env_path("docling")
        == tmp_path / "data" / "extractor_env_cache" / "docling"
    )


def test_extractor_env_context_restores_module_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(extractor_env_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        extractor_env_mod,
        "_EXTRACTOR_ENV_ROOT",
        tmp_path / "extractor_env_cache",
    )
    local_root = tmp_path / "extractor_env_cache" / "docling"
    local_site = local_root / ".venv" / "lib" / "python3.12" / "site-packages"
    local_root.mkdir(parents=True)
    app_module_path = tmp_path / "venv" / "site-packages" / "sharedpkg" / "__init__.py"
    app_module_path.parent.mkdir(parents=True)
    app_module_path.write_text("", encoding="utf-8")
    local_module_path = local_site / "sharedpkg" / "__init__.py"
    local_module_path.parent.mkdir(parents=True)
    local_module_path.write_text("", encoding="utf-8")
    local_only_path = local_site / "extractor_only" / "__init__.py"
    local_only_path.parent.mkdir(parents=True)
    local_only_path.write_text("", encoding="utf-8")

    app_shared = ModuleType("sharedpkg")
    app_shared.__file__ = str(app_module_path)
    local_shared = ModuleType("sharedpkg")
    local_shared.__file__ = str(local_module_path)
    local_only = ModuleType("extractor_only")
    local_only.__file__ = str(local_only_path)

    monkeypatch.setitem(sys.modules, "sharedpkg", app_shared)

    with extractor_env_mod.extractor_env_context("docling"):
        sys.modules["sharedpkg"] = local_shared
        sys.modules["extractor_only"] = local_only
        assert sys.modules["sharedpkg"] is local_shared

    assert sys.modules["sharedpkg"] is app_shared
    assert "extractor_only" not in sys.modules


def test_extractor_env_context_restore_does_not_trigger_lazy_module_getattr(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        extractor_env_mod,
        "_EXTRACTOR_ENV_ROOT",
        tmp_path / "extractor_env_cache",
    )
    local_root = tmp_path / "extractor_env_cache" / "docling"
    local_module_path = local_root / "lazypkg" / "__init__.py"
    local_module_path.parent.mkdir(parents=True)
    local_module_path.write_text("", encoding="utf-8")

    class _LazyModule(ModuleType):
        def __getattr__(self, name):
            raise AssertionError(f"lazy getattr triggered:{name}")

    local_module = _LazyModule("lazypkg")
    local_module.__dict__["__file__"] = str(local_module_path)

    with extractor_env_mod.extractor_env_context("docling"):
        sys.modules["lazypkg"] = local_module

    assert "lazypkg" not in sys.modules


def test_isolate_extractor_imports_removes_global_local_modules(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        extractor_env_mod,
        "_EXTRACTOR_ENV_ROOT",
        tmp_path / "extractor_env_cache",
    )
    local_root = tmp_path / "extractor_env_cache" / "docling"
    local_site = local_root / ".venv" / "lib" / "python3.12" / "site-packages"
    local_module_path = local_site / "sharedpkg" / "__init__.py"
    local_module_path.parent.mkdir(parents=True)
    local_module_path.write_text("", encoding="utf-8")
    app_module_path = tmp_path / "venv" / "site-packages" / "sharedpkg" / "__init__.py"
    app_module_path.parent.mkdir(parents=True)
    app_module_path.write_text("", encoding="utf-8")
    app_other_path = tmp_path / "venv" / "site-packages" / "otherpkg" / "__init__.py"
    app_other_path.parent.mkdir(parents=True)
    app_other_path.write_text("", encoding="utf-8")

    shared = ModuleType("sharedpkg")
    shared.__file__ = str(app_module_path)
    shared_sub = ModuleType("sharedpkg.sub")
    shared_sub.__file__ = str(app_module_path.parent / "sub.py")
    other = ModuleType("otherpkg")
    other.__file__ = str(app_other_path)
    monkeypatch.setitem(sys.modules, "sharedpkg", shared)
    monkeypatch.setitem(sys.modules, "sharedpkg.sub", shared_sub)
    monkeypatch.setitem(sys.modules, "otherpkg", other)

    with extractor_env_mod.extractor_env_context("docling"):
        extractor_env_mod.isolate_extractor_imports("docling")
        assert "sharedpkg" not in sys.modules
        assert "sharedpkg.sub" not in sys.modules
        assert sys.modules["otherpkg"] is other
        assert sys.path[0] == str(local_site)

    assert "sharedpkg" not in sys.modules
    assert "sharedpkg.sub" not in sys.modules
    assert sys.modules["otherpkg"] is other


@pytest.mark.asyncio
async def test_redis_stream_provider(monkeypatch):
    class _PubSub:
        def __init__(self):
            self.unsubscribed = []
            self.closed = False
            self._messages = [{"type": "message", "data": '{"x":1}'}]

        async def subscribe(self, _channel):
            return None

        async def listen(self):
            for item in self._messages:
                yield item

        async def unsubscribe(self, channel):
            self.unsubscribed.append(channel)

        async def close(self):
            self.closed = True

    class _Redis:
        def __init__(self):
            self.published = []
            self.pubsub_obj = _PubSub()

        def pubsub(self):
            return self.pubsub_obj

        async def publish(self, channel, payload):
            self.published.append((channel, payload))

    fake_redis = _Redis()
    fake_asyncio_mod = SimpleNamespace(from_url=lambda _url: fake_redis)
    monkeypatch.setitem(__import__("sys").modules, "redis", SimpleNamespace(asyncio=fake_asyncio_mod))
    monkeypatch.setitem(__import__("sys").modules, "redis.asyncio", fake_asyncio_mod)
    stream_mod = importlib.reload(
        importlib.import_module("democrai.core.infrastructure.network.providers.stream.redis")
    )
    RedisStreamProvider = stream_mod.RedisStreamProvider
    provider = RedisStreamProvider("redis://demo")
    q = provider.subscribe("room")
    await provider.broadcast("room", {"a": 1})
    assert fake_redis.published
    await provider._redis_listener("room")
    assert (await q.get()) == {"x": 1}
    provider.unsubscribe("room", q)


@pytest.mark.asyncio
async def test_agent_runtime_provider_and_skills_io(tmp_path: Path, monkeypatch):
    captured = {}
    definition = runtime_mod.AgentDefinition(
        name="agent1",
        description="desc",
        objective="chat",
        tools=("tool1",),
        skills=("s1",),
        mcp_servers=("mcp1",),
        max_iterations=3,
    )

    class _Provider:
        async def generate_completion(self, messages, options):
            captured["messages"] = messages
            captured["options"] = options
            return SimpleNamespace(id="r1", content="ok", tool_calls=[])

    monkeypatch.setattr(
        runtime_mod,
        "_agent_runtime_config",
        lambda _agent_name: {
            "extra_tools": (),
            "extra_skills": (),
            "extra_mcp_servers": (),
            "extra_agents": (),
            "max_iterations": None,
        },
    )
    monkeypatch.setattr(
        runtime_mod,
        "resolve_agent_provider",
        lambda _definition, parent_provider=None: __import__("asyncio").sleep(
            0, result=parent_provider
        ),
    )
    runtime = runtime_mod.AgentRuntime()
    runtime.agent_registry = {"agent1": definition}
    result = await runtime.run_agent(
        "agent1",
        input="hi",
        provider=_Provider(),
        extra_tools=("tool2",),
        extra_skills=("s2",),
    )
    assert result.content == "ok"
    assert [message.role.value for message in captured["messages"]] == ["system", "user"]
    assert captured["options"] == {
        "tools": ["tool1", "tool2"],
        "skills": ["s1", "s2"],
        "mcp": ["mcp1"],
        "agents": [],
        "tool_max_iterations": 3,
    }

    skill_dir = tmp_path / "mod1" / "skills" / "s1"
    assets = skill_dir / "assets"
    assets.mkdir(parents=True)
    (assets / "a.txt").write_text("x", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Demo\ndescription: Desc\ntags: [a]\n---\n# Title\nBody\n",
        encoding="utf-8",
    )
    dirs = skills_io_mod.module_skill_dirs(tmp_path)
    assert len(dirs) == 1
    discovered_assets = skills_io_mod.discover_assets(skill_dir)
    assert discovered_assets == ("a.txt",)
    from democrai.core.application.access_policy import models as access_models

    monkeypatch.setattr(access_models, "_SUBJECT_TYPES", access_models._SUBJECT_TYPES | {"skill"})
    meta, body = skills_io_mod.parse_skill_document((skill_dir / "SKILL.md").read_text(encoding="utf-8"), skill_dir / "SKILL.md")
    assert meta.name == "Demo"
    assert "Body" in body


@pytest.mark.asyncio
async def test_agent_runtime_provider_error_and_orchestrator_paths(monkeypatch):
    class _Orchestrator:
        async def get_provider_for_objective(self, objective):
            return {"status": "ok", "provider": f"provider:{objective}"}

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(model_orchestrator=_Orchestrator()),
    )
    runtime = runtime_mod.AgentRuntime()
    provider = await runtime._resolve_provider(
        SimpleNamespace(objective="chat")
    )
    assert provider == "provider:chat"

    class _FailOrchestrator:
        async def get_provider_for_objective(self, _objective):
            return {"status": "error", "error": "no-provider"}

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.ai.orchestrator",
        SimpleNamespace(model_orchestrator=_FailOrchestrator()),
    )
    with pytest.raises(RuntimeError, match="no-provider"):
        await runtime._resolve_provider(SimpleNamespace(objective="chat"))
