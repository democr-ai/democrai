from __future__ import annotations

import inspect
from contextlib import nullcontext
from typing import Any, Dict, List, Callable, Awaitable

from democrai.core.platform.utils.debug import debug_auth_flow as _debug_auth_flow
from democrai.core.runtime.foundation.app import (
    RequestContext,
    app_ctx,
    reset_req_ctx,
    set_req_ctx,
)
from democrai.core.runtime.observability.profiling import current_request_profiler
from democrai.core.runtime.observability.request_flow import trace_request_step
from democrai.core.runtime.foundation.registry import task_registry
from democrai.core.application.tasks.notification_queue import NotificationQueue
from democrai.core.application.routing import Router
from democrai.core.application.session_keys import SessionKey
from democrai.sdk.ui import Builder
from democrai.sdk.client import active_sdk as sdk

from .effects import (
    BaseEffect,
    ConfirmEffect,
    NavigateEffect,
    NotifyEffect,
    RefreshModulesEffect,
    RenderEffect,
    ScrollEffect,
    SetJwtEffect,
    StartPipelineEffect,
    UiMessagesEffect,
)

RenderFn = Callable[[dict], Awaitable[List[Dict[str, Any]]]]


class SessionTransaction:
    """
    Buffers session mutations and applies them atomically on commit.

    Prevents partially-applied state if an effect fails mid-loop.
    Usage: `txn.set(key, value)` during the loop, `txn.commit()` at the end.
    """

    def __init__(self, session: dict) -> None:
        self._session = session
        self._changes: Dict[str, Any] = {}
        self._mutated = False

    def set(self, key: str, value: Any) -> None:
        """
        Registers a change to be applied to the session.

        :param key: The session key to update.
        :param value: The new value for the key.
        """
        self._changes[key] = value

    def commit(self) -> bool:
        """Apply buffered changes to session. Returns True if any changes were applied."""
        if not self._changes:
            return self._mutated
        for k, v in self._changes.items():
            self._session[k] = v
        self._mutated = True
        self._changes.clear()
        return True

    @property
    def mutated(self) -> bool:
        """True if any changes have been committed or are pending."""
        return self._mutated or bool(self._changes)


