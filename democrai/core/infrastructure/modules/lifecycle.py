from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys

from democrai.core.application.auth.service import validate_module_name
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.app import app_ctx


def _load_module_manifest(path: str) -> dict | None:
    manifest_path = os.path.join(path, "manifest.json")
    if not os.path.exists(manifest_path):
        return None
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def stop_module(module):
    try:
        from democrai.core.infrastructure.modules.runtime import get_module_runtime

        get_module_runtime().stop_module(module.name)
    except Exception:
        pass

    for stop_event in module._stop_events.values():
        stop_event.set()

    for task in module._background_tasks:
        task.cancel()

    module._background_tasks = []
    module._stop_events = {}


def _remove_class_from_sqlalchemy_module_markers(
    marker, class_name: str, mapped_class
) -> None:
    contents = getattr(marker, "contents", None)
    if not isinstance(contents, dict):
        return

    class_marker = contents.get(class_name)
    remove_item = getattr(class_marker, "remove_item", None)
    if callable(remove_item):
        remove_item(mapped_class)

    for child_marker in list(contents.values()):
        if child_marker is class_marker:
            continue
        _remove_class_from_sqlalchemy_module_markers(
            child_marker, class_name, mapped_class
        )


def _cleanup_module_sqlalchemy_registry(core_base, module_prefix: str) -> None:
    class_registry = getattr(getattr(core_base, "registry", None), "_class_registry", None)
    if class_registry is None:
        return

    module_registry = class_registry.get("_sa_module_registry")
    for class_name, mapped_class in list(class_registry.items()):
        mapped_module = str(getattr(mapped_class, "__module__", "") or "")
        if mapped_module == module_prefix or mapped_module.startswith(f"{module_prefix}."):
            _remove_class_from_sqlalchemy_module_markers(
                module_registry, class_name, mapped_class
            )
            try:
                del class_registry[class_name]
            except KeyError:
                pass


def reload_module(module):
    if module.type not in ["python", "extension"]:
        return

    from democrai.sdk.database import module_database_context

    manifest = _load_module_manifest(module.path)
    if manifest is not None and not normalize_bool(manifest.get("enabled"), default=True):
        module.stop()
        module.is_active = False
        module.error_message = f"Module '{module.name}' is disabled in manifest.json"
        app_ctx().logger.info(
            f"[Modules] Skipping reload for disabled module: {module.name}"
        )
        return

    prefix = f"modules.{module.name}" if module.is_builtin else module.name
    app_ctx().logger.debug(
        f"Deep reloading module: {module.name} (prefix: {prefix})"
    )

    importlib.invalidate_caches()
    sys.path_importer_cache.clear()

    try:
        from democrai.core.application.routing.router import Router

        Router.invalidate_module_routes(module.name)
    except Exception:
        app_ctx().logger.debug(
            f"Router cache invalidation skipped for module {module.name}"
        )

    try:
        from democrai.core.application.handler.action_resolution import (
            invalidate_legacy_action_cache,
        )

        invalidate_legacy_action_cache(module.name)
    except Exception:
        app_ctx().logger.debug(
            f"Legacy action cache invalidation skipped for module {module.name}"
        )

    # Ensure sandboxed module workers do not keep stale code across reloads.
    try:
        from democrai.core.infrastructure.modules.runtime import get_module_runtime

        get_module_runtime().stop_module(module.name)
    except Exception:
        app_ctx().logger.debug(
            f"Sandbox runtime stop skipped for module {module.name}"
        )

    for stop_event in dict(module._stop_events).values():
        stop_event.set()
    for task in list(module._background_tasks):
        task.cancel()
    module._background_tasks = []
    module._stop_events = {}

    to_delete = [
        m for m in sys.modules if m == prefix or m.startswith(f"{prefix}.")
    ]
    for m in sorted(to_delete, key=len, reverse=True):
        del sys.modules[m]
    try:
        from democrai.core.infrastructure.storage.data.mixins import Base as CoreBase

        table_prefix = f"p_{module.name}_"
        for table_name, table in list(CoreBase.metadata.tables.items()):
            if str(table_name).startswith(table_prefix):
                CoreBase.metadata.remove(table)
        _cleanup_module_sqlalchemy_registry(CoreBase, prefix)
    except Exception:
        app_ctx().logger.debug(
            f"SQLAlchemy metadata cleanup skipped for module {module.name}"
        )

    module.error_message = None
    module.sidebar_entries = []
    module.sidebar_init_declared = False
    module.actions_module = None
    module.commands_module = None
    module.ui_module = None
    try:
        with module_database_context(module.name):
            module_pkg_module = importlib.import_module(prefix)
            load_sidebar = getattr(module, "_load_sidebar_entries_from_init", None)
            if callable(load_sidebar):
                load_sidebar(module_pkg_module)

            actions_pkg = f"{prefix}.actions"
            try:
                module.actions_module = importlib.import_module(actions_pkg)
            except ImportError as exc:
                missing_name = str(getattr(exc, "name", "") or "").strip()
                if not missing_name or missing_name == actions_pkg:
                    module.actions_module = None
                else:
                    raise RuntimeError(f"(actions) {exc}") from exc
            except Exception as exc:
                raise RuntimeError(f"(actions) {exc}") from exc

            commands_pkg = f"{prefix}.commands"
            try:
                module.commands_module = importlib.import_module(commands_pkg)
            except ImportError as exc:
                missing_name = str(getattr(exc, "name", "") or "").strip()
                if not missing_name or missing_name == commands_pkg:
                    module.commands_module = None
                else:
                    raise RuntimeError(f"(commands) {exc}") from exc
            except Exception as exc:
                raise RuntimeError(f"(commands) {exc}") from exc

            ui_pkg = f"{prefix}.ui"
            try:
                module.ui_module = importlib.import_module(ui_pkg)
            except ImportError as exc:
                missing_name = str(getattr(exc, "name", "") or "").strip()
                if not missing_name or missing_name == ui_pkg:
                    module.ui_module = None
                else:
                    raise RuntimeError(f"(ui) {exc}") from exc
            except Exception as exc:
                raise RuntimeError(f"(ui) {exc}") from exc
    except Exception as e:
        module.is_active = False
        module.error_message = f"Reload failed for module '{module.name}': {e}"
        app_ctx().logger.error(module.error_message)
        return

    module.is_active = True


