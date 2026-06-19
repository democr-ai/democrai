from __future__ import annotations

import importlib
from types import SimpleNamespace


install_extractors_mod = importlib.import_module("democrai.core.runtime.cli.install_extractors")


class _Report:
    def has_errors(self):
        return False

    def to_dict(self):
        return {
            "status": "ok",
            "extractors": {"installed": [], "activated": [], "skipped": [], "errors": []},
            "mime_bindings": [],
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
extractors:
  - id: docling
    mime_bindings:
      - text/plain
  - id: ai_audio
""".strip(),
        encoding="utf-8",
    )


def _patch_runtime(monkeypatch, audit_store):
    ctx = SimpleNamespace(setup_mode=False, observability_store=audit_store)
    monkeypatch.setattr(install_extractors_mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(install_extractors_mod, "core_runtime_options_from_args", lambda args: args)
    monkeypatch.setattr(install_extractors_mod, "start_core_runtime", lambda options: None)
    monkeypatch.setattr(
        install_extractors_mod,
        "run_shutdown_cleanup",
        lambda ctx, reloader=None, child_proc=None: None,
    )

    async def _fake_install(*args, **kwargs):
        return _Report()

    monkeypatch.setattr(install_extractors_mod, "install_extractors_from_config", _fake_install)
    monkeypatch.setattr(
        install_extractors_mod,
        "install_extractors_config_audit_metadata",
        lambda config: {"extractors": ["docling", "ai_audio"], "extractor_count": 2},
    )


def test_install_extractors_records_cli_audit_event(tmp_path, monkeypatch):
    config_path = tmp_path / "extractors.yaml"
    _write_config(config_path)
    audit_store = _AuditStore()
    _patch_runtime(monkeypatch, audit_store)

    result = install_extractors_mod.install_extractors(
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
    assert event["entity_id"] == "install-extractors"
    assert event["operation"] == "install-extractors"
    assert event["status"] == "started"
    assert event["actor_user_id"] == 0
    assert event["actor_role"] == "core"
    assert event["channel"] == "cli"
    assert event["metadata"]["command"] == "install-extractors"
    assert event["metadata"]["reset_mode"] == "selected"
    assert event["metadata"]["extractors"] == ["docling", "ai_audio"]
    assert event["metadata"]["extractor_count"] == 2


def test_install_extractors_audit_failure_does_not_block_command(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "extractors.yaml"
    _write_config(config_path)
    audit_store = _AuditStore(fail=True)
    _patch_runtime(monkeypatch, audit_store)

    result = install_extractors_mod.install_extractors(
        config_path=str(config_path),
        reset_mode="keep",
        yes=False,
        json_output=False,
        args=SimpleNamespace(),
    )

    assert result == 0
    assert "audit_not_recorded:audit_down" in capsys.readouterr().err
