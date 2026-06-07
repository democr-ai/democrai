from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

import pytest


def test_extractor_install_runtime_applies_manifest_environment(monkeypatch):
    import democrai.core.application.knowledge.extractor.runtime as mod

    captured: dict[str, dict[str, str] | None] = {}

    class _Extractor:
        @classmethod
        def _install_local(cls, **_kwargs):
            return {"ok": True}

    def _extractor_env_context(extractor_id, env=None):
        captured["extractor_id"] = extractor_id
        captured["env"] = env
        return nullcontext()

    monkeypatch.setattr(mod, "process_guard_context", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(mod, "get_extractor_access", lambda *_args: ())
    monkeypatch.setattr(mod, "get_extractor_allowed_imports", lambda *_args: [])
    monkeypatch.setattr(
        mod,
        "get_extractor_environment",
        lambda *_args: {"HF_HUB_DISABLE_XET": "1"},
    )
    monkeypatch.setattr(mod, "extractor_env_context", _extractor_env_context)
    monkeypatch.setattr(mod, "isolate_extractor_imports", lambda *_args: None)
    monkeypatch.setattr(mod, "load_extractor_class", lambda *_args: _Extractor)

    assert mod.install_extractor_runtime(extractor_id="docling") == {"ok": True}
    assert captured == {
        "extractor_id": "docling",
        "env": {"HF_HUB_DISABLE_XET": "1"},
    }


def test_extractor_environment_rejects_invalid_manifest_values(monkeypatch):
    import democrai.core.application.knowledge.extractor.runtime as mod

    monkeypatch.setattr(
        mod,
        "_extractor_phase_section",
        lambda *_args: {"environment": {"VALID": "1", "BROKEN": 1}},
    )

    with pytest.raises(ValueError, match="invalid_extractor_environment"):
        mod.get_extractor_environment("docling", "install")


def test_extractor_access_by_os_filters_linux_only_paths(monkeypatch, tmp_path):
    import democrai.core.application.knowledge.extractor.runtime as mod

    section = {
        "access": [
            {
                "resource_type": "network",
                "operation": "receive",
                "target": "https://pypi.org/*",
            },
        ],
        "access_by_os": {
            "linux": [
                {
                    "resource_type": "filesystem",
                    "operation": "execute",
                    "target": "/sbin/ldconfig",
                },
            ],
        },
    }
    monkeypatch.setattr(mod, "_extractor_phase_section", lambda *_args: section)
    monkeypatch.setattr(mod, "get_extractor_local_env_path", lambda _id=None: tmp_path / "env")
    monkeypatch.setattr(mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")
    monkeypatch.setattr(mod, "get_extractor_local_config_path", lambda _id=None: tmp_path / "config")
    monkeypatch.setattr(mod, "get_extractor_local_tmp_path", lambda _id=None: tmp_path / "tmp")
    monkeypatch.setattr(mod, "extractor_runtime_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_system_probe_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_dependency_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_create_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_modify_paths", lambda: ())

    monkeypatch.setattr(mod, "os_key", lambda: "linux")
    linux_targets = {
        rule.resource.target
        for rule in mod.get_extractor_access("docling", "install")
    }
    assert "/sbin/ldconfig" in linux_targets

    monkeypatch.setattr(mod, "os_key", lambda: "darwin")
    darwin_targets = {
        rule.resource.target
        for rule in mod.get_extractor_access("docling", "install")
    }
    assert "/sbin/ldconfig" not in darwin_targets
    assert section["access"] == [
        {
            "resource_type": "network",
            "operation": "receive",
            "target": "https://pypi.org/*",
        },
    ]


def test_extractor_access_includes_runtime_system_and_dependency_reads(monkeypatch, tmp_path):
    import democrai.core.application.knowledge.extractor.runtime as mod

    monkeypatch.setattr(mod, "_extractor_phase_section", lambda *_args: {})
    monkeypatch.setattr(mod, "get_extractor_local_env_path", lambda _id=None: tmp_path / "env")
    monkeypatch.setattr(mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")
    monkeypatch.setattr(mod, "get_extractor_local_config_path", lambda _id=None: tmp_path / "config")
    monkeypatch.setattr(mod, "get_extractor_local_tmp_path", lambda _id=None: tmp_path / "tmp")
    monkeypatch.setattr(mod, "get_extractor_venv_path", lambda _id=None: tmp_path / "env" / ".venv")
    monkeypatch.setattr(mod, "get_extractor_venv_python_path", lambda _id=None: tmp_path / "env" / ".venv" / "bin" / "python")
    monkeypatch.setattr(mod, "extractor_runtime_read_paths", lambda: ("/dev/null",))
    monkeypatch.setattr(mod, "extractor_runtime_system_probe_read_paths", lambda: ("/etc/os-release",))
    monkeypatch.setattr(mod, "extractor_runtime_dependency_read_paths", lambda: ("/usr", "/lib"))
    monkeypatch.setattr(mod, "extractor_runtime_create_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_modify_paths", lambda: ())

    resources = {
        (
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in mod.get_extractor_access("docling", "runtime")
        if rule.resource.resource_type.value == "filesystem"
    }

    assert ("read", "/dev/null") in resources
    assert ("read", "/etc/os-release") in resources
    assert ("read", "/usr") in resources
    assert ("read", "/lib") in resources
    assert ("modify", "/usr") not in resources
    assert ("create", "/usr") not in resources


def test_docling_manifest_does_not_declare_ineffective_execute_allowlist():
    manifest = json.loads(Path("extractors/docling/manifest.json").read_text(encoding="utf-8"))
    install = manifest["install"]

    assert all(
        item.get("target") not in {"/sbin/ldconfig", "/usr/sbin/ldconfig"}
        for item in install["access"]
    )
    assert "access_by_os" not in install
