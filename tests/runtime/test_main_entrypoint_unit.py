from __future__ import annotations

import json
import os
from types import SimpleNamespace


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

    monkeypatch.setattr(main_mod, "start", lambda app_dir=None, configure_args=None: _handle(exit_code=77))

    assert main_mod.main() == 77


def test_main_routes_multi_worker_server_without_second_core_start(monkeypatch):
    import main as main_mod

    observed = {}
    handle = _handle(mode="server", workers=2, dev=1)
    monkeypatch.setattr(
        main_mod,
        "start",
        lambda app_dir=None, configure_args=None: (
            observed.setdefault("start", (app_dir, configure_args)),
            handle,
        )[1],
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
    assert callable(observed["start"][1])


def test_main_degrades_windows_multi_worker_server_to_single_worker(monkeypatch):
    import main as main_mod

    observed = {}
    handle = _handle(mode="server", workers=2, dev=0)
    monkeypatch.setattr(main_mod.os, "name", "nt")
    monkeypatch.setattr(main_mod, "start", lambda app_dir=None, configure_args=None: handle)
    monkeypatch.setattr(
        main_mod,
        "_run_server_master",
        lambda args: observed.setdefault("server_master", args.workers),
    )
    monkeypatch.setattr(
        main_mod,
        "_wait_for_shutdown",
        lambda **kwargs: (
            observed.setdefault("wait_workers", handle.args.workers),
            0,
        )[1],
    )

    rc = main_mod.main()

    assert rc == 0
    assert handle.args.workers == 1
    assert observed["wait_workers"] == 1
    assert "server_master" not in observed


def test_main_server_web_client_starts_yarn_client(monkeypatch):
    import main as main_mod

    observed = {}
    client_proc = SimpleNamespace(
        poll=lambda: None,
        terminate=lambda: observed.setdefault("client_terminate", True),
    )
    handle = _handle(mode="server", client="webclient")
    monkeypatch.setattr(main_mod, "start", lambda app_dir=None, configure_args=None: handle)
    monkeypatch.setattr(
        main_mod,
        "_start_yarn_client",
        lambda client: observed.setdefault("client", client) and client_proc,
    )
    monkeypatch.setattr(
        main_mod,
        "_wait_for_shutdown",
        lambda **kwargs: (
            observed.setdefault("server_run", kwargs.get("child_proc")),
            0,
        )[1],
    )

    assert main_mod.main() == 0
    assert observed["client"] == "webclient"
    assert observed["server_run"] == client_proc


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
    monkeypatch.setattr(
        main_mod,
        "stop",
        lambda reloader=None, child_proc=None: observed.setdefault("stop", (reloader, child_proc)),
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


def test_start_desktop_core_process_posix_uses_pass_fds(monkeypatch):
    import main as main_mod

    observed = {}
    proc = SimpleNamespace(
        terminate=lambda: observed.setdefault("terminated", True),
    )
    args = _handle(mode="desktop").args
    monkeypatch.setattr(main_mod.os, "name", "posix")
    monkeypatch.setattr(main_mod.os, "pipe", lambda: (10, 11))
    monkeypatch.setattr(main_mod.os, "close", lambda fd: observed.setdefault("closed", fd))
    monkeypatch.setattr(
        main_mod,
        "_read_core_endpoint",
        lambda fd: (observed.setdefault("read_fd", fd), "ipc")[1],
    )

    def _popen(command, **kwargs):
        observed["popen"] = (command, kwargs)
        return proc

    monkeypatch.setattr(main_mod.subprocess, "Popen", _popen)

    assert main_mod._start_desktop_core_process(args) == (proc, "ipc")
    assert observed["popen"][1]["pass_fds"] == (11,)
    assert observed["popen"][1]["close_fds"] is True
    assert observed["popen"][1]["env"][main_mod._CORE_ENDPOINT_FD_ENV] == "11"
    assert main_mod._CORE_ENDPOINT_FILE_ENV not in observed["popen"][1]["env"]
    assert observed["closed"] == 11
    assert observed["read_fd"] == 10


def test_start_desktop_core_process_windows_uses_endpoint_file(monkeypatch, tmp_path):
    import main as main_mod

    observed = {}
    endpoint_file = tmp_path / "endpoint.json"

    class _Proc:
        def poll(self):
            return None

        def terminate(self):
            observed.setdefault("terminated", True)

    args = _handle(mode="desktop").args
    monkeypatch.setattr(main_mod.os, "name", "nt")
    monkeypatch.setattr(main_mod.tempfile, "mkstemp", lambda **_kwargs: (12, str(endpoint_file)))
    monkeypatch.setattr(main_mod.os, "close", lambda fd: observed.setdefault("closed", fd))
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
    assert "pass_fds" not in observed["popen"][1]
    assert observed["popen"][1]["close_fds"] is True
    assert observed["popen"][1]["env"][main_mod._CORE_ENDPOINT_FILE_ENV] == str(endpoint_file)
    assert main_mod._CORE_ENDPOINT_FD_ENV not in observed["popen"][1]["env"]


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
