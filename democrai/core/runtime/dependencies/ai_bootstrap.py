from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Optional


def ensure_engine_env_base() -> Path:
    """
    Ensure the shared local root used by per-engine environments exists.

    This only prepares the base cache directory at application startup.
    It does not install or synchronize any engine-specific dependencies.
    """
    from democrai.core.runtime.foundation.paths import data_dir

    target = data_dir() / "engine_env_cache"
    target.mkdir(parents=True, exist_ok=True)
    return target


def bootstrap_ai() -> bool:
    """
    Bootstrap only the engine-scoped dependency environment.

    There is no longer a global AI runtime or shared dependency environment to prepare at process
    startup. Heavy dependencies are installed and loaded per-engine.
    """
    from democrai.core.runtime.dependencies.engine_env import (
        activate_local_engine_env,
        bootstrap_engine_env,
        has_engine_env_context,
    )

    if not has_engine_env_context():
        return False
    if os.environ.get("DEMOCRAI_ENGINE_WORKER") == "1":
        activate_local_engine_env()
        return True
    bootstrap_engine_env()
    return True


def ensure_import(module_name: str, *, dependency_key: Optional[str] = None):
    """
    Ensure a dependency is importable, installing it only through the current
    engine/local dependency flow.
    """
    bootstrap_ai()
    try:
        return importlib.import_module(module_name)
    except ImportError as first_err:
        from democrai.core.application.ai.engine.manifests import load_engine_class
        from democrai.core.runtime.dependencies.engine_env import get_current_engine_id
        try:
            engine_id = get_current_engine_id()
            if not engine_id:
                raise RuntimeError("engine_env_context_missing")

            engine_cls = load_engine_class(engine_id)
            if engine_cls is None:
                raise RuntimeError(f"engine_runtime_class_not_found:{engine_id}")

            ready_result = engine_cls.check_ready()
            if not isinstance(ready_result, dict):
                raise RuntimeError(f"engine_ready_result_invalid:{engine_id}")
            if not bool(ready_result.get("ready")):
                engine_cls.install(force=False)
            bootstrap_ai()
            return importlib.import_module(module_name)
        except Exception as install_err:
            from democrai.core.runtime.foundation.exceptions import (
                DependencyMissingError,
                SystemDependencyRequiredError,
            )

            dep = dependency_key if dependency_key is not None else module_name
            if isinstance(install_err, SystemDependencyRequiredError):
                raise DependencyMissingError(
                    f"Missing AI dependency: {dep} ({install_err})",
                    dependency=dep,
                    dependency_key=dep,
                    install_scope="system",
                    system_dependency_key=install_err.dependency_key,
                ) from first_err
            raise DependencyMissingError(
                f"Missing AI dependency: {dep} ({install_err})",
                dependency=dep,
                dependency_key=dep,
                install_scope="python",
            ) from first_err
