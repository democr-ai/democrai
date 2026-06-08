from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import democrai.core.runtime.cli.parser as parser_mod
import democrai.core.runtime.foundation.paths as paths_mod
import democrai.core.runtime.observability.profiling as profiling_mod


def test_paths_helpers_and_resolution(monkeypatch, tmp_path: Path):
    # _mkdir failure branch
    class _BadPath:
        def mkdir(self, **_k):
            raise RuntimeError("boom")

        def __str__(self):
            return "/bad"

    prints = []
    monkeypatch.setattr("builtins.print", lambda msg: prints.append(msg))
    assert paths_mod._mkdir(_BadPath()) is not None
    assert prints

    # is_frozen branches
    monkeypatch.delattr(paths_mod.sys, "frozen", raising=False)
    monkeypatch.delattr(paths_mod.sys, "nuitka_binary_dir", raising=False)
    if "__compiled__" in paths_mod.__dict__:
        monkeypatch.delitem(paths_mod.__dict__, "__compiled__", raising=False)
    assert paths_mod.is_frozen() is False
    monkeypatch.setattr(paths_mod.sys, "frozen", True, raising=False)
    assert paths_mod.is_frozen() is True

    # get_base_dir branches
    monkeypatch.setattr(paths_mod, "is_frozen", lambda: True)
    monkeypatch.setattr(paths_mod.sys, "executable", "/opt/app/bin/democrai")
    assert paths_mod.get_base_dir() == "/opt/app/bin"

    monkeypatch.setattr(paths_mod, "is_frozen", lambda: False)
    monkeypatch.setattr(paths_mod, "__file__", "/x/application/democrai/core/runtime/foundation/paths.py")
    assert paths_mod.get_base_dir() == "/x/application/democrai"

    # _home branches
    monkeypatch.setenv("SUDO_UID", "123")
    monkeypatch.delenv("PKEXEC_UID", raising=False)
    monkeypatch.setattr(paths_mod.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(paths_mod, "pwd", SimpleNamespace(getpwuid=lambda uid: SimpleNamespace(pw_dir="/sudo/home")))
    assert paths_mod._home() == Path("/sudo/home")

    monkeypatch.setattr(paths_mod, "pwd", SimpleNamespace(getpwuid=lambda uid: (_ for _ in ()).throw(RuntimeError("x"))))
    assert isinstance(paths_mod._home(), Path)

    monkeypatch.setattr(paths_mod.sys, "platform", "win32", raising=False)
    monkeypatch.setenv("SUDO_UID", "123")
    assert isinstance(paths_mod._home(), Path)

    # xdg/windows helpers
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    assert paths_mod._xdg_path("XDG_DATA_HOME", tmp_path / "fallback") == tmp_path / "xdg-data"
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert paths_mod._xdg_path("XDG_DATA_HOME", tmp_path / "fallback") == tmp_path / "fallback"

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localdata"))
    assert paths_mod._windows_appdata() == tmp_path / "appdata"
    assert paths_mod._windows_localdata() == tmp_path / "localdata"

    # roots by platform
    monkeypatch.setattr(paths_mod, "_home", lambda: tmp_path / "home")
    monkeypatch.setattr(paths_mod.sys, "platform", "win32", raising=False)
    assert str(paths_mod._data_root()).endswith("appdata/democrai")

    monkeypatch.setattr(paths_mod.sys, "platform", "darwin", raising=False)
    assert "Application Support" in str(paths_mod._data_root())

    monkeypatch.setattr(paths_mod.sys, "platform", "linux", raising=False)
    base = tmp_path / "data" / paths_mod.APP_NAME
    legacy = base / paths_mod.APP_NAME
    legacy.mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "_xdg_path", lambda _e, _f: tmp_path / "data")
    assert paths_mod._data_root() == legacy
    monkeypatch.setattr(paths_mod.sys, "platform", "win32", raising=False)
    assert str(paths_mod._config_root()).endswith("/appdata/democrai")
    assert str(paths_mod._cache_root()).endswith("/localdata/democrai/Cache")
    assert str(paths_mod._state_root()).endswith("/localdata/democrai/State")
    monkeypatch.setattr(paths_mod.sys, "platform", "darwin", raising=False)
    assert "Application Support" in str(paths_mod._config_root())
    assert "Caches" in str(paths_mod._cache_root())
    assert "state" in str(paths_mod._state_root())

    # config/cache/state dirs and wrappers
    monkeypatch.setattr(paths_mod, "_config_root", lambda: tmp_path / "cfg")
    monkeypatch.setattr(paths_mod, "_data_root", lambda: tmp_path / "data2")
    monkeypatch.setattr(paths_mod, "_cache_root", lambda: tmp_path / "cache")
    monkeypatch.setattr(paths_mod, "_state_root", lambda: tmp_path / "state")
    assert paths_mod.config_dir().exists()
    assert paths_mod.data_dir().exists()
    assert paths_mod.cache_dir().exists()
    assert paths_mod.state_dir().exists()
    assert paths_mod.logs_dir().exists()
    assert paths_mod.get_data_dir() == str(tmp_path / "data2")

    short_state = Path(paths_mod.tempfile.gettempdir()) / f"dc-paths-{os.getpid()}"
    monkeypatch.setattr(paths_mod, "_state_root", lambda: short_state)
    ipc_dir = paths_mod.runtime_ipc_dir()
    if len(str(short_state / "ipc")) + 64 <= paths_mod._AF_UNIX_SOCKET_PATH_LIMIT:
        assert ipc_dir == short_state / "ipc"
    else:
        assert len(str(ipc_dir)) < paths_mod._AF_UNIX_SOCKET_PATH_LIMIT
    socket_path = paths_mod.runtime_unix_socket_path("unit.sock")
    assert socket_path.name == "unit.sock"
    assert socket_path.parent == ipc_dir
    assert len(str(socket_path)) <= paths_mod._AF_UNIX_SOCKET_PATH_LIMIT

    long_state = tmp_path / ("very-long-state-root-" + ("x" * 120))
    monkeypatch.setattr(paths_mod, "_state_root", lambda: long_state)
    ipc_dir = paths_mod.runtime_ipc_dir()
    socket_path = paths_mod.runtime_unix_socket_path("unit.sock")
    assert len(str(ipc_dir)) < paths_mod._AF_UNIX_SOCKET_PATH_LIMIT
    assert socket_path.parent == ipc_dir
    assert len(str(socket_path)) <= paths_mod._AF_UNIX_SOCKET_PATH_LIMIT

    long_tmp = tmp_path / ("very-long-tmp-root-" + ("y" * 120))
    monkeypatch.setattr(paths_mod.tempfile, "gettempdir", lambda: str(long_tmp))
    ipc_dir = paths_mod.runtime_ipc_dir()
    socket_path = paths_mod.runtime_unix_socket_path(
        "engine-worker-control-1234567890-abcdef.sock"
    )
    assert not str(ipc_dir).startswith(str(long_tmp))
    assert len(str(socket_path)) <= paths_mod._AF_UNIX_SOCKET_PATH_LIMIT

    # model path + runtime dirs
    assert paths_mod.resolve_model_path("") == ""
    abs_model = paths_mod.resolve_model_path(str((tmp_path / "m.bin").resolve()))
    assert abs_model.startswith("/")
    assert paths_mod.resolve_model_path("relative/model") == "relative/model"

    user_skills = paths_mod.get_user_skills_dir()
    assert user_skills.endswith("skills")

    monkeypatch.setattr(paths_mod, "get_base_dir", lambda: str(tmp_path / "base"))
    runtime_modules = tmp_path / "modules"
    runtime_modules.mkdir()
    monkeypatch.setenv(paths_mod.MODULES_PATH_ENV, str(runtime_modules))
    assert paths_mod.get_runtime_module_dirs() == (str(runtime_modules.resolve()),)
    assert paths_mod.get_builtin_skills_dir().endswith("/skills")


