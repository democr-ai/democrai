from __future__ import annotations

import ast
import importlib
import inspect
import json
import os
import sys
from dataclasses import replace
from typing import Any

from democrai.core.application.auth.service import sync_module_authorization
from democrai.core.application.services.translation import get_translation_service
from democrai.core.infrastructure.modules.compat import resolve_module_resource
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.app import app_ctx


def _load_module_rbac_manifest(module) -> dict[str, Any] | None:
    rbac_path = os.path.join(module.path, "rbac.json")
    if not os.path.exists(rbac_path):
        return None

    try:
        with open(rbac_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError("rbac.json must contain a JSON object")
        return payload
    except Exception as e:
        app_ctx().logger.error(
            f"Invalid rbac.json for module {module.name}: {e}"
        )
        raise


def _collect_forbidden_core_imports(
    module_path: str,
    *,
    fail_closed_dynamic_imports: bool = False,
) -> list[str]:
    def _literal_string(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return str(node.value)
        return None

    def _is_import_call(node: ast.Call, importlib_aliases: set[str], import_module_aliases: set[str]) -> bool:
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in {"__import__"} | import_module_aliases
        if isinstance(func, ast.Attribute):
            if func.attr == "__import__" and isinstance(func.value, ast.Name) and func.value.id == "builtins":
                return True
            if (
                func.attr == "import_module"
                and isinstance(func.value, ast.Name)
                and func.value.id in importlib_aliases
            ):
                return True
        return False

    def _forbidden_import_call(
        node: ast.Call,
        importlib_aliases: set[str],
        import_module_aliases: set[str],
        resolved_target: str | None,
        is_direct_literal: bool,
    ) -> str | None:
        if not _is_import_call(node, importlib_aliases, import_module_aliases):
            return None
        if not node.args:
            return "dynamic_import_call(no-args)"
        if resolved_target:
            target = resolved_target.strip()
            if target == "democrai.core" or target.startswith("democrai.core."):
                func = node.func
                if isinstance(func, ast.Name):
                    return f"{func.id}({target})"
                if isinstance(func, ast.Attribute):
                    if isinstance(func.value, ast.Name):
                        return f"{func.value.id}.{func.attr}({target})"
                    return f"{func.attr}({target})"
                return f"import_call({target})"
            if fail_closed_dynamic_imports and not is_direct_literal:
                func = node.func
                if isinstance(func, ast.Name):
                    return f"dynamic_import_call({func.id})"
                if isinstance(func, ast.Attribute):
                    if isinstance(func.value, ast.Name):
                        return f"dynamic_import_call({func.value.id}.{func.attr})"
                    return f"dynamic_import_call({func.attr})"
                return "dynamic_import_call"
            return None

        if fail_closed_dynamic_imports and not is_direct_literal:
            func = node.func
            if isinstance(func, ast.Name):
                return f"dynamic_import_call({func.id})"
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name):
                    return f"dynamic_import_call({func.value.id}.{func.attr})"
                return f"dynamic_import_call({func.attr})"
            return "dynamic_import_call"
        return None

    violations: list[str] = []
    for root, _dirs, files in os.walk(module_path):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            source_path = os.path.join(root, filename)
            try:
                with open(source_path, "r", encoding="utf-8") as handle:
                    tree = ast.parse(handle.read(), filename=source_path)
            except Exception:
                continue
            rel_path = os.path.relpath(source_path, module_path).replace(os.sep, "/")
            importlib_aliases: set[str] = {"importlib"}
            import_module_aliases: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.strip() == "importlib":
                            importlib_aliases.add(str(alias.asname or "importlib").strip())
                elif isinstance(node, ast.ImportFrom):
                    if str(node.module or "").strip() == "importlib":
                        for alias in node.names:
                            if alias.name.strip() == "import_module":
                                import_module_aliases.add(str(alias.asname or "import_module").strip())

            class _BoundaryVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.scope_stack: list[dict[str, str | None]] = [{}]

                def _push_scope(self) -> None:
                    self.scope_stack.append({})

                def _pop_scope(self) -> None:
                    self.scope_stack.pop()

                def _bind_name(self, name: str, value: str | None) -> None:
                    if self.scope_stack:
                        self.scope_stack[-1][name] = value

                def _resolve_name(self, name: str) -> str | None:
                    for scope in reversed(self.scope_stack):
                        if name in scope:
                            return scope[name]
                    return None

                def _resolve_expr(self, node: ast.AST | None) -> str | None:
                    if node is None:
                        return None
                    literal = _literal_string(node)
                    if literal is not None:
                        return literal
                    if isinstance(node, ast.Name):
                        return self._resolve_name(node.id)
                    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                        left = self._resolve_expr(node.left)
                        right = self._resolve_expr(node.right)
                        if left is None or right is None:
                            return None
                        return f"{left}{right}"
                    if isinstance(node, ast.JoinedStr):
                        parts: list[str] = []
                        for value in node.values:
                            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                                parts.append(str(value.value))
                                continue
                            if isinstance(value, ast.FormattedValue):
                                formatted = self._resolve_expr(value.value)
                                if formatted is None:
                                    return None
                                parts.append(str(formatted))
                                continue
                            return None
                        return "".join(parts)
                    return None

                def _mark_targets_unknown(self, target: ast.AST) -> None:
                    if isinstance(target, ast.Name):
                        self._bind_name(target.id, None)
                        return
                    if isinstance(target, (ast.Tuple, ast.List)):
                        for item in target.elts:
                            self._mark_targets_unknown(item)

                def _bind_assign_target(self, target: ast.AST, value: str | None) -> None:
                    if isinstance(target, ast.Name):
                        self._bind_name(target.id, value)
                        return
                    if isinstance(target, (ast.Tuple, ast.List)):
                        for item in target.elts:
                            self._bind_assign_target(item, value)

                def visit_Import(self, node: ast.Import) -> None:
                    for alias in node.names:
                        imported = alias.name.strip()
                        if imported == "democrai.core" or imported.startswith("democrai.core."):
                            violations.append(
                                f"{rel_path}:{getattr(node, 'lineno', 0)}:{imported}"
                            )
                    self.generic_visit(node)

                def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                    imported_from = str(node.module or "").strip()
                    if imported_from == "democrai.core" or imported_from.startswith("democrai.core."):
                        violations.append(
                            f"{rel_path}:{getattr(node, 'lineno', 0)}:from {imported_from}"
                        )
                    self.generic_visit(node)

                def visit_Assign(self, node: ast.Assign) -> None:
                    value = self._resolve_expr(node.value)
                    for target in node.targets:
                        self._bind_assign_target(target, value)
                    self.generic_visit(node)

                def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
                    value = self._resolve_expr(node.value)
                    self._bind_assign_target(node.target, value)
                    self.generic_visit(node)

                def visit_AugAssign(self, node: ast.AugAssign) -> None:
                    if isinstance(node.op, ast.Add) and isinstance(node.target, ast.Name):
                        current = self._resolve_name(node.target.id)
                        update = self._resolve_expr(node.value)
                        if current is not None and update is not None:
                            self._bind_name(node.target.id, f"{current}{update}")
                        else:
                            self._bind_name(node.target.id, None)
                    else:
                        self._mark_targets_unknown(node.target)
                    self.generic_visit(node)

                def visit_For(self, node: ast.For) -> None:
                    self._mark_targets_unknown(node.target)
                    self.generic_visit(node)

                def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
                    self._mark_targets_unknown(node.target)
                    self.generic_visit(node)

                def visit_With(self, node: ast.With) -> None:
                    for item in node.items:
                        if item.optional_vars is not None:
                            self._mark_targets_unknown(item.optional_vars)
                    self.generic_visit(node)

                def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
                    for item in node.items:
                        if item.optional_vars is not None:
                            self._mark_targets_unknown(item.optional_vars)
                    self.generic_visit(node)

                def visit_Call(self, node: ast.Call) -> None:
                    direct_literal = bool(node.args and _literal_string(node.args[0]) is not None)
                    resolved_target = self._resolve_expr(node.args[0]) if node.args else None
                    forbidden_call = _forbidden_import_call(
                        node,
                        importlib_aliases,
                        import_module_aliases,
                        resolved_target=resolved_target,
                        is_direct_literal=direct_literal,
                    )
                    if forbidden_call:
                        violations.append(
                            f"{rel_path}:{getattr(node, 'lineno', 0)}:{forbidden_call}"
                        )
                    self.generic_visit(node)

                def _visit_scoped(self, node: ast.AST) -> None:
                    self._push_scope()
                    try:
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            for arg in list(node.args.args) + list(node.args.kwonlyargs):
                                self._bind_name(arg.arg, None)
                            if node.args.vararg:
                                self._bind_name(node.args.vararg.arg, None)
                            if node.args.kwarg:
                                self._bind_name(node.args.kwarg.arg, None)
                        self.generic_visit(node)
                    finally:
                        self._pop_scope()

                def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                    self._visit_scoped(node)

                def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                    self._visit_scoped(node)

                def visit_Lambda(self, node: ast.Lambda) -> None:
                    self._visit_scoped(node)

                def visit_ClassDef(self, node: ast.ClassDef) -> None:
                    self._visit_scoped(node)

            _BoundaryVisitor().visit(tree)
    return violations


def _sdk_boundary_fail_closed_dynamic_imports() -> bool:
    cfg = getattr(app_ctx(), "config", None)
    if cfg is None:
        return False
    raw = cfg.get("modules.sdk_boundary.fail_closed_dynamic_imports", False)
    return normalize_bool(raw)


def _enforce_sdk_boundary(module) -> None:
    # Historical bypass kept for reference. Built-in modules used to be allowed
    # to import core internals, but they now follow the same SDK boundary as
    # user modules.
    # if bool(getattr(module, "is_builtin", False)):
    #     return
    violations = _collect_forbidden_core_imports(
        str(module.path),
        fail_closed_dynamic_imports=_sdk_boundary_fail_closed_dynamic_imports(),
    )
    if violations:
        preview = ", ".join(violations[:5])
        raise RuntimeError(
            "module_sdk_boundary_violation:"
            f" direct core imports are not allowed in module '{module.name}' ({preview})"
        )


def load_modules(module, *, load_ui: bool = True):
    if not module.validate_compatibility():
        app_ctx().logger.warning(f"Skipping module {module.name}: {module.error_message}")
        return

    added_paths: list[str] = []
    try:
        locales_path = os.path.join(module.path, "locales")
        if os.path.exists(locales_path):
            get_translation_service().load_module_locales(module.name, locales_path)

        deps_path = os.path.join(module.path, "deps")
        if os.path.exists(deps_path):
            # SB-4: Warn if deps/ contains C extensions — they bypass Python-level restrictions.
            for fname in os.listdir(deps_path):
                if fname.endswith(".so") or fname.endswith(".pyd"):
                    app_ctx().logger.warning(
                        f"[Sandbox] Module {module.name!r} uses C extension {fname!r} "
                        f"in deps/ — C extensions bypass Python-level checks."
                    )
            if deps_path not in sys.path:
                sys.path.insert(0, deps_path)
                added_paths.append(deps_path)

        if module.is_builtin:
            module_rel_path = f"modules.{module.name}"
        else:
            if module.path not in sys.path:
                parent_path = os.path.dirname(module.path)
                if parent_path not in sys.path:
                    sys.path.append(parent_path)
                    added_paths.append(parent_path)
            module_rel_path = module.name

        if module.type in {"python", "extension"}:
            from democrai.sdk.database import module_database_context

            _enforce_sdk_boundary(module)
            with module_database_context(module.name):
                module._load_python_modules(module_rel_path, load_ui=load_ui)

        module_migrations_dir = os.path.join(module.path, "migrations")
        if os.path.exists(module_migrations_dir):
            from democrai.core.infrastructure.storage.data.migrations_handler import run_module_migration

            app_ctx().logger.info(f"Running migrations for module: {module.name}...")
            run_module_migration(module.name, module.path)

        if not getattr(app_ctx(), "setup_mode", False):
            sync_module_authorization(
                module.name,
                _load_module_rbac_manifest(module),
            )

        module.is_active = True
    except Exception as e:
        for path in added_paths:
            try:
                sys.path.remove(path)
            except ValueError:
                pass
        module.error_message = str(e)
        app_ctx().logger.error(f"Error loading modules for {module.name}: {e}")


def load_python_modules(module, module_rel_path: str, *, load_ui: bool = True):
    from democrai.core.platform.utils.discovery import discover_submodules
    from democrai.sdk.client import SDK as ModuleSDK, current_sdk as _current_module_sdk

    module_sdk = ModuleSDK(module.path, module.name)
    token = _current_module_sdk.set(module_sdk)

    try:
        module_pkg_module = importlib.import_module(module_rel_path)
        module._load_sidebar_entries_from_init(module_pkg_module)

        actions_pkg = f"{module_rel_path}.actions"
        for mod_name in discover_submodules(actions_pkg):
            try:
                importlib.import_module(mod_name)
            except ImportError as exc:
                logger = app_ctx().logger
                message = (
                    f"[Modules] Action discovery import failed module={module.name} "
                    f"import={mod_name} error={exc}"
                )
                if hasattr(logger, "exception") and callable(
                    getattr(logger, "exception", None)
                ):
                    logger.exception(message)
                else:
                    logger.error(message)
                continue

        try:
            module.actions_module = importlib.import_module(actions_pkg)
        except ImportError as exc:
            missing_name = str(getattr(exc, "name", "") or "").strip()
            if not missing_name or missing_name == actions_pkg:
                module.actions_module = None
            else:
                logger = app_ctx().logger
                message = (
                    f"[Modules] Actions package import failed module={module.name} "
                    f"import={actions_pkg} error={exc}"
                )
                if hasattr(logger, "exception") and callable(
                    getattr(logger, "exception", None)
                ):
                    logger.exception(message)
                else:
                    logger.error(message)
                raise

        commands_pkg = f"{module_rel_path}.commands"
        for mod_name in discover_submodules(commands_pkg):
            try:
                importlib.import_module(mod_name)
            except ImportError:
                pass

        try:
            module.commands_module = importlib.import_module(commands_pkg)
        except ImportError as exc:
            missing_name = str(getattr(exc, "name", "") or "").strip()
            if not missing_name or missing_name == commands_pkg:
                module.commands_module = None
            else:
                raise

        for asset_kind in ("tools", "agents"):
            asset_pkg = f"{module_rel_path}.{asset_kind}"
            for mod_name in discover_submodules(asset_pkg):
                try:
                    importlib.import_module(mod_name)
                except ImportError as exc:
                    logger = app_ctx().logger
                    message = (
                        f"[Modules] {asset_kind.title()} discovery import failed "
                        f"module={module.name} import={mod_name} error={exc}"
                    )
                    if hasattr(logger, "exception") and callable(
                        getattr(logger, "exception", None)
                    ):
                        logger.exception(message)
                    else:
                        logger.error(message)
                    continue

        if load_ui:
            try:
                module.ui_module = importlib.import_module(f"{module_rel_path}.ui")
            except ImportError as exc:
                ui_pkg = f"{module_rel_path}.ui"
                missing_name = str(getattr(exc, "name", "") or "").strip()
                if not missing_name or missing_name == ui_pkg:
                    module.ui_module = None
                else:
                    raise

        _register_module_skills(module)
    finally:
        _current_module_sdk.reset(token)


def _register_module_skills(module) -> None:
    skills_dir = os.path.join(module.path, "skills")
    if not os.path.exists(skills_dir) or not os.path.isdir(skills_dir):
        return

    from democrai.core.platform.agents.registry import skill_registry
    from democrai.core.platform.agents.skills import SkillLoader

    for skill in SkillLoader(
        skill_dirs=[skills_dir],
        include_default_dirs=False,
    ).discover():
        skill_registry.register(_qualify_module_skill(module, skill))


def _qualify_module_skill(module, skill):
    from democrai.core.application.access_policy.models import AccessSubject

    module_name = module.name.strip()
    raw_name = skill.metadata.name.strip()
    qualified_name = (
        raw_name
        if raw_name.startswith(f"{module_name}.")
        else f"{module_name}.{raw_name}"
    )
    metadata = replace(
        skill.metadata,
        name=qualified_name,
        module_name=module_name,
        access=[
            replace(
                rule,
                subject=AccessSubject.create("skill", qualified_name),
            )
            for rule in skill.metadata.access
        ],
    )
    return replace(skill, metadata=metadata)


def load_sidebar_entries_from_init(module, module_module) -> None:
    module.sidebar_entries = []
    module.sidebar_init_declared = False

    init_func = getattr(module_module, "init", None)
    if not callable(init_func):
        return

    module.sidebar_init_declared = True
    payload: Any = None
    init_context = {
        "module_name": module.name,
        "module_path": module.path,
        "manifest": dict(module._manifest),
    }
    try:
        try:
            signature = inspect.signature(init_func)
            if len(signature.parameters) == 0:
                payload = init_func()
            else:
                payload = init_func(init_context)
        except (TypeError, ValueError):
            payload = init_func(init_context)
    except Exception as exc:
        app_ctx().logger.warning(f"Module {module.name} init() failed for sidebar entries: {exc}")
        return

    raw_entries: list[Any] = []
    if isinstance(payload, dict):
        entries = payload.get("sidebar_entries")
        if isinstance(entries, list):
            raw_entries = entries
    elif isinstance(payload, list):
        raw_entries = payload

    normalized: list[dict[str, Any]] = []
    for index, raw_entry in enumerate(raw_entries):
        entry = module._normalize_sidebar_entry(raw_entry, index=index)
        if entry is not None:
            normalized.append(entry)
    module.sidebar_entries = normalized


def normalize_sidebar_entry(module, raw_entry: Any, *, index: int):
    if not isinstance(raw_entry, dict):
        return None

    entry = dict(raw_entry)
    item_id = entry.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        item_id = f"{module.name}_{index}"

    label = entry.get("label", module.label)
    if not isinstance(label, str):
        label = module.label

    icon = entry.get("icon")
    if isinstance(icon, str):
        icon = resolve_module_resource(module.path, icon)
    elif icon is not None:
        icon = None

    position = entry.get("position", "top")
    if position not in {"top", "bottom"}:
        position = "top"

    action = entry.get("action")
    if not isinstance(action, dict) or not isinstance(action.get("name"), str):
        return None
    action_context = action.get("context")
    if not isinstance(action_context, dict):
        action_context = {}
    normalized_action = {"name": action["name"], "context": action_context}

    visible_for = entry.get("visible_for", "all")
    if visible_for not in {"all", "guest", "authenticated"}:
        visible_for = "all"

    normalized: dict[str, Any] = {
        "id": item_id,
        "label": label,
        "icon": icon,
        "position": position,
        "action": normalized_action,
        "visible_for": visible_for,
    }
    raw_priority = entry.get("priority", getattr(module, "priority", 0))
    try:
        normalized["priority"] = int(raw_priority)
    except (TypeError, ValueError):
        normalized["priority"] = int(getattr(module, "priority", 0))

    active_path = entry.get("active_path")
    if isinstance(active_path, str) and active_path.strip():
        normalized["active_path"] = active_path.strip()

    for key in ("authenticated_label", "authenticated_icon", "guest_label", "guest_icon"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()

    for key in ("authenticated_action", "guest_action"):
        value = entry.get(key)
        if isinstance(value, dict) and isinstance(value.get("name"), str) and value["name"].strip():
            action_ctx = value.get("context")
            if not isinstance(action_ctx, dict):
                action_ctx = {}
            normalized[key] = {"name": value["name"], "context": action_ctx}

    return normalized
