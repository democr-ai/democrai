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


def test_extractor_cache_env_does_not_emit_docling_specific_env(monkeypatch, tmp_path):
    import democrai.core.runtime.dependencies.extractor_env as mod

    monkeypatch.setattr(mod, "get_extractor_local_env_path", lambda _id=None: tmp_path / "env")
    monkeypatch.setattr(mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")
    monkeypatch.setattr(mod, "get_extractor_local_config_path", lambda _id=None: tmp_path / "config")
    monkeypatch.setattr(mod, "get_extractor_local_tmp_path", lambda _id=None: tmp_path / "tmp")

    env = mod._extractor_cache_env("docling")

    assert env["HF_HOME"] == str(tmp_path / "cache" / "huggingface")
    assert env["HF_HUB_CACHE"] == str(tmp_path / "cache" / "huggingface" / "hub")
    assert env["HUGGINGFACE_HUB_CACHE"] == str(tmp_path / "cache" / "huggingface" / "hub")
    assert env["MODELSCOPE_CACHE"] == str(tmp_path / "cache" / "modelscope")
    assert env["MPLCONFIGDIR"] == str(tmp_path / "config" / "matplotlib")
    assert env["TORCH_HOME"] == str(tmp_path / "cache" / "torch")


def test_clean_worker_env_removes_generic_extractor_env(monkeypatch, tmp_path):
    import democrai.core.application.knowledge.extractor.worker_subject as mod

    monkeypatch.setenv("HF_HOME", str(tmp_path / "external" / "hf"))
    monkeypatch.setenv("KEEP_ME", "1")

    env = mod._clean_worker_env()

    assert "HF_HOME" not in env
    assert env["KEEP_ME"] == "1"


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


@pytest.mark.posix_only
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


@pytest.mark.posix_only
def test_extractor_access_reads_resolved_venv_python(monkeypatch, tmp_path):
    import democrai.core.application.knowledge.extractor.runtime as mod

    venv_root = tmp_path / "extractor_env_cache" / "docling" / ".venv"
    uv_python = tmp_path / "uv" / "python" / "bin" / "python3.12"
    monkeypatch.setattr(mod, "_extractor_phase_section", lambda *_args: {})
    monkeypatch.setattr(mod, "get_extractor_local_env_path", lambda _id=None: tmp_path / "env")
    monkeypatch.setattr(mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")
    monkeypatch.setattr(mod, "get_extractor_local_config_path", lambda _id=None: tmp_path / "config")
    monkeypatch.setattr(mod, "get_extractor_local_tmp_path", lambda _id=None: tmp_path / "tmp")
    monkeypatch.setattr(mod, "get_extractor_venv_path", lambda _id=None: venv_root)
    monkeypatch.setattr(
        mod,
        "get_extractor_venv_python_path",
        lambda _id=None: venv_root / "bin" / "python",
    )
    monkeypatch.setattr(
        mod.os.path,
        "realpath",
        lambda path, *args, **kwargs: str(uv_python)
        if str(path).endswith(".venv/bin/python")
        else str(path),
    )
    monkeypatch.setattr(mod, "extractor_runtime_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_system_probe_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_dependency_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_create_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_modify_paths", lambda: ())

    resources = {
        (
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in mod.get_extractor_access("docling", "install")
        if rule.resource.resource_type.value == "filesystem"
    }

    venv_python = str((venv_root / "bin" / "python").resolve())
    resolved_python = str(uv_python.resolve())
    assert ("read", venv_python) in resources
    assert ("read", resolved_python) in resources
    assert ("execute", venv_python) in resources
    assert ("execute", resolved_python) in resources


@pytest.mark.posix_only
def test_extractor_access_reads_python_executable_symlink_chain(monkeypatch, tmp_path):
    import democrai.core.application.knowledge.extractor.runtime as mod

    bin_root = tmp_path / "bin"
    final_root = tmp_path / "runtime" / "bin"
    bin_root.mkdir(parents=True)
    final_root.mkdir(parents=True)
    first = bin_root / "python"
    second = bin_root / "python3.12"
    third = tmp_path / "local" / "bin" / "python3.12"
    third.parent.mkdir(parents=True)
    final = final_root / "python3.12"
    final.write_text("", encoding="utf-8")
    first.symlink_to("python3.12")
    second.symlink_to(third)
    third.symlink_to(final)
    monkeypatch.setattr(mod, "_extractor_phase_section", lambda *_args: {})
    monkeypatch.setattr(mod, "get_extractor_local_env_path", lambda _id=None: tmp_path / "env")
    monkeypatch.setattr(mod, "get_extractor_local_cache_path", lambda _id=None: tmp_path / "cache")
    monkeypatch.setattr(mod, "get_extractor_local_config_path", lambda _id=None: tmp_path / "config")
    monkeypatch.setattr(mod, "get_extractor_local_tmp_path", lambda _id=None: tmp_path / "tmp")
    monkeypatch.setattr(mod, "get_extractor_venv_path", lambda _id=None: tmp_path / "env" / ".venv")
    monkeypatch.setattr(mod, "get_extractor_venv_python_path", lambda _id=None: first)
    monkeypatch.setattr(mod.sys, "executable", str(first))
    monkeypatch.setattr(mod, "extractor_runtime_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_system_probe_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_dependency_read_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_create_paths", lambda: ())
    monkeypatch.setattr(mod, "extractor_runtime_modify_paths", lambda: ())

    resources = {
        (
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in mod.get_extractor_access("docling", "install")
        if rule.resource.resource_type.value == "filesystem"
    }

    for path in (first, second, third, final):
        assert ("read", str(path.resolve(strict=False))) in resources
        assert ("execute", str(path.resolve(strict=False))) in resources


@pytest.mark.posix_only
def test_model_registry_extractor_runtime_can_resolve_orchestrator_socket():
    import democrai.core.application.knowledge.extractor.runtime as mod
    from democrai.core.application.ai.engine.orchestrator.config import (
        EngineOrchestratorConfig,
    )
    from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
    from democrai.core.runtime.foundation.paths import runtime_ipc_dir

    ipc_dir = str(runtime_ipc_dir().resolve())
    resources = {
        (
            rule.subject.subject_type,
            rule.subject.subject_name,
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in mod.get_extractor_access("ai_audio", "runtime")
        if rule.resource.resource_type.value == "filesystem"
    }

    assert ("extractor", "ai_audio", "read", ipc_dir) in resources
    with process_guard_context(
        subject="ai_audio",
        subject_kind="extractor",
        access=mod.get_extractor_access("ai_audio", "runtime"),
        include_runtime_access=False,
        inherit_parent_access=False,
    ):
        assert EngineOrchestratorConfig.load(None).socket_path.endswith(
            "engine-orchestrator.sock"
        )


def test_plain_extractor_runtime_does_not_get_orchestrator_ipc_access():
    import democrai.core.application.knowledge.extractor.runtime as mod
    from democrai.core.runtime.foundation.paths import runtime_ipc_dir

    ipc_dir = str(runtime_ipc_dir().resolve())
    resources = {
        (
            rule.resource.operation.value,
            rule.resource.normalized_target,
        )
        for rule in mod.get_extractor_access("docling", "runtime")
        if rule.resource.resource_type.value == "filesystem"
    }

    assert ("read", ipc_dir) not in resources


def test_docling_manifest_does_not_declare_ineffective_execute_allowlist():
    manifest = json.loads(Path("extractors/docling/manifest.json").read_text(encoding="utf-8"))
    install = manifest["install"]

    assert all(
        item.get("target") not in {"/sbin/ldconfig", "/usr/sbin/ldconfig"}
        for item in install["access"]
    )
    assert "access_by_os" not in install