class EffectExecutor:
    """
    Executes typed effects and builds final protocol response messages.

    The executor takes a list of high-level Effect objects and translates them
    into low-level protocol messages (e.g., UI updates, navigation, notifications).
    It also manages session persistence and background task spawning.
    """

    def __init__(self):
        self._notification_queue = NotificationQueue()

    async def execute(
        self,
        *,
        effects: List[BaseEffect],
        session: dict,
        context: RequestContext,
        action_name: str,
        action_context: Dict[str, Any],
        render: RenderFn,
        session_service: Any,
    ) -> List[Dict[str, Any]]:
        """
        Executes a list of effects and returns the resulting protocol messages.

        :param effects: The list of effects to execute.
        :param session: The current user session.
        :param context: The request context containing metadata (ID, user, etc.).
        :param action_name: The name of the action that produced these effects.
        :param action_context: The context parameters of the action.
        :param render: The rendering function to call for UI-refreshing effects.
        :param session_service: Service for session persistence.
        :return: A list of message dictionaries for the transport response.
        """
        response: List[Dict[str, Any]] = []
        jwt_token: str | None = None
        trace_request_step(
            context.request_id,
            "effects.execute.start",
            effect_count=len(effects),
            action_name=action_name,
        )
        profiler = current_request_profiler()
        span = profiler.span if profiler is not None else None
        with span("effects.persist_identity_change") if span else nullcontext():
            current_user_key = session_service.persist_identity_change(
                session, context.user, context.session_key
            )
        txn = SessionTransaction(session)

        for effect in effects:
            app_ctx().logger.debug(
                f"[Effects] Executing effect={effect.kind} req={context.request_id}",
                "effects",
            )

            if isinstance(effect, NavigateEffect):
                with span("effects.navigate") if span else nullcontext():
                    txn.set(SessionKey.CURRENT_PATH, effect.path)
                    txn.commit()
                    if effect.render:
                        response.extend(await render(session))
                    else:
                        response.append({"current_path": effect.path})
                continue

            if isinstance(effect, RenderEffect):
                with span("effects.render") if span else nullcontext():
                    if effect.path:
                        txn.set(SessionKey.CURRENT_PATH, effect.path)
                        txn.commit()
                    response.extend(await render(session))
                continue

            if isinstance(effect, UiMessagesEffect):
                with span("effects.ui_messages") if span else nullcontext():
                    response.extend(effect.messages)
                continue

            if isinstance(effect, StartPipelineEffect):
                with span("effects.pipeline") if span else nullcontext():
                    pipeline_msg = await self._start_pipeline(
                        effect, session, context, action_name
                    )
                    response.append(pipeline_msg)
                continue

            if isinstance(effect, ConfirmEffect):
                with span("effects.confirm") if span else nullcontext():
                    response.extend(
                        await self._handle_confirmation(
                            effect,
                            session=session,
                            context=context,
                            action_name=action_name,
                        )
                    )
                continue

            if isinstance(effect, NotifyEffect):
                with span("effects.notify") if span else nullcontext():
                    self._handle_notify(effect, session, context)
                continue

            if isinstance(effect, RefreshModulesEffect):
                with span("effects.refresh_modules") if span else nullcontext():
                    from democrai.core.application.handler.actions.base_handlers import (
                        _get_modules_list,
                    )

                    response.append(_get_modules_list(session))
                continue

            if isinstance(effect, ScrollEffect):
                with span("effects.scroll") if span else nullcontext():
                    response.append(
                        Builder.build_property_update_payload(
                            component_id=effect.component_id,
                            property_name="scroll",
                            value="bottom",
                            action="set",
                            surface_id="main",
                        )
                    )
                continue

            if isinstance(effect, SetJwtEffect):
                with span("effects.set_jwt") if span else nullcontext():
                    jwt_token = effect.token
                    _debug_auth_flow(
                        "effects.set_jwt",
                        request_id=context.request_id,
                        token_len=len(jwt_token or ""),
                        action_name=action_name,
                    )
                continue

        with span("effects.txn_commit") if span else nullcontext():
            txn.commit()
        with span("effects.persist") if span else nullcontext():
            if txn.mutated or self._needs_persist_due_to_render(response):
                session_service.persist(current_user_key)

        with span("effects.jwt_response") if span else nullcontext():
            if jwt_token is not None:
                if response and isinstance(response[0], dict):
                    response[0]["jwt"] = jwt_token
                    _debug_auth_flow(
                        "effects.jwt_injected_first_response",
                        request_id=context.request_id,
                        response_keys=list(response[0].keys()),
                        token_len=len(jwt_token or ""),
                    )
                else:
                    response.append({"jwt": jwt_token})
                    _debug_auth_flow(
                        "effects.jwt_appended_response",
                        request_id=context.request_id,
                        token_len=len(jwt_token or ""),
                    )

        trace_request_step(
            context.request_id,
            "effects.executed",
            effect_count=len(effects),
            response_count=len(response),
        )
        return response

    def _needs_persist_due_to_render(self, response: List[Dict[str, Any]]) -> bool:
        for item in response:
            if (
                "surfaceUpdate" in item
                or "beginRendering" in item
                or "current_path" in item
            ):
                return True
        return False

    async def _start_pipeline(
        self,
        effect: StartPipelineEffect,
        session: dict,
        context: RequestContext,
        action_name: str,
    ) -> Dict[str, Any]:
        tm = app_ctx().task_manager
        if not tm:
            raise RuntimeError("TaskManager not initialized")

        user = session.get(SessionKey.USER, {})
        user_id = user.get("id")
        if user_id is None:
            raise ValueError("user_id is required")
        module = effect.module or "core"
        pipeline_coro = self._build_pipeline_coroutine(effect, context, action_name)
        task_id = await tm.submit(
            user_id=user_id,
            task_or_coro=pipeline_coro,
            label=effect.label,
            module=module,
            organization_id=context.organization_id,
        )

        return {
            "pipeline": {
                "status": "started",
                "taskId": task_id,
                "label": effect.label,
                "module": module,
                "requestId": context.request_id,
            }
        }

    def _build_pipeline_coroutine(
        self, effect: StartPipelineEffect, context: RequestContext, action_name: str
    ):
        task = effect.task
        args = effect.args

        async def _runner():
            pipeline_ctx = RequestContext(
                app=app_ctx(),
                request_id=context.request_id,
                user=context.user,
                role=context.role,
                organization_id=context.organization_id,
                access_level=context.access_level,
                channel=context.channel,
                session_key=context.session_key,
                client_ip=context.client_ip,
                action_name=action_name,
                module_name=context.module_name,
                stream_id=context.stream_id,
            )
            token = set_req_ctx(pipeline_ctx)
            try:
                if isinstance(task, str):
                    func = task_registry.get(task)
                    if not func:
                        raise ValueError(f"Task '{task}' not found in registry.")
                    if inspect.iscoroutinefunction(func):
                        return await func(**args)
                    return func(**args)

                if inspect.iscoroutine(task):
                    return await task

                if callable(task):
                    if inspect.iscoroutinefunction(task):
                        return await task(**args)
                    return task(**args)

                raise ValueError(
                    "Pipeline task must be a task name (str), callable, or coroutine."
                )
            finally:
                reset_req_ctx(token)

        return _runner()

    async def _handle_confirmation(
        self,
        effect: ConfirmEffect,
        *,
        session: dict,
        context: RequestContext,
        action_name: str,
    ) -> List[Dict[str, Any]]:
        response: List[Dict[str, Any]] = []
        via = effect.via.lower()
        should_dialog = effect.render and via in {"dialog", "both"}
        should_email = via in {"email", "both"}

        if should_dialog:
            if effect.path:
                response.extend(
                    await self._build_confirmation_modal_messages(
                        path=effect.path,
                        params=effect.params,
                        session=session,
                    )
                )
            else:
                app_ctx().logger.warning(
                    f"[Effects] Confirmation dialog requested without a path: {action_name}"
                )

        if should_email:
            payload = {
                "kind": "confirmation_required",
                "requestId": context.request_id,
                "action": action_name,
                "details": effect.params,
            }
            self._handle_notify(
                NotifyEffect(
                    channel="email",
                    payload=payload,
                    user_id=context.user,
                    organization_id=context.organization_id,
                ),
                session,
                context,
            )

        return response

    async def _build_confirmation_modal_messages(
        self,
        *,
        path: str,
        params: dict,
        session: dict,
    ) -> List[Dict[str, Any]]:
        modal_builder = await Router.resolve(path, session, extra_params=params)
        modal_roots = [c.id for c in modal_builder.get_roots() if c.id]
        if not modal_roots:
            return []

        dialog = sdk.ui.Dialog("confirmation_modal_frame", "Democrai", modal_roots)
        wrapper = Builder()
        wrapper.merge(modal_builder, components=True, replace=True)
        wrapper.add(dialog)

        messages = list(wrapper.build_surface_update_payload("modal"))
        data_model = getattr(modal_builder, "_data_model", None)
        if isinstance(data_model, dict) and data_model:
            messages.append(
                modal_builder.__class__.build_data_model_update_payload(
                    surface_id="modal",
                    data=data_model,
                )
            )
        store_data = getattr(modal_builder, "_store_data", None)
        if isinstance(store_data, dict):
            for scope in ("page", "global"):
                values = store_data.get(scope)
                if isinstance(values, dict) and values:
                    messages.append(
                        modal_builder.__class__.build_state_update_payload(
                            values,
                            scope=scope,
                        )
                    )
        messages.append(
            {
                "beginRendering": {
                    "root": "confirmation_modal_frame",
                    "surfaceId": "modal",
                }
            }
        )
        return messages

    def _handle_notify(
        self, effect: NotifyEffect, session: dict, context: RequestContext
    ) -> None:
        """
        Dispatches a notification to the appropriate channel (in-app, email, etc.).

        :param effect: The notification effect details.
        :param session: The current user session.
        :param context: The current request context.
        """
        channel = effect.channel.lower()
        user_id = (
            effect.user_id
            if effect.user_id is not None
            else (session.get(SessionKey.USER) or {}).get("id") or context.user
        )
        if not user_id or isinstance(user_id, str):
            return
        organization_id = (
            effect.organization_id
            if effect.organization_id is not None
            else context.organization_id
        )
        if user_id is None:
            app_ctx().logger.warning(
                f"[Effects] Skipping notify on channel '{channel}' because no user is available"
            )
            return
        payload = effect.payload
        if channel == "toast":
            if not str(payload.get("kind") or "").strip():
                payload["kind"] = "toast"
            if (
                not str(payload.get("text") or "").strip()
                and str(payload.get("message") or "").strip()
            ):
                payload["text"] = str(payload.get("message") or "").strip()
            if not str(payload.get("title") or "").strip():
                level = (
                    str(payload.get("level") or payload.get("variant") or "info")
                    .strip()
                    .lower()
                )
                payload["title"] = {
                    "success": "Success",
                    "error": "Error",
                    "warning": "Warning",
                    "warn": "Warning",
                    "info": "Info",
                }.get(level, "Info")

        # 1. Try custom notifier service if registered in DI container.
        notifier = app_ctx().container.get(EventNotifier)
        if notifier:
            try:
                try:
                    notifier.notify(
                        channel=channel,
                        user_id=user_id,
                        organization_id=organization_id,
                        payload=payload,
                    )
                except TypeError:
                    notifier.notify(channel=channel, user_id=user_id, payload=payload)
                return
            except Exception as e:
                app_ctx().logger.error(f"[Effects] Custom notifier failed: {e}")

        # 2. Built-in channels.
        if channel in {"inapp", "in_app", "ws", "bus", "toast"}:
            message = {"eventNotification": payload}
            if not self._send_to_user(user_id, organization_id, message):
                self._notification_queue.enqueue(
                    user_id=user_id,
                    organization_id=organization_id,
                    task_id=context.request_id,
                    notif_type="event",
                    payload=payload,
                )
            return

        if channel == "email":
            app_ctx().logger.info(
                f"[Effects] Email notification requested (no provider configured): user={user_id} payload={effect.payload}"
            )
            return

        app_ctx().logger.warning(f"[Effects] Unknown notify channel '{channel}'")

    def _send_to_user(
        self, user_id: int, organization_id: int | None, message: dict
    ) -> bool:
        registry = getattr(app_ctx(), "connection_registry", None)
        if not registry:
            return False
        connections = registry.get_connections(user_id, organization_id)
        if not connections:
            bridge = getattr(app_ctx(), "redis_task_bridge", None)
            if bridge:
                bridge.publish(user_id, message, organization_id)
                return True
            return False
        for bus, client_id in connections:
            try:
                bus.send(client_id, message)
            except Exception as e:
                app_ctx().logger.error(f"[Effects] Send notify error: {e}")
        return True


class EventNotifier:
    """Optional notifier interface injectable via DI container."""

    def notify(
        self,
        *,
        channel: str,
        user_id: int,
        payload: Dict[str, Any],
        organization_id: int | None = None,
    ) -> None:
        raise NotImplementedError
