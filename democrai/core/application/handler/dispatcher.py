from typing import Any, Dict, List, Callable
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.application.auth.module_access import is_module_locked_for_session
from democrai.core.application.auth.action import is_public_action, is_setup_only_action
from democrai.core.application.handler.action_resolution import (
    action_execution_error,
    check_action_permissions,
    resolve_core_action,
    resolve_legacy_action,
    resolve_module_name,
    resolve_registry_action,
    unknown_action_response,
)


def _get_core_default_actions():
    from democrai.core.application.handler.actions.base_handlers import (
        nav,
        navigate,
        render_route_surface,
        open_modal,
        open_drawer,
        close_modal,
        close_drawer,
        logout,
        refresh_token,
        load_client_auth_context,
        get_notifications_count,
        background_task_get,
        list_notifications,
        approve_external_access,
        get_supported_languages,
        get_user_language,
        set_user_language,
        modules_list,
        composer_transcribe_audio,
        orchestration_test,
    )
    from democrai.core.application.runtime_prompt.actions import runtime_prompt_response

    return {
        "nav": nav,
        "navigate": navigate,
        "render_route_surface": render_route_surface,
        "open_modal": open_modal,
        "open_drawer": open_drawer,
        "close_modal": close_modal,
        "close_drawer": close_drawer,
        "logout": logout,
        "refresh_token": refresh_token,
        "load_client_auth_context": load_client_auth_context,
        "get_notifications_count": get_notifications_count,
        "background_task.get": background_task_get,
        "list_notifications": list_notifications,
        "approve_external_access": approve_external_access,
        "get_supported_languages": get_supported_languages,
        "get_user_language": get_user_language,
        "set_user_language": set_user_language,
        "modulesList": modules_list,
        "composer_transcribe_audio": composer_transcribe_audio,
        "orchestration_test": orchestration_test,
        "runtime_prompt_response": runtime_prompt_response,
    }