def test_cli_parser_branches(monkeypatch):
    monkeypatch.setattr(parser_mod, "ALL_TARGETS", ["db"])
    monkeypatch.setattr(parser_mod, "CREATE_TARGETS", ["db"])
    monkeypatch.setattr(parser_mod, "ROLLBACK_TARGETS", ["db"])

    base = parser_mod.build_base_parser(add_help=False)
    parsed = base.parse_args(["--mode", "server", "--host", "0.0.0.0"])
    assert parsed.mode == "server"

    # module callable detection
    args = parser_mod.parse_args(["module.cmd", "1", "--flag"])
    assert args.command == "module-callable"
    assert args.module_command == "module.cmd"

    # no remaining -> normal parser
    args2 = parser_mod.parse_args(["--mode", "desktop"])
    assert args2.mode == "desktop"

    # unknown global option path
    with pytest.raises(SystemExit):
        parser_mod.parse_args(["--unknown-opt"])

    # unknown args after command path
    with pytest.raises(SystemExit):
        parser_mod.parse_args(["migrate", "db", "--bad"])

    ok_args = parser_mod.parse_args(["migrate", "db"])
    assert ok_args.command == "migrate"
    assert ok_args.target == "db"


def test_profiling_helpers_and_context(monkeypatch):
    # env toggles
    monkeypatch.setenv("DEMOCRAI_PROFILE_REQUESTS", "0")
    assert profiling_mod._profile_enabled() is False
    monkeypatch.setenv("DEMOCRAI_PROFILE_REQUESTS", "1")
    assert profiling_mod._profile_enabled() is True

    monkeypatch.setenv("DEMOCRAI_PROFILE_EVERY", "bad")
    assert profiling_mod._profile_every() == 100
    monkeypatch.setenv("DEMOCRAI_PROFILE_EVERY", "1")
    assert profiling_mod._should_profile("req") is True

    monkeypatch.setenv("DEMOCRAI_PROFILE_EVERY", "100")
    monkeypatch.setattr(profiling_mod.zlib, "crc32", lambda _b: 0)
    assert profiling_mod._should_profile("req") is True

    # profiler disabled branches
    p_disabled = profiling_mod.RequestProfiler("r1", "k", enabled=False)
    with p_disabled.span("x"):
        pass
    p_disabled.add_ms("x", 1.0)
    p_disabled.finish()
    assert p_disabled.spans_ms == {}

    # profiler enabled + finish log
    logs = []
    monkeypatch.setattr(
        profiling_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(info=lambda *a, **k: logs.append(a))),
    )
    tick = [1.0, 1.2, 1.5, 2.0]
    monkeypatch.setattr(profiling_mod.time, "perf_counter", lambda: tick.pop(0) if tick else 2.0)

    p = profiling_mod.RequestProfiler("r2", "kind", enabled=True)
    with p.span("db"):
        pass
    p.add_ms("db", 10)
    p.finish()
    assert "db" in p.spans_ms
    assert logs

    # start/stop/current/ensure branches
    monkeypatch.setattr(profiling_mod, "_should_profile", lambda _rid: True)
    prof, token = profiling_mod.start_request_profile("req-1", "ui")
    assert profiling_mod.current_request_profiler() is prof

    existing, token2, created = profiling_mod.ensure_request_profile("req-2", "api")
    assert existing is prof and token2 is None and created is False

    profiling_mod.stop_request_profile(token)
    assert profiling_mod.current_request_profiler() is None

    created_prof, created_token, created_flag = profiling_mod.ensure_request_profile("req-3", "api")
    assert created_flag is True
    profiling_mod.stop_request_profile(created_token)
    assert created_prof.request_id == "req-3"
