from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import os
import subprocess
from typing import Any, Callable, Optional

from democrai.sdk.ui import Builder
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import (
    RequestContext,
    app_ctx,
    req_ctx,
    reset_req_ctx,
    set_req_ctx,
)
from democrai.core.runtime.foundation.registry import task_registry


class Tasks:
    """Expose background-task orchestration helpers to modules."""

    def __init__(self, sdk) -> None:
        """Create the tasks facade for the current SDK instance."""
        self.sdk = sdk

    def _capture_request_context(self) -> RequestContext | None:
        try:
            current = req_ctx()
        except LookupError:
            return None
        return RequestContext(
            request_id=current.request_id,
            user=current.user,
            role=current.role,
            organization_id=current.organization_id,
            access_level=current.access_level,
            channel=current.channel,
            app=current.app,
            session_key=current.session_key,
            client_ip=current.client_ip,
            action_name=current.action_name,
            stream_id=current.stream_id,
        )

    def _build_request_context(self, *, task_id: str | None = None) -> RequestContext:
        current = self._capture_request_context()
        user = self.sdk.session.get("user") or {}
        user_id = to_optional_int(user.get("id"))
        organization_id = to_optional_int(user.get("organization_id"))
        role = str(user.get("role") or "").strip() or None
        access_level = to_optional_int(user.get("access_level"))
        session_key = str(self.sdk.session.get("session_key") or "").strip() or None
        if current is not None:
            return RequestContext(
                request_id=current.request_id or f"sdk-task:{task_id or self.sdk.module_name}",
                user=current.user if current.user is not None else user_id,
                role=current.role or role,
                organization_id=(
                    current.organization_id
                    if current.organization_id is not None
                    else organization_id
                ),
                access_level=(
                    current.access_level
                    if current.access_level is not None
                    else access_level
                ),
                channel=current.channel or "ipc",
                app=current.app or app_ctx(),
                session_key=current.session_key or session_key,
                client_ip=current.client_ip,
                action_name=current.action_name,
                stream_id=current.stream_id,
            )
        return RequestContext(
            request_id=f"sdk-task:{task_id or self.sdk.module_name}",
            user=user_id,
            role=role,
            organization_id=organization_id,
            access_level=access_level,
            channel="ipc",
            app=app_ctx(),
            session_key=session_key,
            client_ip=None,
            action_name=None,
            stream_id=None,
        )

    def _registered_module(self):
        try:
            return getattr(app_ctx(), "modules", None).get_module(self.sdk.module_name)
        except Exception as exc:
            app_ctx().logger.error(
                f"[SDK Tasks] failed_to_resolve_module_for_sandbox: {self.sdk.module_name} - {exc}"
            )
            raise

    def _runtime_guard(
        self,
        request_context: RequestContext,
        *,
        allow_subprocess: bool = False,
    ) -> contextlib.AbstractContextManager[Any]:
        from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

        module_name = str(self.sdk.module_name or "").strip()
        if module_name == "core":
            return contextlib.nullcontext()
        if not module_name:
            raise RuntimeError(f"sdk_task_module_not_registered:{module_name}")
        registered = self._registered_module()
        return process_guard_context(
            subject=module_name,
            subject_kind="module",
            access=registered.access,
            allow_subprocess=allow_subprocess,
            user_id=request_context.user,
            organization_id=request_context.organization_id,
            session_key=request_context.session_key,
        )

    def _subprocess_sandbox_env(
        self,
        request_context: RequestContext | None = None,
    ) -> dict[str, str]:
        module_name = str(self.sdk.module_name or "").strip()
        if not module_name or module_name == "core":
            return {}
        registered = self._registered_module()
        env = {
            "DEMOCRAI_NETWORK_SUBJECT": module_name,
            "DEMOCRAI_NETWORK_SUBJECT_KIND": "module",
            "DEMOCRAI_ACCESS": json.dumps(
                [rule.to_dict() for rule in registered.access],
            ),
        }
        if request_context is not None:
            if request_context.user is not None:
                env["DEMOCRAI_USER_ID"] = str(request_context.user)
            if request_context.organization_id is not None:
                env["DEMOCRAI_ORGANIZATION_ID"] = str(request_context.organization_id)
            if request_context.session_key:
                env["DEMOCRAI_SESSION_KEY"] = str(request_context.session_key)
        return env

    @contextlib.contextmanager
    def _task_runtime_context(
        self,
        request_context: RequestContext,
        *,
        allow_subprocess: bool = False,
    ):
        from democrai.sdk.client import current_sdk

        sdk_token = current_sdk.set(self.sdk)
        req_token = set_req_ctx(request_context)
        try:
            with self._runtime_guard(
                request_context,
                allow_subprocess=allow_subprocess,
            ):
                yield
        finally:
            reset_req_ctx(req_token)
            current_sdk.reset(sdk_token)

    def _coerce_coroutine(self, task_or_coro: Callable | str, **kwargs) -> Any:
        """Normalize a coroutine object or registered task name into an awaitable."""
        if asyncio.iscoroutine(task_or_coro):
            return task_or_coro
        if isinstance(task_or_coro, str):
            func = task_registry.get(task_or_coro)
            if not func:
                raise ValueError(f"Task '{task_or_coro}' not found in registry.")
            if inspect.iscoroutinefunction(func):
                return func(**kwargs)

            async def _wrapper():
                return func(**kwargs)

            return _wrapper()
        raise ValueError("Task must be a coroutine or a registered task name (str).")

    async def run_background(
        self,
        coro: Callable | str,
        label: str = "Background Task",
        **kwargs,
    ) -> str:
        """Submit a background task for the current authenticated user."""
        from democrai.core.runtime.foundation.app import app_ctx

        task_manager = app_ctx().task_manager

        user = self.sdk.session.get("user", {})
        user_id = to_optional_int(user.get("id"))
        organization_id = to_optional_int(user.get("organization_id"))
        if user_id is None:
            raise ValueError("user_id is required")

        if not task_manager:
            raise RuntimeError("TaskManager not initialized")

        return await task_manager.submit(
            user_id,
            coro,
            label,
            module=self.sdk.module_name,
            organization_id=organization_id,
            **kwargs,
        )

    async def run_blocking(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Run a blocking callable in a worker thread and await its result."""
        if not callable(func):
            raise TypeError("func must be callable")
        request_context = self._build_request_context()

        def _runner() -> Any:
            with self._task_runtime_context(request_context):
                return func(*args, **kwargs)

        return await asyncio.to_thread(_runner)

    async def run_subprocess(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        check: bool = False,
        text: bool = True,
        capture_output: bool = True,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[Any]:
        """Run a subprocess under module sandbox context.

        Subprocess execution is intentionally available only via this SDK entrypoint.
        """
        if not isinstance(command, list) or not command:
            raise TypeError("command must be a non-empty list[str]")
        normalized_command: list[str] = []
        for item in command:
            token = str(item or "").strip()
            if not token:
                raise ValueError("command contains empty token")
            normalized_command.append(token)

        request_context = self._build_request_context()
        runtime_env = dict(os.environ)
        if env is not None:
            if not isinstance(env, dict):
                raise TypeError("env must be dict[str, str]")
            for key, value in env.items():
                runtime_env[str(key)] = str(value)
        runtime_env.update(self._subprocess_sandbox_env(request_context))

        def _runner() -> subprocess.CompletedProcess[Any]:
            with self._task_runtime_context(
                request_context,
                allow_subprocess=True,
            ):
                from democrai.core.infrastructure.sandbox.launcher import run_subprocess

                return run_subprocess(
                    normalized_command,
                    cwd=cwd,
                    check=check,
                    text=text,
                    capture_output=capture_output,
                    timeout=timeout,
                    env=runtime_env,
                )

        return await asyncio.to_thread(_runner)

    async def update_progress(
        self,
        task_id: str,
        progress: float,
        checkpoint: Optional[dict[str, Any]] = None,
        label: Optional[str] = None,
    ) -> None:
        """Update progress for a running task."""
        from democrai.core.runtime.foundation.app import app_ctx

        task_manager = app_ctx().task_manager
        if task_manager:
            await task_manager.update_progress(task_id, progress, checkpoint, label)
            return

    async def emit_progress(
        self,
        task_id: str,
        progress: float | None = None,
        label: Optional[str] = None,
        checkpoint: Optional[dict[str, Any]] = None,
    ) -> None:
        """Emit a live progress update without persisting the task row."""
        from democrai.core.runtime.foundation.app import app_ctx

        task_manager = app_ctx().task_manager
        if task_manager:
            await task_manager.emit_progress(task_id, progress, label, checkpoint)
            return

    async def request_confirmation(
        self,
        task_id: str,
        builder: Builder,
    ) -> dict[str, Any]:
        """Request interactive confirmation for a running task using a UI builder."""
        from democrai.core.runtime.foundation.app import app_ctx

        task_manager = app_ctx().task_manager
        if not task_manager:
            raise RuntimeError("TaskManager not initialized")

        components = [component.to_dict() for component in builder._components]
        return await task_manager.request_confirmation(task_id, components)

    def list_user_tasks(
        self,
        user_id: int,
        organization_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Return serialized tasks visible to a user."""
        from democrai.core.runtime.foundation.app import app_ctx

        task_manager = app_ctx().task_manager
        if not task_manager:
            return []

        try:
            tasks = task_manager.get_user_tasks_serialized(user_id, organization_id)
        except Exception:
            return []
        return tasks if isinstance(tasks, list) else []

    def get_tasks_by_key(
        self,
        task_key: str,
        organization_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Return serialized tasks that match an exact task key."""
        from democrai.core.runtime.foundation.app import app_ctx

        task_manager = app_ctx().task_manager
        if not task_manager:
            return []

        try:
            tasks = task_manager.get_tasks_by_key(task_key, organization_id)
        except Exception:
            return []

        tasks.sort(key=lambda task: task.created_at, reverse=True)
        return [task.to_dict() for task in tasks]

    def get_tasks_by_key_prefix(
        self,
        prefix: str,
        organization_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Return serialized tasks whose key starts with a prefix."""
        from democrai.core.runtime.foundation.app import app_ctx

        task_manager = app_ctx().task_manager
        if not task_manager:
            return []

        try:
            tasks = task_manager.get_tasks_by_key_prefix(prefix, organization_id)
        except Exception:
            return []

        tasks.sort(key=lambda task: task.created_at, reverse=True)
        return [task.to_dict() for task in tasks]
