from __future__ import annotations

import importlib
import os
import sys
import traceback
from contextlib import nullcontext
from pathlib import Path

from democrai.core.application.auth.action import check_access, get_required_permissions
from democrai.core.application.auth.module_access import is_module_locked_for_session
from democrai.core.application.auth.roles import is_super_role
from democrai.core.application.home import resolve_home_page_path
from democrai.core.platform.utils.discovery import discover_module_ui_modules
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx
from democrai.core.runtime.foundation.exceptions import AccessDeniedError
from democrai.core.runtime.foundation.paths import get_runtime_module_dirs
from democrai.core.runtime.observability.profiling import current_request_profiler


_RESERVED_ROUTE_PARAM_KEYS = {"stream_id", "_stream_id"}


def _span(profiler, name: str):
    """Return a profiler span context manager, or a no-op if profiler is None."""
    return profiler.span(name) if profiler is not None else nullcontext()


def _ensure_module_import_paths(ctx) -> None:
    candidates: list[str] = []
    for root in get_runtime_module_dirs():
        root_path = Path(root)
        candidates.append(str(root_path))
        candidates.append(str(root_path.parent))
    for module in ctx.modules.get_all_modules():
        module_path = Path(str(module.path or ""))
        candidates.append(str(module_path.parent))
        candidates.append(str(module_path.parent.parent))

    for candidate in candidates:
        if candidate and candidate not in sys.path:
            sys.path.insert(0, candidate)


def warmup():
    from democrai.core.application.routing.router import ROUTER, Router

    ctx = app_ctx()
    ctx.logger.info("[Router] Starting warmup (eager loading)...")

    failures = []
    patterns = []

    _ensure_module_import_paths(ctx)

    for module in ctx.modules.get_all_modules():
        full_modules = discover_module_ui_modules(module.name, module.path, module.is_builtin)
        for module_name in full_modules:
            try:
                importlib.import_module(module_name)
            except Exception as exc:
                failures.append({"app": module.name, "ui_module": module_name, "error": str(exc)})

        patterns.extend(Router._discover_module_patterns(module))

    ROUTER.set_patterns(patterns)

    if failures:
        ctx.logger.warning(f"[Router] Warmup completed with {len(failures)} errors.")
    else:
        ctx.logger.info("[Router] Warmup completed successfully.")

    return failures


def is_public_path(path: str) -> bool:
    from democrai.core.application.routing.router import ROUTER, Router

    _ensure_module_import_paths(app_ctx())

    app_name, page_path, _ = Router.parse_path(path)
    module = app_ctx().modules.get_module(app_name)
    if not module:
        return False

    Router._ensure_module_routes(module)
    match_result = ROUTER.match(app_name + "/ui/" + page_path)
    if not match_result:
        return False

    full_module_path = f"modules.{match_result.pattern.replace('/', '.')}"
    try:
        page_module = importlib.import_module(full_module_path)
    except Exception:
        return False

    render = getattr(page_module, "render", None)
    return bool(render is not None and getattr(render, "_is_public", False))


