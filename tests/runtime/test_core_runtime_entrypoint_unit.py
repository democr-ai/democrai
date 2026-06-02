from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import democrai.core.application.ai.engine.manifests as engine_manifests
import democrai.core.application.knowledge.extractor.manifests as extractor_manifests
import democrai.core.runtime.entrypoint as entrypoint_mod
import democrai.core.runtime.foundation.paths as paths_mod
from democrai.core.runtime.foundation.app import app_ctx


def test_core_runtime_options_from_values_normalizes_runtime_paths(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    options = entrypoint_mod.CoreRuntimeOptions.from_values(
        mode="server",
        http=True,
        host="0.0.0.0",
        port="9000",
        workers="2",
        dev="1",
        listen_fd=7,
        modules_path=f"{first}{os.pathsep}{second}{os.pathsep}{first}",
        engines_path=[f"{second}{os.pathsep}{first}"],
        extractors_path=str(first),
    )

    assert options.mode == "server"
    assert options.http is True
    assert options.host == "0.0.0.0"
    assert options.port == 9000
    assert options.workers == 2
    assert options.dev == 1
    assert options.listen_fd == 7
    assert options.module_paths == (
        str(first.resolve()),
        str(second.resolve()),
    )
    assert options.engine_paths == (
        str(second.resolve()),
        str(first.resolve()),
    )
    assert options.extractor_paths == (str(first.resolve()),)


def test_core_runtime_options_from_args_reads_runner_environment(monkeypatch, tmp_path):
    modules_dir = tmp_path / "modules"
    engines_dir = tmp_path / "engines"
    extractors_dir = tmp_path / "extractors"
    monkeypatch.setenv(
        entrypoint_mod.MODULES_PATH_ENV,
        f"{modules_dir}{os.pathsep}{modules_dir}",
    )
    monkeypatch.setenv(entrypoint_mod.ENGINES_PATH_ENV, str(engines_dir))
    monkeypatch.setenv(entrypoint_mod.EXTRACTORS_PATH_ENV, str(extractors_dir))

    options = entrypoint_mod.core_runtime_options_from_args(
        SimpleNamespace(mode="server")
    )

    assert options.module_paths == (str(modules_dir.resolve()),)
    assert options.engine_paths == (str(engines_dir.resolve()),)
    assert options.extractor_paths == (str(extractors_dir.resolve()),)


def test_core_runtime_options_from_args_ignores_runtime_path_args(monkeypatch, tmp_path):
    env_modules_dir = tmp_path / "env-modules"
    arg_modules_dir = tmp_path / "arg-modules"
    monkeypatch.setenv(entrypoint_mod.MODULES_PATH_ENV, str(env_modules_dir))

    options = entrypoint_mod.core_runtime_options_from_args(
        SimpleNamespace(mode="server", modules_path=str(arg_modules_dir))
    )

    assert options.module_paths == (str(env_modules_dir.resolve()),)


def test_start_core_runtime_sets_context_and_bootstraps(monkeypatch, tmp_path):
    observed = {}

    class _Bootstrapper:
        def bootstrap(self, options):
            observed["options"] = options
            return "ipc-endpoint"

    monkeypatch.setattr(entrypoint_mod, "RuntimeBootstrapper", _Bootstrapper)
    monkeypatch.setattr(
        entrypoint_mod,
        "LoggerManager",
        lambda log_dir: SimpleNamespace(log_dir=log_dir),
    )
    monkeypatch.setattr(entrypoint_mod, "logs_dir", lambda: tmp_path / "logs")

    options = entrypoint_mod.CoreRuntimeOptions.from_values(
        mode="server",
        modules_path=[tmp_path / "modules"],
        engines_path=[tmp_path / "engines"],
        extractors_path=[tmp_path / "extractors"],
    )

    endpoint = entrypoint_mod.start_core_runtime(options)
    ctx = app_ctx()

    assert endpoint == "ipc-endpoint"
    assert observed["options"] is options
    assert ctx.runtime_mode == "server"
    assert ctx.runtime_module_paths == (str((tmp_path / "modules").resolve()),)
    assert ctx.runtime_engine_paths == (str((tmp_path / "engines").resolve()),)
    assert ctx.runtime_extractor_paths == (str((tmp_path / "extractors").resolve()),)
    assert ctx.logger.log_dir == str(tmp_path / "logs")


def test_manifest_roots_include_runtime_paths(monkeypatch, tmp_path):
    ctx = app_ctx()
    monkeypatch.setattr(ctx, "runtime_engine_paths", (str(tmp_path / "engines"),), raising=False)
    monkeypatch.setattr(ctx, "runtime_extractor_paths", (str(tmp_path / "extractors"),), raising=False)
    monkeypatch.setattr(
        ctx,
        "config",
        SimpleNamespace(get=lambda _key, default=None: default),
        raising=False,
    )
    assert engine_manifests.get_engine_roots() == (tmp_path / "engines",)
    assert extractor_manifests.get_extractor_roots() == (tmp_path / "extractors",)
