from __future__ import annotations

import time
from typing import Any, Dict, List, Callable, Awaitable

from democrai.core.runtime.foundation.app import (
    app_ctx,
    module_name_from_action,
    req_ctx,
)
from democrai.core.runtime.observability.profiling import (
    current_request_profiler,
    ensure_request_profile,
    stop_request_profile,
)
from democrai.core.runtime.observability.request_flow import trace_request_step
from democrai.core.application.session_keys import SessionKey
from .effects import effects_from_action_result
from .executor import EffectExecutor
from .models import RequestEnvelope

RenderFn = Callable[[dict], Awaitable[List[Dict[str, Any]]]]

_RESERVED_ACTION_CONTEXT_KEYS = {
    "_source_component_id",
    "_stream_id",
    "_surface_id",
    "session_key",
    "stream_id",
}


def _action_context_from_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if key not in _RESERVED_ACTION_CONTEXT_KEYS
    }


class RequestCycleEngine:
    """
    Coordinates request processing for init, ping, and user actions.

    The engine manages the lifecycle of a request, from session retrieval
    and permission checking to action dispatching and effect execution.
    It ensures that Core remains focused on high-level session management
    and UI rendering.
    """

    _PERMISSIONS_TTL_SECONDS = 60.0

    def __init__(self):
        self.effect_executor = EffectExecutor()
        self._action_lock_manager = app_ctx().action_lock_manager

    async def handle(
        self,
        msg: RequestEnvelope | Dict[str, Any],
        *,
        get_session: Callable[[str | None, str | None], dict],
        render: RenderFn,
        dispatcher: Any,
        session_service: Any,
    ) -> List[Dict[str, Any]]:
        """
        Processes an incoming request envelope and returns a list of UI responses.

        :param msg: The incoming message, either as a RequestEnvelope or a raw dict.
        :param get_session: A callable to retrieve or create a session for the user.
        :param render: The rendering function to generate the UI response.
        :param dispatcher: The action dispatcher to handle user/binding actions.
        :param session_service: Service for session persistence and management.
        :return: A list of message dictionaries to be sent back to the transport layer.
        """
        envelope = (
            msg
            if isinstance(msg, RequestEnvelope)
            else RequestEnvelope.from_message(msg)
        )
        message = envelope.message
        request = req_ctx()
        request_id = request.request_id
        user = request.user
        role = request.role
        msg_type = message.get("type")
        request_kind = envelope.kind
        profiler, profile_token, owns_profile = ensure_request_profile(
            request_id, request_kind
        )

        try:
            if envelope.is_ping:
                trace_request_step(
                    request_id,
                    "request.ping",
                    message_type=msg_type or "ping",
                    user=user,
                )
                return [
                    {"ok": True, "type": "pong", "request_id": request_id, "user": user}
                ]

            with profiler.span("session.get"):
                session = get_session(user, role)
            with profiler.span("permissions.get"):
                permissions = self._get_permissions(user, session)

            # Start module background commands once to avoid per-request overhead.
            modules_runtime = getattr(app_ctx(), "modules", None)
            if modules_runtime and hasattr(modules_runtime, "ensure_started"):
                with profiler.span("modules.ensure_started"):
                    await modules_runtime.ensure_started()

            if envelope.is_init:
                # Force full re-render by clearing template cache in session
                session.pop(SessionKey.ACTIVE_MAIN_TEMPLATE, None)
                session.pop(SessionKey.ACTIVE_MAIN_TEMPLATE_LEGACY, None)
                trace_request_step(
                    request_id,
                    "request.init",
                    user=user,
                )
                with profiler.span("render.init"):
                    return await render(session, force_shell=True)

            if envelope.has_binding_action:
                return await self._handle_binding_action(
                    msg=message,
                    session=session,
                    permissions=permissions,
                    dispatcher=dispatcher,
                )

            if not envelope.has_user_action:
                return []

            return await self._handle_user_action(
                msg=message,
                session=session,
                permissions=permissions,
                render=render,
                dispatcher=dispatcher,
                session_service=session_service,
                request_user=user,
                request_role=role,
                request_channel=request.channel,
            )
        finally:
            if owns_profile:
                profiler.finish()
                if profile_token is not None:
                    stop_request_profile(profile_token)

    def _get_permissions(self, user: int | None, session: dict | None) -> List[str]:
        """
        Retrieves and caches user permissions for the current session.

        :param user: The unique identifier of the user (integer ID).
        :param session: The current session dictionary for caching.
        :return: A list of permission strings granted to the user.
        """
        if bool(getattr(app_ctx(), "setup_mode", False)):
            return []
        if user is None:
            return []
        if session is None:
            session = {}

        now = time.monotonic()
        cached_user = session.get(SessionKey.PERM_CACHE_USER)
        cached_ts = session.get(SessionKey.PERM_CACHE_TS)
        cached_values = session.get(SessionKey.PERM_CACHE_VALUES)
        if (
            cached_user == user
            and isinstance(cached_ts, (int, float))
            and (now - float(cached_ts)) < self._PERMISSIONS_TTL_SECONDS
            and isinstance(cached_values, list)
        ):
            return [str(p) for p in cached_values]

        from democrai.core.application.auth.service import get_user_permissions

        permissions = get_user_permissions(user)
        session[SessionKey.PERM_CACHE_USER] = user
        session[SessionKey.PERM_CACHE_TS] = now
        session[SessionKey.PERM_CACHE_VALUES] = permissions
        return permissions

    async def _handle_user_action(
        self,
        *,
        msg: Dict[str, Any],
        session: dict,
        permissions: List[str],
        render: RenderFn,
        dispatcher: Any,
        session_service: Any,
        request_user: int | None,
        request_role: str | None,
        request_channel: str,
    ) -> List[Dict[str, Any]]:
        """
        Internal handler for explicit user actions (e.g., button clicks).

        Manages action locking, dispatching to modules, and execution of resulting effects.

        :param msg: The raw message dictionary containing the 'userAction'.
        :param session: The current user session.
        :param permissions: List of permissions for the current user.
        :param render: The rendering function.
        :param dispatcher: The action dispatcher.
        :param session_service: Session management service.
        :param request_user: The user ID from the request context.
        :param request_role: The user role from the request context.
        :param request_channel: The communication channel (e.g., 'desktop').
        :return: A list of UI messages (effects and/or re-render).
        """
        from democrai.sdk.client import SDK

        request = req_ctx()
        request_id = request.request_id
        session_key = request.session_key
        organization_id = request.organization_id

        action = msg["userAction"]
        name = action["name"]
        request.module_name = module_name_from_action(name)
        action_ctx = _action_context_from_payload(action.get("context", {}))
        surface_id = action.get("surfaceId")
        if isinstance(surface_id, str) and surface_id:
            action_ctx["_surface_id"] = surface_id
        source_component_id = action.get("sourceComponentId")
        if isinstance(source_component_id, str) and source_component_id:
            action_ctx["_source_component_id"] = source_component_id

        action_ctx["stream_id"] = request.stream_id or None
        action_ctx["session_key"] = session_key or None

        lock_key = self._action_lock_key(
            action_name=name,
            user=request_user,
            session_key=session_key,
        )
        if lock_key:
            acquired = await self._action_lock_manager.acquire(lock_key, request_id)
            if not acquired:
                trace_request_step(
                    request_id,
                    "action.dispatch.busy",
                    action_name=name,
                    user=request_user,
                )
                return [
                    {
                        "ok": False,
                        "type": "action_busy",
                        "error": "action_busy",
                        "request_id": request_id,
                        "actionBusy": {
                            "action": name,
                            "requestId": request_id,
                        },
                    }
                ]

        request_sdk = SDK(
            "",
            "core",
            current_path=session.get(SessionKey.CURRENT_PATH, ""),
            session=session,
        )
        profiler = current_request_profiler()
        try:
            trace_request_step(
                request_id,
                "action.dispatch.start",
                action_name=name,
                module_name=module_name_from_action(name),
                user=request_user,
                organization_id=organization_id,
            )

            span = profiler.span if profiler is not None else None
            if span:
                with span("dispatch.user_action"):
                    result = await dispatcher.dispatch(
                        name, action_ctx, session, permissions, request_sdk
                    )
            else:
                result = await dispatcher.dispatch(
                    name, action_ctx, session, permissions, request_sdk
                )
            trace_request_step(
                request_id,
                "action.dispatch.completed",
                action_name=name,
                result_type=type(result).__name__,
            )
            if not isinstance(result, dict):
                app_ctx().logger.error(
                    f"[RequestCycle] Invalid action response for '{name}': {type(result)}"
                )
                trace_request_step(
                    request_id,
                    "action.dispatch.invalid_response",
                    action_name=name,
                    result_type=type(result).__name__,
                )
                return [
                    {
                        "ok": False,
                        "type": "error",
                        "error": "invalid_action_response",
                        "details": f"Expected dict, got {type(result).__name__}",
                    }
                ]

            if result.get("type") == "error":
                trace_request_step(
                    request_id,
                    "action.dispatch.error",
                    action_name=name,
                    error=result.get("error"),
                )
                return [result]

            if span:
                with span("effects.parse"):
                    effects = effects_from_action_result(
                        result, action_name=name, action_context=action_ctx
                    )
            else:
                effects = effects_from_action_result(
                    result, action_name=name, action_context=action_ctx
                )
            if not effects and result and "effects" not in result:
                # Conservative fallback for module actions that return custom payloads.
                if span:
                    with span("effects.parse_fallback"):
                        effects = effects_from_action_result(
                            {"message": result},
                            action_name=name,
                            action_context=action_ctx,
                        )
                else:
                    effects = effects_from_action_result(
                        {"message": result}, action_name=name, action_context=action_ctx
                    )
            trace_request_step(
                request_id,
                "effects.parsed",
                action_name=name,
                effect_count=len(effects),
            )

            if span:
                with span("effects.execute"):
                    return await self.effect_executor.execute(
                        effects=effects,
                        session=session,
                        context=request,
                        action_name=name,
                        action_context=action_ctx,
                        render=render,
                        session_service=session_service,
                    )
            return await self.effect_executor.execute(
                effects=effects,
                session=session,
                context=request,
                action_name=name,
                action_context=action_ctx,
                render=render,
                session_service=session_service,
            )
        finally:
            if lock_key:
                await self._action_lock_manager.release(lock_key, request_id)

    @staticmethod
    def _action_lock_key(
        *,
        action_name: str,
        user: int | None,
        session_key: str | None,
    ) -> str:
        principal = str(user) if user is not None else session_key
        action = action_name
        if not principal or not action:
            return ""
        return f"user:{principal}:action:{action}"

    async def _handle_binding_action(
        self,
        *,
        msg: Dict[str, Any],
        session: dict,
        permissions: List[str],
        dispatcher: Any,
    ) -> List[Dict[str, Any]]:
        """
        Internal handler for reactive binding actions (e.g., data polling/updates).

        Unlike user actions, binding actions typically return a single value
        intended for a specific UI binding.

        :param msg: The raw message dictionary containing the 'bindingAction'.
        :param session: The current user session.
        :param permissions: List of permissions for the current user.
        :param dispatcher: The action dispatcher.
        :return: A list containing a 'bindingActionResult' message.
        """
        from democrai.sdk.client import SDK

        request = req_ctx()
        request_id = request.request_id
        action = msg["bindingAction"]
        name = action.get("name", "")
        action_ctx = _action_context_from_payload(action.get("context", {}))
        if request.stream_id:
            action_ctx["stream_id"] = request.stream_id
        if request.session_key:
            action_ctx["session_key"] = request.session_key
        request_sdk = SDK(
            "",
            "core",
            current_path=session.get(SessionKey.CURRENT_PATH, ""),
            session=session,
        )
        trace_request_step(
            request_id,
            "binding.dispatch.start",
            action_name=name,
        )
        profiler = current_request_profiler()
        if profiler is not None:
            with profiler.span("dispatch.binding_action"):
                result = await dispatcher.dispatch(
                    name, action_ctx, session, permissions, request_sdk
                )
        else:
            result = await dispatcher.dispatch(
                name, action_ctx, session, permissions, request_sdk
            )
        trace_request_step(
            request_id,
            "binding.dispatch.completed",
            action_name=name,
            result_type=type(result).__name__,
        )
        if not isinstance(result, dict):
            result = {"value": result}

        if result.get("type") == "error":
            trace_request_step(
                request_id,
                "binding.dispatch.error",
                action_name=name,
                error=result.get("error"),
            )
            return [
                {
                    "bindingActionResult": {
                        "requestId": msg.get("request_id"),
                        "bindingId": action.get("bindingId"),
                        "ok": False,
                        "error": result.get("error"),
                        "details": result.get("details"),
                    }
                }
            ]

        value = result.get("value", result)
        return [
            {
                "bindingActionResult": {
                    "requestId": msg.get("request_id"),
                    "bindingId": action.get("bindingId"),
                    "ok": True,
                    "value": value,
                }
            }
        ]
