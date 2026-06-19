from __future__ import annotations

import builtins
import importlib
from types import SimpleNamespace

import pytest

setup_mod = importlib.import_module("democrai.core.runtime.cli.setup")


class _ConfigProvider:
    def __init__(self):
        self.config_path = "/tmp/democrai/config.yaml"
        self._config = {}
        self.saved = False

    def save(self):
        self.saved = True


class _SetupSDK:
    def __init__(self, ctx, *, fail: bool = False):
        self.calls = []
        self.ctx = ctx
        self.fail = fail

    def finalize(self, admin_user, admin_pass, *, admin_email=None):
        if self.fail:
            raise RuntimeError("finalize_down")
        self.calls.append(
            {
                "admin_user": admin_user,
                "admin_pass": admin_pass,
                "admin_email": admin_email,
            }
        )
        self.ctx.setup_mode = False


def _write_setup(path, *, password: str | None = "secret"):
    password_line = f'  password: "{password}"\n' if password is not None else ""
    path.write_text(
        f"""
admin:
  username: admin
  email: admin@example.com
{password_line}
config:
  database:
    type: sqlite
  storage:
    media:
      type: local
""".strip(),
        encoding="utf-8",
    )


def _patch_runtime(monkeypatch, ctx, setup_sdk):
    import democrai.sdk.client as sdk_client

    fake_sdk = SimpleNamespace(system=SimpleNamespace(setup=setup_sdk))
    token = sdk_client.current_sdk.set(fake_sdk)
    monkeypatch.setattr(setup_mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(setup_mod, "core_runtime_options_from_args", lambda args: args)
    monkeypatch.setattr(setup_mod, "start_core_runtime", lambda options: None)
    monkeypatch.setattr(
        setup_mod,
        "run_shutdown_cleanup",
        lambda ctx, reloader=None, child_proc=None: None,
    )
    return token, sdk_client


def test_setup_validation_requires_mapping():
    with pytest.raises(setup_mod.SetupCommandError, match="admin_must_be_mapping"):
        setup_mod._validate_setup_payload({"config": {"database": {"type": "sqlite"}}})


def test_setup_validation_requires_config():
    with pytest.raises(setup_mod.SetupCommandError, match="config_must_be_non_empty_mapping"):
        setup_mod._validate_setup_payload({"admin": {"username": "admin"}})


def test_setup_validation_requires_username():
    with pytest.raises(setup_mod.SetupCommandError, match="admin.username_required"):
        setup_mod._validate_setup_payload(
            {
                "admin": {"username": " ", "password": "secret"},
                "config": {"database": {"type": "sqlite"}},
            }
        )


def test_setup_validation_missing_env(monkeypatch):
    monkeypatch.delenv("MISSING_ADMIN_PASSWORD", raising=False)

    with pytest.raises(setup_mod.SetupCommandError, match="env_missing:admin.password"):
        setup_mod._validate_setup_payload(
            {
                "admin": {"username": "admin", "password": "${MISSING_ADMIN_PASSWORD}"},
                "config": {"database": {"type": "sqlite"}},
            }
        )


def test_setup_missing_password_without_tty(tmp_path, monkeypatch):
    config_path = tmp_path / "setup.yaml"
    _write_setup(config_path, password=None)
    monkeypatch.setattr(setup_mod.sys.stdin, "isatty", lambda: False)

    result = setup_mod.setup_application(
        config_path=str(config_path),
        yes=False,
        json_output=False,
        args=SimpleNamespace(),
    )

    assert result == 2


def test_setup_prompt_password_with_tty(tmp_path, monkeypatch):
    config_path = tmp_path / "setup.yaml"
    _write_setup(config_path, password=None)
    config_provider = _ConfigProvider()
    ctx = SimpleNamespace(setup_mode=True, config=config_provider)
    setup_sdk = _SetupSDK(ctx)
    token, sdk_client = _patch_runtime(monkeypatch, ctx, setup_sdk)
    monkeypatch.setattr(setup_mod.sys.stdin, "isatty", lambda: True)
    responses = iter(["prompt-secret", "prompt-secret"])
    monkeypatch.setattr(setup_mod.getpass, "getpass", lambda prompt: next(responses))
    monkeypatch.setattr(builtins, "input", lambda prompt: "y")

    try:
        result = setup_mod.setup_application(
            config_path=str(config_path),
            yes=False,
            json_output=False,
            args=SimpleNamespace(),
        )
    finally:
        sdk_client.current_sdk.reset(token)

    assert result == 0
    assert setup_sdk.calls[0]["admin_pass"] == "prompt-secret"


def test_setup_requires_confirmation_without_tty(tmp_path, monkeypatch):
    config_path = tmp_path / "setup.yaml"
    _write_setup(config_path)
    config_provider = _ConfigProvider()
    ctx = SimpleNamespace(setup_mode=True, config=config_provider)
    setup_sdk = _SetupSDK(ctx)
    token, sdk_client = _patch_runtime(monkeypatch, ctx, setup_sdk)
    monkeypatch.setattr(setup_mod.sys.stdin, "isatty", lambda: False)

    try:
        result = setup_mod.setup_application(
            config_path=str(config_path),
            yes=False,
            json_output=False,
            args=SimpleNamespace(),
        )
    finally:
        sdk_client.current_sdk.reset(token)

    assert result == 2
    assert config_provider.saved is False
    assert setup_sdk.calls == []


def test_setup_confirms_before_runtime_start(tmp_path, monkeypatch):
    config_path = tmp_path / "setup.yaml"
    _write_setup(config_path)
    config_provider = _ConfigProvider()
    ctx = SimpleNamespace(setup_mode=True, config=config_provider)
    setup_sdk = _SetupSDK(ctx)
    token, sdk_client = _patch_runtime(monkeypatch, ctx, setup_sdk)
    events: list[str] = []
    monkeypatch.setattr(setup_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt: events.append("confirm") or "y",
    )
    monkeypatch.setattr(
        setup_mod,
        "start_core_runtime",
        lambda options: events.append("runtime"),
    )

    try:
        result = setup_mod.setup_application(
            config_path=str(config_path),
            yes=False,
            json_output=False,
            args=SimpleNamespace(),
        )
    finally:
        sdk_client.current_sdk.reset(token)

    assert result == 0
    assert events[:2] == ["confirm", "runtime"]


def test_setup_flow_saves_config_and_finalizes(tmp_path, monkeypatch):
    config_path = tmp_path / "setup.yaml"
    _write_setup(config_path, password="${ADMIN_PASSWORD}")
    monkeypatch.setenv("ADMIN_PASSWORD", "env-secret")
    config_provider = _ConfigProvider()
    ctx = SimpleNamespace(setup_mode=True, config=config_provider)
    setup_sdk = _SetupSDK(ctx)
    token, sdk_client = _patch_runtime(monkeypatch, ctx, setup_sdk)

    try:
        result = setup_mod.setup_application(
            config_path=str(config_path),
            yes=True,
            json_output=False,
            args=SimpleNamespace(),
        )
    finally:
        sdk_client.current_sdk.reset(token)

    assert result == 0
    assert config_provider.saved is True
    assert config_provider._config["database"]["type"] == "sqlite"
    assert setup_sdk.calls == [
        {
            "admin_user": "admin",
            "admin_pass": "env-secret",
            "admin_email": "admin@example.com",
        }
    ]
    assert ctx.setup_mode is False


def test_setup_existing_installation_blocks_without_saving(tmp_path, monkeypatch):
    config_path = tmp_path / "setup.yaml"
    _write_setup(config_path)
    config_provider = _ConfigProvider()
    ctx = SimpleNamespace(setup_mode=False, config=config_provider)
    setup_sdk = _SetupSDK(ctx)
    token, sdk_client = _patch_runtime(monkeypatch, ctx, setup_sdk)

    try:
        result = setup_mod.setup_application(
            config_path=str(config_path),
            yes=True,
            json_output=False,
            args=SimpleNamespace(),
        )
    finally:
        sdk_client.current_sdk.reset(token)

    assert result == 2
    assert config_provider.saved is False
    assert setup_sdk.calls == []


def test_setup_finalize_error_returns_operational_failure(tmp_path, monkeypatch):
    config_path = tmp_path / "setup.yaml"
    _write_setup(config_path)
    config_provider = _ConfigProvider()
    ctx = SimpleNamespace(setup_mode=True, config=config_provider)
    setup_sdk = _SetupSDK(ctx, fail=True)
    token, sdk_client = _patch_runtime(monkeypatch, ctx, setup_sdk)

    try:
        result = setup_mod.setup_application(
            config_path=str(config_path),
            yes=True,
            json_output=False,
            args=SimpleNamespace(),
        )
    finally:
        sdk_client.current_sdk.reset(token)

    assert result == 1
