from __future__ import annotations

import sys
from types import ModuleType

import democrai.core.runtime.dependencies.engine_env as engine_env_mod
import pytest


@pytest.mark.posix_only
def test_isolate_engine_imports_removes_global_module_present_in_local_env(monkeypatch, tmp_path):
    monkeypatch.setattr(engine_env_mod, "_ENGINE_LOCAL_PATH_OVERRIDES", {})

    local_env = tmp_path / "engine_env_cache" / "onnx"
    local_site = local_env / ".venv" / "lib" / "python3.12" / "site-packages"
    local_cache = local_env / "cache"
    local_config = local_env / "config"
    local_tmp = local_env / "tmp"
    (local_site / "numpy").mkdir(parents=True)
    (local_site / "numpy" / "__init__.py").write_text("", encoding="utf-8")
    local_cache.mkdir()
    local_config.mkdir()
    local_tmp.mkdir()

    global_numpy_path = tmp_path / "venv" / "site-packages" / "numpy" / "__init__.py"
    global_numpy_path.parent.mkdir(parents=True)
    global_numpy_path.write_text("", encoding="utf-8")
    global_other_path = tmp_path / "venv" / "site-packages" / "otherpkg" / "__init__.py"
    global_other_path.parent.mkdir(parents=True)
    global_other_path.write_text("", encoding="utf-8")

    numpy_mod = ModuleType("numpy")
    numpy_mod.__file__ = str(global_numpy_path)
    numpy_core_mod = ModuleType("numpy.core")
    numpy_core_mod.__file__ = str(global_numpy_path.parent / "core" / "__init__.py")
    other_mod = ModuleType("otherpkg")
    other_mod.__file__ = str(global_other_path)

    monkeypatch.setitem(sys.modules, "numpy", numpy_mod)
    monkeypatch.setitem(sys.modules, "numpy.core", numpy_core_mod)
    monkeypatch.setitem(sys.modules, "otherpkg", other_mod)
    monkeypatch.setattr(
        sys,
        "path",
        [str(local_site), str(global_numpy_path.parent.parent)],
    )
    engine_env_mod.set_engine_local_path_overrides(
        "onnx",
        env_path=str(local_env),
        cache_path=str(local_cache),
        config_path=str(local_config),
        tmp_path=str(local_tmp),
    )

    engine_env_mod.isolate_engine_imports("onnx")

    assert "numpy" not in sys.modules
    assert "numpy.core" not in sys.modules
    assert sys.modules["otherpkg"] is other_mod
    assert sys.path[0] == str(local_site)
