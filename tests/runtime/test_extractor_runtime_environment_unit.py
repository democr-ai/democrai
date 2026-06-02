from __future__ import annotations

from contextlib import nullcontext

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
