from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from democrai.core.application.auth.service import get_user_permissions
from democrai.core.application.runtime_prompt.authorization import (
    check_action_authorization,
    check_prompt_authorization,
)
from democrai.core.application.runtime_prompt.modal import (
    build_runtime_prompt_drawer_messages,
)
from democrai.core.application.runtime_prompt.models import (
    PendingRuntimePrompt,
    RuntimePromptAction,
    RuntimePromptDecision,
    RuntimePromptRequest,
)
from democrai.core.runtime.foundation.app import app_ctx


def _normalize_actions(actions: list[dict[str, Any]]) -> tuple[RuntimePromptAction, ...]:
    normalized: list[RuntimePromptAction] = []
    for item in actions:
        action_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        if not action_id or not label:
            raise ValueError("runtime_prompt_action_invalid")
        raw_permissions = item.get("required_permissions") or ()
        permissions = tuple(
            str(permission).strip()
            for permission in raw_permissions
            if str(permission).strip()
        )
        normalized.append(
            RuntimePromptAction(
                id=action_id,
                label=label,
                required_permissions=permissions,
            )
        )
    if not normalized:
        raise ValueError("runtime_prompt_actions_required")
    return tuple(normalized)


def _normalize_form_model(form_model: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> tuple[dict[str, Any], ...]:
    return tuple(dict(item) for item in (form_model or []) if isinstance(item, dict))


def _request_from_payload(
    *,
    question: str,
    actions: list[dict[str, Any]],
    required_role: str | None,
    required_access_level: int | None,
    required_permissions: list[str] | tuple[str, ...] | None,
    form_model: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    form_values: dict[str, Any] | None,
    request_context: dict[str, Any],
    metadata: dict[str, Any] | None,
    timeout_seconds: float,
) -> RuntimePromptRequest | RuntimePromptDecision:
    prompt_id = uuid4().hex
    resolved_question = str(question or "").strip()
    if not resolved_question:
        raise ValueError("runtime_prompt_question_required")

    user_id = request_context.get("user")
    if user_id is None:
        return RuntimePromptDecision(
            ok=False,
            prompt_id=prompt_id,
            error="runtime_prompt_user_required",
        )

    session_key = str(request_context.get("session_key") or "").strip()
    if not session_key:
        return RuntimePromptDecision(
            ok=False,
            prompt_id=prompt_id,
            error="runtime_prompt_session_required",
        )

    permissions = tuple(
        str(permission).strip()
        for permission in (required_permissions or ())
        if str(permission).strip()
    )

    return RuntimePromptRequest(
        prompt_id=prompt_id,
        question=resolved_question,
        actions=_normalize_actions(actions),
        user_id=user_id,
        organization_id=request_context.get("organization_id"),
        session_key=session_key,
        request_id=str(request_context.get("request_id") or "").strip(),
        role=str(request_context.get("role") or "").strip() or None,
        access_level=request_context.get("access_level"),
        required_role=str(required_role or "").strip() or None,
        required_access_level=required_access_level,
        required_permissions=permissions,
        form_model=_normalize_form_model(form_model),
        form_values=form_values if form_values is not None else {},
        metadata=metadata if metadata is not None else {},
        timeout_seconds=timeout_seconds,
    )


class RuntimePromptService:
    def __init__(self) -> None:
        self._pending: dict[str, PendingRuntimePrompt] = {}

    async def ask(
        self,
        *,
        question: str,
        actions: list[dict[str, Any]],
        required_role: str | None = None,
        required_access_level: int | None = None,
        required_permissions: list[str] | tuple[str, ...] | None = None,
        form_model: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
        form_values: dict[str, Any] | None = None,
        request_context: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        timeout_seconds: float = 300.0,
    ) -> RuntimePromptDecision:
        request = _request_from_payload(
            question=question,
            actions=actions,
            required_role=required_role,
            required_access_level=required_access_level,
            required_permissions=required_permissions,
            form_model=form_model,
            form_values=form_values,
            request_context=request_context,
            metadata=metadata,
            timeout_seconds=timeout_seconds,
        )
        if isinstance(request, RuntimePromptDecision):
            return request

        permissions = get_user_permissions(request.user_id)
        denied = check_prompt_authorization(request, permissions)
        if denied is not None:
            return RuntimePromptDecision(
                ok=False,
                prompt_id=request.prompt_id,
                error=denied,
            )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[RuntimePromptDecision] = loop.create_future()
        self._pending[request.prompt_id] = PendingRuntimePrompt(
            request=request,
            future=future,
        )
        if not self._send_prompt(request):
            self._pending.pop(request.prompt_id, None)
            return RuntimePromptDecision(
                ok=False,
                prompt_id=request.prompt_id,
                error="runtime_prompt_no_active_connection",
            )
        try:
            return await asyncio.wait_for(future, timeout=request.timeout_seconds)
        except asyncio.TimeoutError:
            return RuntimePromptDecision(
                ok=False,
                prompt_id=request.prompt_id,
                error="runtime_prompt_timeout",
            )
        finally:
            self._pending.pop(request.prompt_id, None)

    async def respond(
        self,
        *,
        prompt_id: str,
        action_id: str,
        data: dict[str, Any] | None = None,
        user_id: int | None,
        session_key: str | None,
    ) -> RuntimePromptDecision:
        pending = self._pending.get(prompt_id)
        if pending is None:
            return RuntimePromptDecision(
                ok=False,
                prompt_id=prompt_id,
                error="runtime_prompt_not_found",
            )

        request = pending.request
        if user_id != request.user_id:
            return RuntimePromptDecision(
                ok=False,
                prompt_id=request.prompt_id,
                error="runtime_prompt_user_mismatch",
            )
        if session_key != request.session_key:
            return RuntimePromptDecision(
                ok=False,
                prompt_id=request.prompt_id,
                error="runtime_prompt_session_mismatch",
            )

        permissions = get_user_permissions(request.user_id)
        denied = check_prompt_authorization(request, permissions)
        if denied is not None:
            return RuntimePromptDecision(
                ok=False,
                prompt_id=request.prompt_id,
                error=denied,
            )

        selected = None
        for action in request.actions:
            if action.id == action_id:
                selected = action
                break
        if selected is None:
            return RuntimePromptDecision(
                ok=False,
                prompt_id=request.prompt_id,
                error="runtime_prompt_action_unknown",
            )

        action_denied = check_action_authorization(selected, permissions)
        if action_denied is not None:
            return RuntimePromptDecision(
                ok=False,
                prompt_id=request.prompt_id,
                error=action_denied,
            )

        decision = RuntimePromptDecision(
            ok=True,
            prompt_id=request.prompt_id,
            action=selected.id,
            data=data if data is not None else {},
        )
        if not pending.future.done():
            pending.future.set_result(decision)
        return decision

    def _send_prompt(self, request: RuntimePromptRequest) -> bool:
        registry = getattr(app_ctx(), "connection_registry", None)
        if registry is None:
            return False
        connections = registry.get_connections(request.user_id, request.organization_id)
        if not connections:
            return False

        session_connections = self._filter_session_connections(
            connections,
            request.session_key,
        )
        if not session_connections:
            return False

        messages = build_runtime_prompt_drawer_messages(request)
        for bus, client_id in session_connections:
            for message in messages:
                try:
                    bus.send(client_id, message)
                except Exception as exc:
                    app_ctx().logger.error(
                        f"[RuntimePrompt] Failed to send prompt {request.prompt_id}: {exc}"
                    )
        return True

    def _filter_session_connections(
        self,
        connections,
        session_key: str,
    ):
        network = getattr(app_ctx(), "network", None)
        session_map = getattr(network, "_client_session_keys", None)
        if not isinstance(session_map, dict):
            return list(connections)
        expected = session_key
        return [
            (bus, client_id)
            for bus, client_id in connections
            if session_map.get((id(bus), client_id)) == expected
        ]


_runtime_prompt_service = RuntimePromptService()


def get_runtime_prompt_service() -> RuntimePromptService:
    return _runtime_prompt_service
