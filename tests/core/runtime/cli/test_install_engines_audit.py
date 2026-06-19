from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from democrai.core.runtime.foundation.app import req_ctx

install_engines_mod = importlib.import_module("democrai.core.runtime.cli.install_engines")


class _Report:
    def has_errors(self):
        return False

    def to_dict(self):
        return {
            "status": "ok",
            "engines": {"installed": [], "activated": [], "skipped": [], "errors": []},
            "models": {"downloaded": [], "activated": [], "skipped": [], "errors": []},
        }


class _AuditStore:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.events = []

    def record_audit_event(self, **kwargs):
        if self.fail:
            raise RuntimeError("audit_down")
        self.events.append(kwargs)
        return SimpleNamespace(id=1)


def _write_config(path):
    path.write_text(
        """
engines:
  - provider: openai
    name: openai-main
  - provider: ollama
    instances:
      - name: ollama-local-a
      - name: ollama-local-b
""".strip(),
        encoding="utf-8",
    )


def _patch_runtime(monkeypatch, audit_store):
    ctx = SimpleNamespace(setup_mode=False, observability_store=audit_store)
    monkeypatch.setattr(install_engines_mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(install_engines_mod, "core_runtime_options_from_args", lambda args: args)
    monkeypatch.setattr(install_engines_mod, "start_core_runtime", lambda options: None)
    monkeypatch.setattr(
        install_engines_mod,
        "run_shutdown_cleanup",
        lambda ctx, reloader=None, child_proc=None: None,
    )

    async def _fake_install(*args, **kwargs):
        return _Report()

    monkeypatch.setattr(install_engines_mod, "install_engines_from_config", _fake_install)


def test_install_engines_records_cli_audit_event(tmp_path, monkeypatch):
    config_path = tmp_path / "engines.yaml"
    _write_config(config_path)
    audit_store = _AuditStore()
    _patch_runtime(monkeypatch, audit_store)

    result = install_engines_mod.install_engines(
        config_path=str(config_path),
        reset_mode="selected",
        yes=False,
        json_output=False,
        args=SimpleNamespace(),
    )

    assert result == 0
    assert len(audit_store.events) == 1
    event = audit_store.events[0]
    assert event["event_type"] == "cli_command"
    assert event["entity_type"] == "runtime_command"
    assert event["entity_id"] == "install-engines"
    assert event["operation"] == "install-engines"
    assert event["status"] == "started"
    assert event["actor_user_id"] == 0
    assert event["actor_role"] == "core"
    assert event["channel"] == "cli"
    assert event["metadata"]["command"] == "install-engines"
    assert event["metadata"]["reset_mode"] == "selected"
    assert event["metadata"]["providers"] == ["openai", "ollama"]
    assert event["metadata"]["engine_count"] == 3


def test_install_engines_audit_failure_does_not_block_command(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "engines.yaml"
    _write_config(config_path)
    audit_store = _AuditStore(fail=True)
    _patch_runtime(monkeypatch, audit_store)

    result = install_engines_mod.install_engines(
        config_path=str(config_path),
        reset_mode="keep",
        yes=False,
        json_output=False,
        args=SimpleNamespace(),
    )

    assert result == 0
    assert "audit_not_recorded:audit_down" in capsys.readouterr().err


def test_install_engines_full_reset_pre_resets_before_runtime_start(tmp_path, monkeypatch):
    config_path = tmp_path / "engines.yaml"
    _write_config(config_path)
    audit_store = _AuditStore()
    _patch_runtime(monkeypatch, audit_store)
    events = []

    def _start_runtime(options):
        events.append("start_runtime")

    async def _fake_install(*args, **kwargs):
        events.append("install_begin")
        assert kwargs["reset_mode"] == "full"
        return _Report()

    monkeypatch.setattr(install_engines_mod, "start_core_runtime", _start_runtime)
    monkeypatch.setattr(install_engines_mod, "install_engines_from_config", _fake_install)
    monkeypatch.setattr(
        install_engines_mod,
        "reset_full_engine_state_before_runtime_start",
        lambda **kwargs: events.append("pre_reset"),
    )

    result = install_engines_mod.install_engines(
        config_path=str(config_path),
        reset_mode="full",
        yes=True,
        json_output=False,
        args=SimpleNamespace(),
    )

    assert result == 0
    assert events == [
        "pre_reset",
        "start_runtime",
        "install_begin",
    ]


def test_install_engines_runs_install_with_core_request_context(tmp_path, monkeypatch):
    config_path = tmp_path / "engines.yaml"
    _write_config(config_path)
    audit_store = _AuditStore()
    _patch_runtime(monkeypatch, audit_store)
    captured = {}

    async def _fake_install(*args, **kwargs):
        current = req_ctx()
        captured["module_name"] = current.module_name
        captured["channel"] = current.channel
        captured["user"] = current.user
        captured["action_name"] = current.action_name
        return _Report()

    monkeypatch.setattr(install_engines_mod, "install_engines_from_config", _fake_install)

    result = install_engines_mod.install_engines(
        config_path=str(config_path),
        reset_mode="keep",
        yes=False,
        json_output=False,
        args=SimpleNamespace(),
    )

    assert result == 0
    assert captured == {
        "module_name": "core",
        "channel": "cli",
        "user": 0,
        "action_name": "install-engines",
    }
    with pytest.raises(LookupError):
        req_ctx()