class ActionDispatcher:
    """
    Central dispatcher for all user actions.

    Responsibilities:
    1. Routes actions to Core handlers or Module functions.
    2. Enforces permission checks (for metadata-decorated module actions).
    3. Provides a unified interface for the Request Handler.
    """

    def __init__(self):
        self._core_actions: Dict[str, Callable] = {}
        self.register_core_actions()
        self._dispatch_depth_key = "_dispatch_depth"
        self._max_dispatch_depth = 32

    def register_core_actions(self):
        for key, handler in _get_core_default_actions().items():
            self.register_action(key, handler)

    def register_action(self, name: str, handler: Callable):
        """Registers a custom core action handler."""
        self._core_actions[name] = handler

    async def dispatch(
        self, action_name: str, ctx: dict, session: dict, permissions: List[str], sdk
    ) -> Dict[str, Any]:
        """
        Dispatches an action to the appropriate handler.

        Flow:
        1. Checks if it's a registered Core Action.
        2. Resolves ModuleSDK if it's a module action (e.g., 'auth.login').
        3. Searches for handler and validates permissions.
        """

        from democrai.core.infrastructure.modules.runtime import (
            build_module_reuse_key,
            get_module_runtime,
        )
        from democrai.sdk.client import current_sdk as _current_module_sdk

        # _current_module_sdk is set twice intentionally:
        # - outer `token`: makes the request-level sdk available to resolution helpers
        # - inner `inner_token`: overrides with the resolved module's sdk before calling
        #   the handler, so that decorators like @sdk.action read the correct module context
        token = _current_module_sdk.set(sdk)
        depth_incremented = False
        starting_depth = 0

        try:
            if isinstance(session, dict):
                starting_depth = session.get(self._dispatch_depth_key, 0) or 0
                if starting_depth >= self._max_dispatch_depth:
                    return {
                        "ok": False,
                        "type": "error",
                        "error": "recursion_limit_exceeded",
                        "details": f"Action recursion depth exceeded ({self._max_dispatch_depth})",
                    }
                session[self._dispatch_depth_key] = starting_depth + 1
                depth_incremented = True

            resolved = resolve_core_action(action_name, self._core_actions, sdk)
            if resolved is None:
                resolved = resolve_registry_action(action_name, session, sdk)
            if resolved is None:
                resolved = resolve_legacy_action(action_name, session)
            if resolved is None:
                return unknown_action_response(action_name)

            denied = self._check_guest_action_access(action_name, resolved.handler, session)
            if denied is not None:
                return denied

            denied = check_action_permissions(action_name, resolved.handler, permissions)
            if denied is not None:
                return denied

            inner_token = _current_module_sdk.set(resolved.sdk)
            module_name = resolve_module_name(action_name)
            if module_name is None:
                sdk_module = getattr(resolved.sdk, "module_name", None)
                if sdk_module and sdk_module != "core":
                    module_name = sdk_module
            try:
                if module_name is not None and module_name != "core":
                    if is_module_locked_for_session(module_name, session):
                        app_ctx().logger.warning(
                            f"[Dispatcher] Access Denied for module '{module_name}'. Module is locked."
                        )
                        return {
                            "ok": False,
                            "type": "error",
                            "error": "module_locked",
                            "details": module_name,
                        }
                    module = app_ctx().modules.get_module(module_name)
                    if module is not None:
                        runtime_response = await get_module_runtime().invoke(
                            module=module,
                            operation="action",
                            payload={
                                "handler_module": str(getattr(resolved.handler, "__module__", "") or ""),
                                "handler_name": str(getattr(resolved.handler, "__name__", "") or ""),
                                "action_name": action_name,
                                "ctx": ctx,
                                "session": session,
                            },
                            session=session,
                            metadata={"mode": "module_action", "action_name": action_name},
                            persistent=True,
                            reuse_key=build_module_reuse_key(module.name, session),
                            lock_key=f"action:{action_name}",
                        )
                        if isinstance(runtime_response, dict):
                            mutated_session = runtime_response.get("session")
                            if isinstance(mutated_session, dict):
                                session.clear()
                                session.update(mutated_session)
                            result = runtime_response.get("result")
                            if isinstance(result, dict):
                                return result
                        return runtime_response
                return await resolved.handler(ctx, session, resolved.sdk)
            except Exception as e:
                return action_execution_error(action_name, e, source=resolved.source)
            finally:
                _current_module_sdk.reset(inner_token)
        except Exception as __e:
            app_ctx().logger.error(f"[Dispatcher] Exception action: {__e}")
            return {
                "ok": False,
                "type": "error",
                "error": "dispatcher_exception",
                "details": str(__e),
            }
        finally:
            if depth_incremented and isinstance(session, dict):
                current_depth = session.get(self._dispatch_depth_key, 0) or 0
                restored_depth = max(0, current_depth - 1)
                if restored_depth == 0:
                    session.pop(self._dispatch_depth_key, None)
                else:
                    session[self._dispatch_depth_key] = restored_depth
            _current_module_sdk.reset(token)

    @staticmethod
    def _check_guest_action_access(action_name: str, handler: Callable, session: dict) -> dict | None:
        if is_setup_only_action(handler):
            if bool(getattr(app_ctx(), "setup_mode", False)):
                return None
            return {
                "ok": False,
                "type": "error",
                "error": "setup_mode_required",
                "details": action_name,
            }

        try:
            from democrai.core.runtime.foundation.app import req_ctx

            authenticated = req_ctx().user is not None
        except LookupError:
            user = session.get("user") if isinstance(session, dict) else None
            if user is None:
                return None
            authenticated = isinstance(user, dict) and user.get("id") not in (None, "", "guest")

        if authenticated or is_public_action(handler):
            return None
        return {
            "ok": False,
            "type": "error",
            "error": "authentication_required",
            "details": action_name,
        }
