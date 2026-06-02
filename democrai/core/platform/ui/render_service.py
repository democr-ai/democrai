from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Dict, List, cast

from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.exceptions import AccessDeniedError
from democrai.core.runtime.observability.profiling import current_request_profiler
from democrai.core.application.home import (
    DEFAULT_GUEST_PAGE,
    remember_post_login_path,
    resolve_guest_page_path,
    resolve_home_page_path,
)
from democrai.core.application.routing import Router
from democrai.core.application.session_keys import SessionKey
from democrai.sdk.ui import Builder
from democrai.sdk.client import active_sdk as sdk
from democrai.core.platform.utils.debug import debug_ui_trace as _debug_ui_trace
from democrai.core.platform.ui.media_sources import rewrite_builder_media_sources


class RenderService:
    """
    Builds protocol-level UI responses from session state and module routes.

    RenderService is responsible for resolving the current path, building the UI
    components through the Router, and generating the surface update messages
    required by the desktop/web clients. It handles both full shell updates
    and incremental 'persistent' renders of the main content area.
    """
    _MAIN_TEMPLATE_SESSION_KEY = SessionKey.ACTIVE_MAIN_TEMPLATE
    _LEGACY_MAIN_TEMPLATE_SESSION_KEY = SessionKey.ACTIVE_MAIN_TEMPLATE_LEGACY
    _ACTIVE_APP_SESSION_KEY = "active_app_name"
    _CLIENT_SURFACE_RESET_SESSION_KEY = "_client_surface_reset"
    _PENDING_TOASTS_SESSION_KEY = "_pending_toasts"

    def __init__(self, session_service):
        self.session_service = session_service

    async def render(self, session: dict, force_shell: bool = False) -> List[Dict[str, Any]]:
        """
        Computes the next UI state based on the current session.

        :param session: The current user session dictionary.
        :param force_shell: If True, forces a full shell re-render even if incremental is possible.
        :return: A list of protocol messages (surfaceUpdate, beginRendering, etc.).
        """
        profiler = current_request_profiler()
        if profiler is None:
            user = self._get_session_user(session)
            current_path = self._resolve_current_path(session)
            _debug_ui_trace(
                "render_start",
                current_path=current_path,
                user=user,
                setup_mode=getattr(app_ctx(), "setup_mode", False),
                session_keys=sorted(session.keys()),
            )
            content_builder = await self._resolve_content(current_path, session, user)
            current_path = self._resolve_current_path(session)
            app_name, page_path, params = Router.parse_path(current_path)
            if session.pop(self._CLIENT_SURFACE_RESET_SESSION_KEY, False):
                force_shell = True

            # Force shell render if we are switching between apps/modules,
            # as the desktop client clears the main surface container on app switch.
            if not force_shell and session.get(self._ACTIVE_APP_SESSION_KEY) != app_name:
                force_shell = True

            prev_template = self._active_main_template(session)
            if self._should_use_persistent_shell(content_builder):
                return await self._render_persistent_shell(
                    session=session,
                    user=user,
                    current_path=current_path,
                    content_builder=content_builder,
                    force_refresh=force_shell,
                )

            app_name, page_path, params = Router.parse_path(current_path)
            rewrite_builder_media_sources(content_builder, module_name=app_name)
            if self._is_subsurface_render(content_builder):
                return await self._render_subsurface_response(
                    session=session,
                    user=user,
                    current_path=current_path,
                    content_builder=content_builder,
                    app_name=app_name,
                    page_path=page_path,
                    params=params,
                    force_shell=force_shell,
                )
            builder, page_root_ids = self._build_page_container(content_builder, current_path)
            _debug_ui_trace(
                "page_container",
                current_path=current_path,
                component_ids=[getattr(c, "id", None) for c in getattr(builder, "_components", [])],
                page_root_ids=page_root_ids,
                template=getattr(content_builder, "template", None),
            )
            await self._append_pending_modal(builder, page_root_ids, session)
            self._finalize_layout(builder, page_root_ids, content_builder, session)
            prev_template = self._active_main_template(session)
            extra_messages = [
                *self._cleanup_aux_surfaces(session),
                *self._consume_pending_toasts(session),
            ]
            
            # Resolve the main content surface ID from the template's @main_content tag
            main_content_surface_id = self._resolve_main_content_surface_id(content_builder.template, session)
            
            if prev_template and not self._should_use_persistent_shell(content_builder, prev_template):
                extra_messages.append({"deleteSurface": {"surfaceId": main_content_surface_id}})
            response = self._build_render_response(
                builder, app_name, page_path, params, extra_messages=extra_messages
            )
            self._store_active_main_template(session, content_builder.template)
            _debug_ui_trace(
                "render_response",
                current_path=current_path,
                response_keys=[sorted(msg.keys()) for msg in response],
                response_len=len(response),
            )
            return response

        with profiler.span("render.user_lookup"):
            user = self._get_session_user(session)
        with profiler.span("render.path_resolve"):
            current_path = self._resolve_current_path(session)
        with profiler.span("render.content"):
            content_builder = await self._resolve_content(current_path, session, user)
        with profiler.span("render.path_refresh"):
            current_path = self._resolve_current_path(session)
        
        app_name, page_path, params = Router.parse_path(current_path)
        if session.pop(self._CLIENT_SURFACE_RESET_SESSION_KEY, False):
            force_shell = True
        prev_template = self._active_main_template(session)
        if not force_shell and session.get(self._ACTIVE_APP_SESSION_KEY) != app_name:
            force_shell = True

        if self._should_use_persistent_shell(content_builder):
            with profiler.span("render.persistent_shell"):
                return await self._render_persistent_shell(
                    session=session,
                    user=user,
                    current_path=current_path,
                    content_builder=content_builder,
                    force_refresh=force_shell,
                )
        with profiler.span("render.parse_path"):
            app_name, page_path, params = Router.parse_path(current_path)
        rewrite_builder_media_sources(content_builder, module_name=app_name)
        if self._is_subsurface_render(content_builder):
            with profiler.span("render.subsurface"):
                return await self._render_subsurface_response(
                    session=session,
                    user=user,
                    current_path=current_path,
                    content_builder=content_builder,
                    app_name=app_name,
                    page_path=page_path,
                    params=params,
                    force_shell=force_shell,
                )
        extra_messages = [
            *self._cleanup_aux_surfaces(session),
            *self._consume_pending_toasts(session),
        ]
        with profiler.span("render.page_container"):
            builder, page_root_ids = self._build_page_container(content_builder, current_path)
        with profiler.span("render.pending_modal"):
            await self._append_pending_modal(builder, page_root_ids, session)
        with profiler.span("render.finalize_layout"):
            self._finalize_layout(builder, page_root_ids, content_builder, session)
        with profiler.span("render.build_response"):
            # Resolve the main content surface ID from the template's @main_content tag
            main_content_surface_id = self._resolve_main_content_surface_id(content_builder.template, session)
             
            if prev_template and not self._should_use_persistent_shell(content_builder, prev_template):
                extra_messages.append({"deleteSurface": {"surfaceId": main_content_surface_id}})
            response = self._build_render_response(builder, app_name, page_path, params, extra_messages=extra_messages)
        self._store_active_main_template(session, content_builder.template)
        return response

    def _is_subsurface_render(self, builder: Builder) -> bool:
        return bool(getattr(builder, "surface_id", "main") != "main" and getattr(builder, "shell_route", None))

    def _get_session_user(self, session: dict) -> str:
        user = session.get(SessionKey.USER, {})
        return (user.get("username") or user.get("name") or "guest") if user else "guest"

    def _resolve_current_path(self, session: dict) -> str:
        if app_ctx().setup_mode:
            return "/system/setup"
        current_path = session.get(SessionKey.CURRENT_PATH, "")
        if isinstance(current_path, str) and current_path.strip() not in {"", "/"}:
            return current_path

        user = session.get(SessionKey.USER) if isinstance(session, dict) else None
        username = user.get("username") or user.get("name") if isinstance(user, dict) else ""
        if isinstance(user, dict) and username != "guest":
            return resolve_home_page_path()
        return resolve_guest_page_path()

    async def _resolve_content(self, current_path: str, session: dict, user: str):
        """
        Delegates to the Router to resolve a path into a UI component builder.

        Handles authentication redirects and dependency-missing modals.

        :param current_path: The URL-like path to resolve (e.g., '/chat/main').
        :param session: The current session.
        :param user: The username/ID for logging purposes.
        :return: An Builder instance representing the target UI.
        """
        try:
            builder = await Router.resolve(current_path, session)
            _debug_ui_trace(
                "resolve_content",
                current_path=current_path,
                user=user,
                builder_type=type(builder).__name__,
                component_ids=[getattr(c, "id", None) for c in getattr(builder, "_components", [])],
            )
            return builder
        except AccessDeniedError:
            remember_post_login_path(session, current_path)
            guest_path = resolve_guest_page_path()
            app_ctx().logger.info(f"[Render] Access denied. Redirecting to {guest_path}")
            session[SessionKey.CURRENT_PATH] = guest_path
            self.session_service.persist(user or "guest")
            try:
                return await Router.resolve(guest_path, session)
            except AccessDeniedError:
                app_ctx().logger.warning(
                    f"[Render] Guest page {guest_path} is not public. Falling back to {DEFAULT_GUEST_PAGE}"
                )
                session[SessionKey.CURRENT_PATH] = DEFAULT_GUEST_PAGE
                self.session_service.persist(user or "guest")
                return await Router.resolve(DEFAULT_GUEST_PAGE, session)
        except Exception as e:
            from democrai.core.runtime.foundation.exceptions import DependencyMissingError

            if not isinstance(e, DependencyMissingError):
                raise

            app_ctx().logger.warning(f"[Render] Dependency missing during render: {e}")
            dependency = (
                e.dependency
                or e.dependency_key
                or str(e).split(": ")[-1]
            )
            self._queue_toast(
                session,
                {
                    "kind": "toast",
                    "variant": "error",
                    "title": "Missing dependency",
                    "text": f"Missing AI dependency: {dependency}",
                },
            )
            return await Router.resolve(current_path, session)

    def _build_page_container(self, content_builder, current_path: str):
        builder = Builder()
        builder.merge(content_builder, components=True, replace=True)
        page_roots = content_builder.get_roots()
        page_root_ids = [c.id for c in page_roots if c.id]
        _debug_ui_trace(
            "build_page_container",
            current_path=current_path,
            page_root_ids=page_root_ids,
            component_ids=[getattr(c, "id", None) for c in getattr(builder, "_components", [])],
        )
        return builder, page_root_ids

    async def _render_subsurface_response(
        self,
        *,
        session: dict,
        user: str,
        current_path: str,
        content_builder: Builder,
        app_name: str,
        page_path: str,
        params: Dict[str, Any],
        force_shell: bool = False,
    ) -> List[Dict[str, Any]]:
        profiler = current_request_profiler()
        response: List[Dict[str, Any]] = [
            {
                "current_path": {
                    "app_name": app_name,
                    "page_path": page_path,
                    "params": params,
                }
            }
        ]
        shell_route = cast(str, content_builder.shell_route)
        active_shell_route = session.get("_active_shell_route")
        shell_changed = force_shell or active_shell_route != shell_route
        raw_active_aux = session.get("_active_aux_surfaces")
        active_aux = list(raw_active_aux) if isinstance(raw_active_aux, list) else []
        stale_aux_surfaces = [
            surface_id
            for surface_id in active_aux
            if surface_id != content_builder.surface_id
        ]

        if shell_changed:
            span = profiler.span if profiler is not None else None
            with span("render.subsurface.shell") if span else nullcontext():
                shell_builder = await self._resolve_content(shell_route, session, user)
                rewrite_builder_media_sources(
                    shell_builder,
                    module_name=self._module_name_for_path(shell_route),
                )
                builder, page_root_ids = self._build_page_container(shell_builder, current_path)
                await self._append_pending_modal(builder, page_root_ids, session)
                self._finalize_layout(builder, page_root_ids, shell_builder, session)
                response.extend(self._build_surface_messages(builder, surface_id="main", include_window_actions=True))

        for stale_surface_id in stale_aux_surfaces:
            response.append({"deleteSurface": {"surfaceId": stale_surface_id}})

        span = profiler.span if profiler is not None else None
        with span("render.subsurface.aux") if span else nullcontext():
            response.extend(
                self._build_aux_surface_messages(
                    content_builder,
                    surface_id=content_builder.surface_id,
                )
            )
        with span("render.subsurface.session") if span else nullcontext():
            session["_active_shell_route"] = shell_route
            session["_active_aux_surfaces"] = [content_builder.surface_id]

            # Reset template state to ensure navigation back to full shell works
            self._store_active_main_template(session, None)
            session.pop(self._ACTIVE_APP_SESSION_KEY, None)

        response.extend(self._consume_pending_toasts(session))
        return response

    def _cleanup_aux_surfaces(self, session: dict) -> List[Dict[str, Any]]:
        raw_active_aux = session.get("_active_aux_surfaces")
        active_aux = list(raw_active_aux) if isinstance(raw_active_aux, list) else []
        session.pop("_active_aux_surfaces", None)
        session.pop("_active_shell_route", None)
        return [
            {"deleteSurface": {"surfaceId": surface_id}}
            for surface_id in active_aux
            if surface_id not in {"main", "main_content"}
        ]

    async def _append_pending_modal(self, builder, page_root_ids: list[str], session: dict):
        pending = session.get(SessionKey.PENDING_MODAL)
        if not pending:
            return

        if isinstance(pending, str):
            modal_path = pending
            modal_params = {}
        elif isinstance(pending, dict):
            modal_path = pending.get("path")
            raw_modal_params = pending.get("params")
            modal_params = raw_modal_params if isinstance(raw_modal_params, dict) else {}
        else:
            session[SessionKey.PENDING_MODAL] = None
            return

        try:
            modal_builder = await Router.resolve(modal_path, session, extra_params=modal_params)
            rewrite_builder_media_sources(
                modal_builder,
                module_name=self._module_name_for_path(modal_path),
            )
            modal_roots = modal_builder.get_roots()
            modal_root_ids = [c.id for c in modal_roots if c.id]

            dialog = sdk.ui.Dialog("pending_modal_frame", "Democrai", modal_root_ids)
            builder.add(dialog)
            builder.merge(modal_builder, components=True)
            page_root_ids.append("pending_modal_frame")
        except Exception as e:
            app_ctx().logger.error(f"[Render] Failed to load pending modal {modal_path}: {e}")
            session[SessionKey.PENDING_MODAL] = None

    @staticmethod
    def _module_name_for_path(path: str) -> str:
        app_name, _, _ = Router.parse_path(path if isinstance(path, str) else "")
        return app_name if isinstance(app_name, str) and app_name else "dashboard"

    def _finalize_layout(self, builder, page_root_ids: list[str], content_builder, session: dict):
        wrapper = sdk.ui.Column("content_area_container", page_root_ids)
        wrapper.set_property("stretch", True)
        builder.add(wrapper)
        builder.set_template(content_builder.template, session)

    def _build_render_response(
        self,
        builder,
        app_name: str,
        page_path: str,
        params: Dict[str, Any],
        extra_messages: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        response: List[Dict[str, Any]] = [
            {
                "current_path": {
                    "app_name": app_name,
                    "page_path": page_path,
                    "params": params,
                }
            }
        ]
        if extra_messages:
            response.extend(extra_messages)
        response.extend(
            self._build_surface_messages(
                builder, surface_id="main", include_window_actions=True
            )
        )
        app_ctx().logger.debug(f"[Render] Render response: {response}")
        return response

    @staticmethod
    def _should_use_persistent_shell(builder: Builder) -> bool:
        """
        Check if we can perform a persistent render (incremental update of content area).
        Conditions:
        - Target surface is 'main' (not a subsurface render)
        - A template is selected
        - No shell route override (which forces a different rendering path)
        """
        return (
            getattr(builder, "surface_id", "main") == "main"
            and bool(getattr(builder, "template", None))
            and not getattr(builder, "shell_route", None)
        )

    @staticmethod
    def _active_main_template(session: dict) -> str | None:
        value = session.get(RenderService._MAIN_TEMPLATE_SESSION_KEY)
        if not (isinstance(value, str) and value):
            value = session.get(RenderService._LEGACY_MAIN_TEMPLATE_SESSION_KEY)
        return str(value) if isinstance(value, str) and value else None

    @staticmethod
    def _store_active_main_template(session: dict, template_name: str | None) -> None:
        if template_name:
            session[RenderService._MAIN_TEMPLATE_SESSION_KEY] = str(template_name)
            session.pop(RenderService._LEGACY_MAIN_TEMPLATE_SESSION_KEY, None)
        else:
            session.pop(RenderService._MAIN_TEMPLATE_SESSION_KEY, None)
            session.pop(RenderService._LEGACY_MAIN_TEMPLATE_SESSION_KEY, None)

    async def _render_persistent_shell(
        self,
        *,
        session: dict,
        user: str,
        current_path: str,
        content_builder: Builder,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Performs an incremental render of the main content area without refreshing the outer shell.

        :param session: The current session.
        :param user: The username/ID.
        :param current_path: The path being rendered.
        :param content_builder: The builder for the main content area.
        :param force_refresh: Force a template refresh if true.
        :return: List of protocol messages.
        """
        profiler = current_request_profiler()
        app_name, page_path, params = Router.parse_path(current_path)
        rewrite_builder_media_sources(content_builder, module_name=app_name)
        extra_messages = [
            *self._cleanup_aux_surfaces(session),
            *self._consume_pending_toasts(session),
        ]
        response: List[Dict[str, Any]] = [
            {
                "current_path": {
                    "app_name": app_name,
                    "page_path": page_path,
                    "params": params,
                }
            }
        ]
        if extra_messages:
            response.extend(extra_messages)

        raw_template = content_builder.template
        current_template = raw_template if isinstance(raw_template, str) and raw_template else "full"
        prev_tpl = self._active_main_template(session)
        main_template_changed = force_refresh or prev_tpl != current_template
        
        if main_template_changed:
            with profiler.span("render.persistent_shell.shell") if profiler else nullcontext():
                if prev_tpl:
                    old_sid = self._resolve_main_content_surface_id(prev_tpl, session)
                    response.append({"deleteSurface": {"surfaceId": old_sid}})

                shell_builder = Builder()
                shell_builder.set_template(current_template, session)
                response.extend(
                    self._build_surface_messages(
                        shell_builder,
                        surface_id="main",
                        include_window_actions=True,
                    )
                )

        with profiler.span("render.persistent_shell.content") if profiler else nullcontext():
            main_content_surface_id = self._resolve_main_content_surface_id(current_template, session)
            response.extend(
                self._build_aux_surface_messages(
                    content_builder,
                    surface_id=main_content_surface_id,
                )
            )

        pending = session.get(SessionKey.PENDING_MODAL)
        if pending:
            modal_path = pending if isinstance(pending, str) else pending.get("path")
            modal_params = {} if isinstance(pending, str) else pending.get("params", {})
            if isinstance(modal_path, str) and modal_path:
                try:
                    modal_builder = await Router.resolve(
                        modal_path,
                        session,
                        extra_params=modal_params,
                    )
                    rewrite_builder_media_sources(
                        modal_builder,
                        module_name=self._module_name_for_path(modal_path),
                    )
                    response.extend(
                        self._build_aux_surface_messages(
                            modal_builder,
                            surface_id="modal",
                        )
                    )
                    session["_pending_modal_active"] = True
                except Exception as exc:
                    app_ctx().logger.error(
                        f"[Render] Failed to load pending modal {modal_path}: {exc}"
                    )
                    session[SessionKey.PENDING_MODAL] = None
                    if session.pop("_pending_modal_active", False):
                        response.append({"deleteSurface": {"surfaceId": "modal"}})
        elif session.pop("_pending_modal_active", False):
            response.append({"deleteSurface": {"surfaceId": "modal"}})

        self._store_active_main_template(session, current_template)
        session[self._ACTIVE_APP_SESSION_KEY] = app_name
        return response

    @classmethod
    def _queue_toast(cls, session: dict, payload: dict[str, Any]) -> None:
        pending = session.setdefault(cls._PENDING_TOASTS_SESSION_KEY, [])
        if isinstance(pending, list):
            pending.append({"eventNotification": payload})

    @classmethod
    def _consume_pending_toasts(cls, session: dict) -> list[dict[str, Any]]:
        pending = session.pop(cls._PENDING_TOASTS_SESSION_KEY, [])
        return [item for item in pending if isinstance(item, dict)] if isinstance(pending, list) else []

    def _build_surface_messages(
        self,
        builder: Builder,
        *,
        surface_id: str,
        include_window_actions: bool,
    ) -> List[Dict[str, Any]]:
        window_actions = (
            [
                {"windowAction": {"op": "resize", "width": 500, "height": 700}},
                {"windowAction": {"op": "center"}},
            ]
            if builder.template_dimensions == "window"
            else [{"windowAction": {"op": "maximize"}}]
        )

        response: List[Dict[str, Any]] = []
        profiler = current_request_profiler()
        with profiler.span("render.surface.surface_update") if profiler else nullcontext():
            response.extend(builder.build_surface_update_payload(surface_id))
        with profiler.span("render.surface.data_model") if profiler else nullcontext():
            response.extend(self._build_data_model_messages(builder, surface_id=surface_id))
        with profiler.span("render.surface.store") if profiler else nullcontext():
            response.extend(self._build_store_messages(builder))
        with profiler.span("render.surface.final_messages") if profiler else nullcontext():
            response.append({"beginRendering": {"root": "root", "surfaceId": surface_id}})
            if include_window_actions:
                response.extend(window_actions)
        return response

    def _build_aux_surface_messages(
        self,
        builder: Builder,
        *,
        surface_id: str,
    ) -> List[Dict[str, Any]]:
        profiler = current_request_profiler()
        with profiler.span("render.aux.get_roots") if profiler else nullcontext():
            root_ids = [c.id for c in builder.get_roots() if c.id]
        if not root_ids:
            return [{"deleteSurface": {"surfaceId": surface_id}}]
        if len(root_ids) > 1:
            with profiler.span("render.aux.wrap_roots") if profiler else nullcontext():
                wrapper = Builder()
                wrapper.merge(builder, components=True, replace=True)
                wrapper.add(sdk.ui.Column(f"{surface_id}_root", root_ids))
                builder = wrapper
                root_ids = [f"{surface_id}_root"]

        response: List[Dict[str, Any]] = []
        with profiler.span("render.aux.surface_update") if profiler else nullcontext():
            response.extend(builder.build_surface_update_payload(surface_id))
        with profiler.span("render.aux.data_model") if profiler else nullcontext():
            response.extend(self._build_data_model_messages(builder, surface_id=surface_id))
        with profiler.span("render.aux.store") if profiler else nullcontext():
            response.extend(self._build_store_messages(builder))
        with profiler.span("render.aux.final_messages") if profiler else nullcontext():
            response.append(
                {"beginRendering": {"root": root_ids[0], "surfaceId": surface_id}}
            )
        return response

    @staticmethod
    def _resolve_main_content_surface_id(template_name: str, session: dict) -> str:
        """
        Identifies which surface ID is marked as the main content anchor (@main_content)
        in the given template.

        Defaults to 'main_content' for backwards compatibility if no explicit anchor is found.

        :param template_name: The name of the registered template.
        :param session: The current session.
        :return: The surface ID string (e.g., 'main_content', 'chat_surface').
        """
        from democrai.core.runtime.foundation.registry import template_registry
        profiler = current_request_profiler()
        with profiler.span("render.resolve_main_surface.template_lookup") if profiler else nullcontext():
            tpl_func = template_registry.get(template_name)
        if not tpl_func:
            return "main_content"
            
        try:
            with profiler.span("render.resolve_main_surface.template_call") if profiler else nullcontext():
                components, _ = tpl_func(session=session)
            with profiler.span("render.resolve_main_surface.scan") if profiler else nullcontext():
                component_items = components if isinstance(components, list) else []
                for comp in component_items:
                    if not isinstance(comp, dict): continue
                    inner = comp.get("component")
                    if not isinstance(inner, dict): continue
                    ctype = list(inner.keys())[0] if inner else None
                    props = inner.get(ctype) if ctype else None
                    if isinstance(props, dict) and props.get("tag") == "@main_content":
                        # For SurfaceHost, the surface_id is what we want
                        s_id = props.get("surface_id")
                        if isinstance(s_id, str) and s_id:
                            return s_id
                        # Fallback to component ID
                        component_id = comp.get("id")
                        return component_id if isinstance(component_id, str) and component_id else "main_content"
        except Exception:
            pass
            
        return "main_content"

    @staticmethod
    def _build_data_model_messages(
        builder: Builder,
        *,
        surface_id: str,
    ) -> List[Dict[str, Any]]:
        data_model = getattr(builder, "_data_model", None)
        if not isinstance(data_model, dict) or not data_model:
            return []
        return [
            Builder.build_data_model_update_payload(
                surface_id=surface_id,
                data=data_model,
            )
        ]

    @staticmethod
    def _build_store_messages(builder: Builder) -> List[Dict[str, Any]]:
        store_data = getattr(builder, "_store_data", None)
        if not isinstance(store_data, dict):
            return []
        messages: List[Dict[str, Any]] = []
        for scope in ("page", "global"):
            values = store_data.get(scope)
            if isinstance(values, dict) and values:
                messages.append(
                    Builder.build_state_update_payload(
                        values,
                        scope=scope,
                    )
                )
        return messages