async def resolve(path: str, session: dict, extra_params=None):
    from democrai.core.application.routing.router import ROUTER, Router, printErrorResponse

    _ensure_module_import_paths(app_ctx())

    profiler = current_request_profiler()
    with _span(profiler, "router.parse_path"):
        app_name, page_path, params = Router.parse_path(path)

    for key in _RESERVED_ROUTE_PARAM_KEYS:
        params.pop(key, None)
    if extra_params:
        params.update(
            {
                key: value
                for key, value in extra_params.items()
                if key not in _RESERVED_ROUTE_PARAM_KEYS
            }
        )

    try:
        current_request = req_ctx()
    except Exception:
        current_request = None
    if current_request is not None:
        if current_request.stream_id:
            params["stream_id"] = current_request.stream_id

    logger = app_ctx().logger
    debug = getattr(logger, "debug", None)
    if callable(debug):
        debug(
            f"[Router] Resolving: app={app_name}, page={page_path}, params={params}",
            "router",
        )


    with _span(profiler, "router.module_lookup"):
        module = app_ctx().modules.get_module(app_name)
    if not module:
        app_ctx().logger.warning(f"[Router] Module '{app_name}' not found")
        return printErrorResponse(404, f"App '{app_name}' not found")

    with _span(profiler, "router.ensure_routes"):
        Router._ensure_module_routes(module)
    with _span(profiler, "router.match"):
        match_result = ROUTER.match(app_name + "/ui/" + page_path)

    if not match_result:
        app_ctx().logger.warning(f"[Router] No match found for '{app_name}/ui/{page_path}'")
        return printErrorResponse(404, f"Path '{app_name}/ui/{page_path}' not found")

    params["route_params"] = match_result.params
    page_path = match_result.pattern
    module_name = page_path.replace("/", ".")
    full_module_path = f"modules.{module_name}"

    try:
        with _span(profiler, "router.import_module"):
            page_module = importlib.import_module(full_module_path)
    except Exception as exc:
        app_ctx().logger.error(f"[Router] RESOLVE FAILURE: Failed to load {full_module_path}: {exc}")
        return printErrorResponse(404, f"ROUTE {full_module_path} NOT FOUND")

    try:
        if hasattr(page_module, "render"):
            user = session.get("user") or {}
            username = user.get("username") or user.get("name") or "guest"
            is_authenticated = bool(user) and username != "guest"
            is_public = getattr(page_module.render, "_is_public", False)
            is_only_guest = getattr(page_module.render, "_only_guest", False)

            if is_only_guest and is_authenticated:
                home_path = resolve_home_page_path()
                session["current_path"] = home_path
                app_ctx().logger.info(
                    f"[Router] Redirecting authenticated user away from guest-only route '{full_module_path}' to {home_path}"
                )
                return await Router.resolve(home_path, session)

            if not is_public and not is_authenticated:
                app_ctx().logger.warning(
                    f"[Router] Access Denied: '{full_module_path}' requires authentication."
                )
                raise AccessDeniedError("Authentication required")

            with _span(profiler, "router.auth.required_permissions"):
                required_perms = get_required_permissions(page_module.render)
                if not required_perms:
                    required_perms = getattr(page_module, "REQUIRED_PERMISSIONS", [])
            role = user.get("role", "Guest") if user else "Guest"

            with _span(profiler, "router.auth.module_lock"):
                module_locked = (
                    not is_super_role(role)
                    and is_module_locked_for_session(
                        app_name,
                        session,
                    )
                )
            if module_locked:
                app_ctx().logger.warning(
                    f"[Router] Access Denied to {full_module_path}. Module is locked."
                )
                return printErrorResponse(403, "MODULE_LOCKED")

            with _span(profiler, "router.auth.permissions"):
                if is_super_role(role):
                    pass
                elif required_perms:
                    if not is_authenticated:
                        app_ctx().logger.warning(
                            f"[Router] Access Denied to {full_module_path}. Authentication required for permissions: {required_perms}"
                        )
                        raise AccessDeniedError("Authentication required")

                    from democrai.core.application.auth.service import get_user_permissions

                    user_id = user.get("id")
                    if user_id is None:
                        raise AccessDeniedError("Authentication required")
                    user_perms = get_user_permissions(user_id)
                    if not check_access(required_perms, user_perms):
                        app_ctx().logger.warning(
                            f"[Router] Access Denied to {full_module_path}. Required: {required_perms}"
                        )
                        return printErrorResponse(403, "UNAUTHORIZED")

            from democrai.core.infrastructure.modules.runtime import (
                build_module_reuse_key,
                get_module_runtime,
            )
            from democrai.sdk.client import SDK as ModuleSDK, current_sdk as _current_module_sdk

            request_id = current_request.request_id if current_request is not None else ""
            in_module_worker = request_id == f"runtime:{module.name}"

            with _span(profiler, "router.sdk_init"):
                module_sdk = ModuleSDK(module.path, module.name, current_path=path, session=session)
                token = _current_module_sdk.set(module_sdk)
            try:
                with _span(profiler, "router.page_render"):
                    if in_module_worker:
                        builder = page_module.render(dict(params or {}), session)
                        if hasattr(builder, "__await__"):
                            builder = await builder
                        if not hasattr(builder, "get_roots") or not hasattr(builder, "build_surface_update_payload"):
                            raise RuntimeError(f"module_render_invalid_builder:{full_module_path}")
                        if hasattr(page_module.render, "_template_name"):
                            builder.set_template(page_module.render._template_name)
                        return builder

                    builder = await get_module_runtime().invoke(
                        module=module,
                        operation="render",
                        payload={
                            "page_module": full_module_path,
                            "current_path": path,
                            "params": dict(params),
                            "session": dict(session),
                        },
                        session=dict(session),
                        metadata={"mode": "module_render", "page_module": full_module_path},
                        persistent=True,
                        reuse_key=build_module_reuse_key(module.name, session),
                    )
                return builder
            finally:
                _current_module_sdk.reset(token)

        app_ctx().logger.warning(f"[Router] Module {full_module_path} has no 'render' function")
        return printErrorResponse(404, f"Page '{page_path}' in module '{app_name}' has no render function")
    except ImportError as exc:
        error_msg = f"Module '{full_module_path}' not found (Error: {exc})"
        app_ctx().logger.error(f"[Router] ERROR: {error_msg}")

        module_base = os.path.join(module.path, "ui")
        expected_file = os.path.join(module_base, *page_path.split("/")) + ".py"
        app_ctx().logger.debug(f"[Router] Diagnostic: checking for file at {expected_file}")
        if not os.path.exists(expected_file):
            app_ctx().logger.warning("[Router] Diagnostic: File DOES NOT EXIST")
        else:
            app_ctx().logger.debug(
                "[Router] Diagnostic: File EXISTS, import failed for other reasons (check __init__.py)"
            )
        return printErrorResponse(404, error_msg)
    except AccessDeniedError:
        raise
    except Exception as exc:
        app_ctx().logger.error(f"[Router] Unexpected error: {exc}")
        app_ctx().logger.error(traceback.format_exc())
        return printErrorResponse(500, f"INTERNAL ERROR: {exc}")
