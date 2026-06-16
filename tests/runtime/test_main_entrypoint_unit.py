from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest


def _handle(**overrides):
    exit_code = overrides.pop("exit_code", None)
    endpoint = overrides.pop("endpoint", "ipc-endpoint")
    args = SimpleNamespace(
        mode="desktop",
        host="127.0.0.1",
        port=8000,
        workers=1,
        server_worker=False,
        dev=0,
        client=None,
        http=False,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return SimpleNamespace(args=args, endpoint=endpoint, exit_code=exit_code)


def test_main_returns_sdk_start_exit_code(monkeypatch):
    import main as main_mod

    monkeypatch.setattr(main_mod.sys, "argv", ["main.py", "config", "validate"])
    monkeypatch.setattr(main_mod, "_runtime_start", lambda app_dir=None, configure_args=None: _handle(exit_code=77))

    assert main_mod.main() == 77


def test_main_routes_server_to_master_without_runtime_start(monkeypatch):
    import main as main_mod

    observed = {}
    monkeypatch.setattr(
        main_mod.sys,
        "argv",
        ["main.py", "--mode", "server", "--workers", "2", "--dev", "1"],
    )
    monkeypatch.setattr(
        main_mod,
        "_runtime_start",
        lambda **_kwargs: observed.setdefault("runtime_start", True),
    )
    monkeypatch.setattr(
        main_mod,
        "_run_server_master",
        lambda args: (
            observed.setdefault(
                "server_master",
                (args.mode, args.workers, args.dev, args.server_worker),
            ),
            23,
        )[1],
    )

    rc = main_mod.main()

    assert rc == 23
    assert observed["server_master"] == ("server", 2, 1, False)
    assert "runtime_start" not in observed


def test_main_routes_core_worker_to_runtime_start(monkeypatch):
    import main as main_mod

    observed = {}
    handle = _handle(mode="server", workers=1, dev=0, endpoint=None)
    monkeypatch.setattr(main_mod.sys, "argv", ["main.py", "--core-worker", "--mode", "server"])
    monkeypatch.setattr(
        main_mod,
        "_runtime_start",
        lambda argv=None, app_dir=None, configure_args=None: (
            observed.setdefault("start", (argv, app_dir, configure_args)),
            handle,
        )[1],
    )
    monkeypatch.setattr(
        main_mod,
        "_wait_for_shutdown",
        lambda **kwargs: (
            observed.setdefault("wait", kwargs),
            31,
        )[1],
    )

    assert main_mod.main() == 31
    assert observed["start"][0] == ["--mode", "server"]
    assert observed["start"][1] == main_mod._runner_base_dir()
    assert callable(observed["start"][2])
    assert "wait" in observed


def test_main_server_web_client_starts_yarn_client(monkeypatch):
    import main as main_mod

    observed = {}
    client_proc = SimpleNamespace(
        poll=lambda: None,
        terminate=lambda: observed.setdefault("client_terminate", True),
    )
    monkeypatch.setattr(main_mod.sys, "argv", ["main.py", "--mode", "server", "--client", "webclient"])
    monkeypatch.setattr(
        main_mod,
        "_start_yarn_client",
        lambda client: observed.setdefault("client", client) and client_proc,
    )
    monkeypatch.setattr(
        main_mod,
        "_run_server_master",
        lambda args: (observed.setdefault("server_run", args.client), 0)[1],
    )

    assert main_mod.main() == 0
    assert observed["client"] == "webclient"
    assert observed["server_run"] == "webclient"
    assert observed["client_terminate"] is True


def test_run_desktop_mode_starts_client_and_stops(monkeypatch):
    import main as main_mod

    observed = {}
    core_proc = SimpleNamespace(
        poll=lambda: None,
        terminate=lambda: observed.setdefault("core_terminate", True),
        wait=lambda timeout=None: observed.setdefault("core_wait", timeout),
        kill=lambda: observed.setdefault("core_kill", True),
    )
    child_proc = SimpleNamespace(
        poll=lambda: 0,
        terminate=lambda: observed.setdefault("child_terminate", True),
        wait=lambda timeout=None: observed.setdefault("child_wait", timeout),
    )
    args = _handle(mode="desktop", client="qtdesktop", dev=0).args
    monkeypatch.setattr(
        main_mod,
        "_start_desktop_core_process",
        lambda args: (core_proc, "core-endpoint"),
    )
    monkeypatch.setattr(
        main_mod,
        "_start_desktop_client",
        lambda args, client, endpoint: (
            observed.setdefault("child", (client, args.host, args.port, endpoint)),
            child_proc,
        )[1],
    )
    rc = main_mod._run_desktop_mode(args)

    assert rc == 0
    assert observed["child"] == ("qtdesktop", "127.0.0.1", 8000, "core-endpoint")
    assert observed["child_terminate"] is True
    assert observed["core_terminate"] is True


def test_run_desktop_mode_starts_main_reloader_in_dev_mode(monkeypatch):
    import main as main_mod

    observed = {}
    reloader_callback = {}
    core_polls = {"count": 0}
    core_procs = [
        SimpleNamespace(
            pid=None,
            poll=lambda: None,
            terminate=lambda: observed.setdefault("core_terminate_first", True),
            wait=lambda timeout=None: observed.setdefault("core_wait_first", timeout),
            kill=lambda: observed.setdefault("core_kill_first", True),
        ),
        SimpleNamespace(
            pid=None,
            poll=lambda: 0,
            terminate=lambda: observed.setdefault("core_terminate_second", True),
            wait=lambda timeout=None: observed.setdefault("core_wait_second", timeout),
            kill=lambda: observed.setdefault("core_kill_second", True),
        ),
    ]
    child_polls = {"count": 0}

    def _child_poll():
        child_polls["count"] += 1
        if child_polls["count"] == 1:
            reloader_callback["restart_application"]()
        return None

    child_proc = SimpleNamespace(
        poll=_child_poll,
        terminate=lambda: observed.setdefault("child_terminate", True),
        wait=lambda timeout=None: observed.setdefault("child_wait", timeout),
    )
    reloader = SimpleNamespace(stop=lambda: observed.setdefault("reloader_stop", True))
    args = _handle(mode="desktop", client="qtdesktop", dev=1).args

    def _start_core(_args):
        core_polls["count"] += 1
        return core_procs[core_polls["count"] - 1], f"core-endpoint-{core_polls['count']}"

    monkeypatch.setattr(
        main_mod,
        "_start_desktop_core_process",
        _start_core,
    )
    monkeypatch.setattr(
        main_mod,
        "_kill_process_tree",
        lambda proc: observed.setdefault("core_tree_killed", proc),
    )
    monkeypatch.setattr(main_mod, "_start_desktop_client", lambda args, client, endpoint: child_proc)
    monkeypatch.setattr(
        main_mod,
        "_start_main_reloader",
        lambda **kwargs: (
            observed.setdefault("reloader_kwargs", kwargs),
            reloader_callback.update(
                {"restart_application": kwargs["restart_application"]}
            ),
            reloader,
        )[2],
    )
    assert main_mod._run_desktop_mode(args) == 0
    assert observed["reloader_kwargs"]["client_name"] == "qtdesktop"
    assert callable(observed["reloader_kwargs"]["restart_application"])
    assert observed["core_tree_killed"] is core_procs[0]
    assert core_polls["count"] == 2
    assert observed["reloader_stop"] is True
    assert observed["child_terminate"] is True
    assert observed["core_terminate_second"] is True


@pytest.mark.posix_only
def test_start_yarn_client_runs_in_selected_client_root(monkeypatch):
    import main as main_mod

    observed = {}

    class _Proc:
        pass

    proc = _Proc()
    monkeypatch.setattr(main_mod, "_runner_base_dir", lambda: "/app")
    monkeypatch.setattr(main_mod.os.path, "isdir", lambda path: path == "/app/clients/webclient")

    def _popen(cmd, cwd=None):
        observed["popen"] = (cmd, cwd)
        return proc

    monkeypatch.setattr(main_mod.subprocess, "Popen", _popen)

    assert main_mod._start_yarn_client("webclient") is proc
    assert observed["popen"] == (["yarn", "dev"], "/app/clients/webclient")


def test_start_desktop_core_process_uses_endpoint_file(monkeypatch, tmp_path):
    import main as main_mod

    observed = {}
    endpoint_file = tmp_path / "endpoint.json"

    class _Proc:
        def poll(self):
            return None

        def terminate(self):
            observed.setdefault("terminated", True)

    args = _handle(mode="desktop").args
    monkeypatch.setattr(main_mod.tempfile, "mkstemp", lambda **_kwargs: (12, str(endpoint_file)))
    monkeypatch.setattr(main_mod.os, "close", lambda fd: observed.setdefault("closed", fd))
    monkeypatch.setattr("democrai.sdk.runtime._load_master_config", lambda: None)
    real_unlink = os.unlink

    def _unlink(path):
        observed.setdefault("unlinks", []).append(path)
        try:
            real_unlink(path)
        except FileNotFoundError:
            pass

    monkeypatch.setattr(main_mod.os, "unlink", _unlink)

    def _popen(command, **kwargs):
        observed["popen"] = (command, kwargs)
        endpoint_file.write_text(json.dumps({"endpoint": "ipc"}) + "\n", encoding="utf-8")
        return _Proc()

    monkeypatch.setattr(main_mod.subprocess, "Popen", _popen)

    proc, endpoint = main_mod._start_desktop_core_process(args)

    assert isinstance(proc, _Proc)
    assert endpoint == "ipc"
    assert observed["popen"][1]["pass_fds"] == ()
    assert observed["popen"][1]["close_fds"] is True
    assert observed["popen"][1]["env"][main_mod._CORE_ENDPOINT_FILE_ENV] == str(endpoint_file)
    assert main_mod._CORE_WORKER_ARG in observed["popen"][0]


@pytest.mark.posix_only
def test_run_server_master_launches_core_workers_with_listener_fd(monkeypatch):
    import main as main_mod

    observed = {"workers": []}

    class _Listener:
        def fileno(self):
            return 44

        def close(self):
            observed["closed"] = True

    class _Proc:
        def __init__(self):
            self._polls = 0

        def poll(self):
            self._polls += 1
            return 0 if self._polls > 1 else None

        def terminate(self):
            observed.setdefault("terminated", 0)
            observed["terminated"] += 1

        def wait(self, timeout=None):
            observed.setdefault("waits", []).append(timeout)
            return 0

        def kill(self):
            observed["killed"] = True

    args = _handle(mode="server", workers=1, host="127.0.0.1", port=8000, dev=0).args
    monkeypatch.setattr(main_mod, "_create_shared_listener", lambda host, port: _Listener())
    monkeypatch.setattr(main_mod.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(main_mod.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        main_mod,
        "_start_core_worker",
        lambda worker_args, pass_fds=(): (
            observed["workers"].append((worker_args, pass_fds)),
            _Proc(),
        )[1],
    )

    assert main_mod._run_server_master(args) == 0
    worker_args, pass_fds = observed["workers"][0]
    assert worker_args.server_worker is True
    assert worker_args.listen_fd == 44
    assert pass_fds == (44,)
    assert observed["closed"] is True


def test_start_core_worker_uses_sandbox_launch_strategy(monkeypatch):
    import main as main_mod

    observed = {}
    config = SimpleNamespace(get=lambda key, default=None: True if key == "sandbox.os.enabled" else default)
    proc = SimpleNamespace(poll=lambda: None)

    class _Strategy:
        def spawn(self, policy, *, pass_fds=()):
            observed["spawn"] = (policy, pass_fds)
            return proc

    monkeypatch.setattr("democrai.sdk.runtime._load_master_config", lambda: config)

    def _build_policy(cfg, command, env, cwd, runtime_mode=None):
        observed["policy_input"] = (cfg, command, env, cwd, runtime_mode)
        return SimpleNamespace(command=command, env=env, cwd=cwd)

    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.core_relaunch.build_core_worker_launch_policy",
        _build_policy,
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.factory.get_core_launch_strategy",
        lambda: _Strategy(),
    )
    monkeypatch.setattr("democrai.sdk.runtime._spawn_broker_required", lambda: False)

    args = _handle(mode="desktop").args
    assert main_mod._start_core_worker(args, env={"A": "B"}, pass_fds=(9,)) is proc
    cfg, command, env, cwd, runtime_mode = observed["policy_input"]
    assert cfg is config
    assert main_mod._CORE_WORKER_ARG in command
    assert env[main_mod._CORE_CHILD_ENV] == "1"
    assert cwd
    assert runtime_mode == "desktop"
    assert observed["spawn"][1] == (9,)


def test_start_core_worker_passes_spawn_broker_env(monkeypatch):
    import main as main_mod

    observed = {}
    config = SimpleNamespace(get=lambda key, default=None: True if key == "sandbox.os.enabled" else default)
    proc = SimpleNamespace(poll=lambda: None)
    broker = SimpleNamespace(close=lambda: observed.setdefault("broker_closed", True))

    class _Strategy:
        def spawn(self, policy, *, pass_fds=()):
            observed["spawn"] = (policy, pass_fds)
            return proc

    def _build_policy(cfg, command, env, cwd, runtime_mode=None):
        observed["policy_input"] = (cfg, command, env, cwd, runtime_mode)
        return SimpleNamespace(command=command, env=env, cwd=cwd)

    monkeypatch.setattr("democrai.sdk.runtime._load_master_config", lambda: config)
    monkeypatch.setattr("democrai.sdk.runtime._spawn_broker_required", lambda: True)
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.spawn_broker.start_spawn_broker",
        lambda: broker,
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.spawn_broker.broker_env",
        lambda value: {"DEMOCRAI_SANDBOX_SPAWN_BROKER_SOCKET": "sock", "DEMOCRAI_SANDBOX_SPAWN_BROKER_TOKEN": "tok"},
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.core_relaunch.build_core_worker_launch_policy",
        _build_policy,
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.sandbox.os.factory.get_core_launch_strategy",
        lambda: _Strategy(),
    )

    args = _handle(mode="desktop").args
    assert main_mod._start_core_worker(args, env={"A": "B"}) is proc
    _cfg, _command, env, _cwd, _runtime_mode = observed["policy_input"]
    assert env["DEMOCRAI_SANDBOX_SPAWN_BROKER_SOCKET"] == "sock"
    assert env["DEMOCRAI_SANDBOX_SPAWN_BROKER_TOKEN"] == "tok"
    main_mod._close_spawn_broker_for_process(proc)
    assert observed["broker_closed"] is True


def test_configure_runtime_args_delegates_desktop_launcher(monkeypatch):
    import main as main_mod

    observed = {}
    args = SimpleNamespace(mode="desktop", client="tauri")
    monkeypatch.setattr(
        main_mod,
        "_configure_desktop_client_runtime",
        lambda runtime_args, client_name: observed.setdefault("configure", (runtime_args, client_name)),
    )

    main_mod._configure_runtime_args(args)

    assert observed["configure"] == (args, "tauri")


def test_configure_runtime_args_ignores_server(monkeypatch):
    import main as main_mod

    observed = {}
    args = SimpleNamespace(mode="server", client="webclient")
    monkeypatch.setattr(
        main_mod,
        "_configure_desktop_client_runtime",
        lambda *_args: observed.setdefault("called", True),
    )

    main_mod._configure_runtime_args(args)

    assert "called" not in observed


def test_launcher_does_not_import_democrai_core():
    import main as main_mod

    with open(main_mod.__file__, "r", encoding="utf-8") as handle:
        source = handle.read()

    assert "democrai.core" not in source
