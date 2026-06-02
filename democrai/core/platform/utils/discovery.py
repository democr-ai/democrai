import importlib
import pkgutil
import inspect
import types
import os
from typing import List
from democrai.core.runtime.foundation.app import app_ctx


def _log_import_failure(message: str) -> None:
    logger = app_ctx().logger
    if hasattr(logger, "exception") and callable(getattr(logger, "exception", None)):
        logger.exception(message)
        return
    logger.error(message)


def discover_submodules(package_name: str, recursive: bool = False) -> List[str]:
    """
    Discover package submodules in a robust way.
    Works in both development and compiled bundles (Nuitka).

    Args:
        package_name: Full package name (e.g. 'democrai.core.application.handler.actions')
        recursive: If True, run recursive discovery (walk_packages)

    Returns:
        List of fully-qualified discovered module names.
    """
    modules = set()
    
    try:
        pkg = importlib.import_module(package_name)
    except ImportError as exc:
        # Optional packages may be legitimately absent; still surface details
        # when the import failed for reasons other than "package not found".
        exc_name = getattr(exc, "name", None)
        missing_name = exc_name.strip() if isinstance(exc_name, str) else ""
        if not missing_name or missing_name == package_name:
            app_ctx().logger.warning(
                f"[Discovery] Unable to load package: {package_name} error={exc}"
            )
        else:
            _log_import_failure(
                f"[Discovery] Unable to load package: {package_name} error={exc}"
            )
        return []

    # 1. Explicit import method (Hybrid/Nuitka)
    # If the package imports its submodules in __init__.py, inspect picks them up.
    for name, obj in inspect.getmembers(pkg):
        if isinstance(obj, types.ModuleType) and obj.__name__.startswith(package_name):
            if obj.__name__ != package_name:
                modules.add(obj.__name__)

    # 2. pkgutil method (Development / Standard)
    # pkgutil.walk_packages or iter_modules works well when .py files are on disk.
    try:
        if hasattr(pkg, "__path__"):
             pkg_path = pkg.__path__
             if recursive:
                 for info in pkgutil.walk_packages(pkg_path, package_name + "."):
                     modules.add(info.name)
             else:
                 for info in pkgutil.iter_modules(pkg_path, package_name + "."):
                     modules.add(info.name)
    except Exception as e:
        # In compiled mode, __path__ can be unusual and pkgutil can fail.
        app_ctx().logger.debug(f"[Discovery] pkgutil failed for {package_name}: {e}")

    return sorted(list(modules))

def discover_module_ui_modules(module_name: str, module_path: str, is_builtin: bool = True) -> List[str]:
    """
    Discover UI modules for a module.
    Handles differences between compiled and filesystem-based modules.
    """
    ui_pkg = f"modules.{module_name}.ui" if is_builtin else f"{module_name}.ui"
    
    # Try package discovery first (compiled mode).
    # Then ALWAYS merge filesystem results for nested modules missed by pkgutil.
    found = set(discover_submodules(ui_pkg, recursive=True))

    ui_fs_path = os.path.join(module_path, "ui")
    if os.path.exists(ui_fs_path):
        for root, _dirs, files in os.walk(ui_fs_path):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    rel_dir = os.path.relpath(root, ui_fs_path)
                    mod_part = file[:-3]
                    if rel_dir == ".":
                        full_name = f"{ui_pkg}.{mod_part}"
                    else:
                        full_name = f"{ui_pkg}.{rel_dir.replace(os.sep, '.')}.{mod_part}"
                    found.add(full_name)

    return sorted(list(found))
