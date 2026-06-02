from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import democrai.core.infrastructure.modules.compat as compat_mod
import democrai.core.infrastructure.modules.runtime as runtime_mod


def test_compat_remaining_branches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(compat_mod, "cron_matches", lambda expr, candidate: False)
    with pytest.raises(ValueError):
        compat_mod.next_cron_run("* * * * *", datetime(2026, 1, 1, 0, 0))

    assert compat_mod.resolve_module_resource(str(tmp_path), None) is None
    assert compat_mod.resolve_module_resource(str(tmp_path), 123) == 123
    assert compat_mod.resolve_module_resource(str(tmp_path), "icon.svg") == "icon.svg"
    assert compat_mod.module_version_match("1.0.0", "1.0.0") is True

    monkeypatch.setattr(compat_mod.sys, "version_info", SimpleNamespace(major=3, minor=12))
    monkeypatch.setattr(compat_mod, "SDK_VERSION", "2.0.0")
    monkeypatch.setattr(compat_mod, "CURRENT_PLATFORM", "linux")
    monkeypatch.setattr(compat_mod, "CURRENT_ARCH", "x86_64")

    module_py_bad = SimpleNamespace(
        requirements={"python": ">=99.0"},
        _version_match=compat_mod.module_version_match,
        type="python",
        platforms={},
        error_message=None,
    )
    assert compat_mod.validate_compatibility(module_py_bad) is False
    assert "Requires Python" in (module_py_bad.error_message or "")

    module_py_ok = SimpleNamespace(
        requirements={},
        _version_match=compat_mod.module_version_match,
        type="python",
        platforms={},
        error_message=None,
    )
    assert compat_mod.validate_compatibility(module_py_ok) is True

    module_plat_bad = SimpleNamespace(
        requirements={},
        _version_match=compat_mod.module_version_match,
        type="extension",
        platforms={"windows": {"arch": ["x86_64"]}},
        error_message=None,
    )
    assert compat_mod.validate_compatibility(module_plat_bad) is False
    assert "does not support platform" in (module_plat_bad.error_message or "")

    module_ext_abi_bad = SimpleNamespace(
        requirements={},
        _version_match=compat_mod.module_version_match,
        type="extension",
        platforms={"linux": {"arch": ["x86_64"], "abi": "cp399"}},
        error_message=None,
    )
    assert compat_mod.validate_compatibility(module_ext_abi_bad) is False
    assert "ABI mismatch" in (module_ext_abi_bad.error_message or "")


@pytest.mark.asyncio
async def test_runtime_remaining_branches(tmp_path: Path, monkeypatch):
    comp = runtime_mod._SerializedComponent({"id": "abc", "x": 1})
    assert comp.id == "abc"
    assert comp.to_dict() == {"id": "abc", "x": 1}

    base = tmp_path / "base"
    base.mkdir()
    module_path = tmp_path / "mod"
    deps_path = module_path / "deps"
    deps_path.mkdir(parents=True)
    old_sys_path = list(runtime_mod.sys.path)
    try:
        runtime_mod.sys.path[:] = []
        runtime_mod._install_module_import_paths(str(module_path), is_builtin=True)
        assert str(deps_path) in runtime_mod.sys.path
        assert str(tmp_path.resolve().parent) in runtime_mod.sys.path

        runtime_mod.sys.path[:] = []
        runtime_mod._install_module_import_paths(str(module_path), is_builtin=False)
        assert str(module_path.resolve().parent) in runtime_mod.sys.path
    finally:
        runtime_mod.sys.path[:] = old_sys_path

    current_sdk = SimpleNamespace(set=lambda _sdk: "tok", reset=lambda _tok: None)

    class _SDK:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setitem(
        sys.modules,
        "democrai.sdk.client",
        SimpleNamespace(SDK=_SDK, current_sdk=current_sdk),
    )
    monkeypatch.setattr(runtime_mod, "set_req_ctx", lambda _ctx: "r")
    monkeypatch.setattr(runtime_mod, "reset_req_ctx", lambda _tok: None)
    monkeypatch.setattr(runtime_mod, "app_ctx", lambda: SimpleNamespace(module_runtime=None))

    subject = runtime_mod._ModuleRuntimeSubject(module_name="m", module_path=str(module_path), is_builtin=False)

    def _import_missing_render(_name):
        return SimpleNamespace()

    monkeypatch.setattr(runtime_mod.importlib, "import_module", _import_missing_render)
    with pytest.raises(RuntimeError, match="module_render_not_found"):
        await subject.invoke(
            operation="render",
            payload={"page_module": "page.mod", "current_path": "/page", "session": {}},
        )

    async def _render_async(_params, _session):
        b = runtime_mod.Builder()
        return b

    _render_async._template_name = "empty"

    def _import_async_render(_name):
        return SimpleNamespace(render=_render_async)

    monkeypatch.setattr(runtime_mod.importlib, "import_module", _import_async_render)
    snap = await subject.invoke(
        operation="render",
        payload={"page_module": "page.mod", "current_path": "/page", "session": {}},
    )
    assert snap["template"] == "empty"

    ctx = SimpleNamespace(module_runtime=None)
    monkeypatch.setattr(runtime_mod, "app_ctx", lambda: ctx)
    rt = runtime_mod.get_module_runtime()
    assert isinstance(rt, runtime_mod.ModuleRuntime)
    assert runtime_mod.get_module_runtime() is rt