def configure_trust(
    manager,
    *,
    trust_mode: str = "all",
    allow_user_modules: bool = True,
    trusted_modules=None,
) -> None:
    normalized_mode = str(trust_mode or "all").strip().lower()
    if normalized_mode not in {"all", "trusted_only"}:
        app_ctx().logger.warning(
            f"[Modules] Unknown trust mode {trust_mode!r}; falling back to 'all'"
        )
        normalized_mode = "all"
    manager._trust_mode = normalized_mode
    manager._allow_user_modules = allow_user_modules
    trusted_source = [] if trusted_modules is None else trusted_modules
    manager._trusted_modules = {
        name.strip() for name in trusted_source if name.strip()
    }


def is_trusted(manager, module_name: str, *, is_builtin: bool) -> bool:
    if manager._trust_mode == "all":
        if not is_builtin and not manager._allow_user_modules:
            return False
        return True

    if is_builtin:
        return True
    if not manager._allow_user_modules:
        return False
    return module_name in manager._trusted_modules


def discover_modules(
    manager, modules_dir: str, is_builtin: bool = True, *, load_ui: bool = True
):
    if is_builtin:
        modules_parent = os.path.dirname(os.path.abspath(modules_dir))
        if modules_parent and modules_parent not in sys.path:
            sys.path.insert(0, modules_parent)

    if os.path.exists(modules_dir):
        for entry in os.scandir(modules_dir):
            if entry.is_dir():
                manager._try_register_module(entry.path, is_builtin, load_ui=load_ui)

    if is_builtin:
        from democrai.core.platform.utils.discovery import discover_submodules

        for pkg_name in discover_submodules("modules"):
            module_name = pkg_name.split(".")[-1]
            if module_name not in manager._modules:
                module_path = os.path.join(modules_dir, module_name)
                manager._try_register_module(module_path, is_builtin, load_ui=load_ui)


def try_register_module(
    manager, module_cls, path: str, is_builtin: bool, *, load_ui: bool = True
):
    manifest_path = os.path.join(path, "manifest.json")
    if not os.path.exists(manifest_path):
        return

    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
            module_name = validate_module_name(manifest.get("name"))
            if module_name in manager._modules:
                return
            if not normalize_bool(manifest.get("enabled"), default=True):
                app_ctx().logger.info(
                    f"[Modules] Skipping disabled module: {module_name}"
                )
                return
            if not manager._is_trusted(module_name, is_builtin=is_builtin):
                app_ctx().logger.warning(
                    f"[Modules] Skipping untrusted module: {module_name}"
                )
                return
            manifest["name"] = module_name

            module = module_cls(
                path, manifest, is_builtin=is_builtin, owner_id=manager._owner_id
            )
            module.load_modules(load_ui=load_ui)
            manager._modules[module.name] = module

            type_str = "Built-in" if is_builtin else "User"
            status = "Active" if module.is_active else f"Error: {module.error_message}"
            app_ctx().logger.info(
                f"Registered {type_str} module: {module.name} (v{module.version}) - {status}"
            )
    except Exception as e:
        app_ctx().logger.error(
            f"Failed to parse manifest for {os.path.basename(path)}: {e}"
        )


def enable_runtime():
    return None


async def start_all_modules(manager):
    for module in manager._modules.values():
        await module.start_background_commands()


async def ensure_started(manager):
    if manager._background_started:
        return

    if app_ctx().setup_mode:
        manager._background_started = True
        manager._start_future = None
        return

    async with manager._start_lock:
        if manager._background_started:
            return
        await manager.start_all_modules()
        manager._background_started = True
        manager._start_future = None


def schedule_startup(manager, loop):
    if loop is None or manager._background_started:
        return
    if manager._start_future is not None and not manager._start_future.done():
        return
    manager._start_future = asyncio.run_coroutine_threadsafe(
        manager.ensure_started(), loop
    )


def shutdown(manager):
    manager._background_started = False
    for module in manager._modules.values():
        module.stop()


def reload_all_modules(manager):
    manager._background_started = False
    for module_name, module in list(manager._modules.items()):
        manifest = _load_module_manifest(module.path)
        if manifest is not None and not normalize_bool(manifest.get("enabled"), default=True):
            module.stop()
            module.is_active = False
            module.error_message = f"Module '{module.name}' is disabled in manifest.json"
            del manager._modules[module_name]
            app_ctx().logger.info(
                f"[Modules] Unloaded disabled module: {module.name}"
            )
            continue
        if getattr(module, "type", "python") not in ["python", "extension"]:
            continue
        try:
            module.reload()
        except Exception as e:
            module.is_active = False
            module.error_message = f"Reload failed for module '{module.name}': {e}"
            app_ctx().logger.error(module.error_message)
