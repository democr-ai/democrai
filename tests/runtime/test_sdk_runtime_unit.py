from __future__ import annotations

from types import SimpleNamespace


def test_sdk_runtime_helper_uses_current_process_argv(monkeypatch):
    from democrai.sdk import runtime
    from democrai.core.runtime import cli, launcher

    observed = {}
    args = SimpleNamespace(os_sandbox_helper_process=True)
    monkeypatch.setattr(runtime.sys, "argv", ["main.py", "--os-sandbox-helper-process"])
    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda argv: (observed.setdefault("parse_argv", list(argv)), args)[1],
    )
    monkeypatch.setattr(
        launcher,
        "_run_helper_process",
        lambda argv: (observed.setdefault("helper_argv", list(argv)), 42)[1],
    )

    handle = runtime.start()

    assert handle.args is args
    assert handle.exit_code == 42
    assert observed["parse_argv"] == ["--os-sandbox-helper-process"]
    assert observed["helper_argv"] == ["--os-sandbox-helper-process"]


def test_sdk_runtime_start_returns_endpoint(monkeypatch):
    from democrai.sdk import runtime
    from democrai.core.platform.utils import env
    from democrai.core.runtime import cli, entrypoint

    observed = {}
    args = SimpleNamespace(
        os_sandbox_helper_process=False,
        mode="desktop",
        port=9010,
        workers=1,
        server_worker=False,
    )
    monkeypatch.setattr(cli, "parse_args", lambda argv: args)
    monkeypatch.setattr(cli, "handle_cli_command", lambda runtime_args: None)
    monkeypatch.setattr(env, "build_desktop_ipc_server_name", lambda port: f"ipc-{port}")

    def _options_from_args(runtime_args):
        observed["options_args"] = runtime_args
        return "options"

    def _start_core_runtime(options):
        observed["options"] = options
        return "unix:/tmp/demo.sock"

    monkeypatch.setattr(
        entrypoint,
        "core_runtime_options_from_args",
        _options_from_args,
    )
    monkeypatch.setattr(
        entrypoint,
        "start_core_runtime",
        _start_core_runtime,
    )

    handle = runtime.start(argv=["--mode", "desktop"])

    assert handle.args is args
    assert handle.endpoint == "unix:/tmp/demo.sock"
    assert handle.exit_code is None
    assert observed["options_args"] is args
    assert observed["options"] == "options"
