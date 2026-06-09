"""
TaskManager — orchestrates background tasks with progress tracking,
checkpoints for resume, and notification delivery to users.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import traceback
from concurrent.futures import Future as ConcurrentFuture
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import OperationalError

from democrai.core.platform.utils.identity import to_optional_int, to_required_int
from democrai.core.platform.utils.timezone import (
    format_app_datetime,
    serialize_app_datetime,
    utc_now_naive,
)
from democrai.core.runtime.foundation.app import RequestContext
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx
from democrai.core.runtime.foundation.app import reset_req_ctx
from democrai.core.runtime.foundation.app import set_req_ctx
from democrai.core.runtime.foundation.registry import task_registry


def _required_request_id(request_id: Any) -> str:
    if not isinstance(request_id, str) or not request_id:
        raise RuntimeError("task_request_id_required")
    return request_id


def _capture_request_context() -> RequestContext | None:
    try:
        current = req_ctx()
    except LookupError:
        return None
    return RequestContext(
        request_id=_required_request_id(current.request_id),
        user=current.user,
        role=current.role,
        organization_id=current.organization_id,
        access_level=current.access_level,
        channel=str(current.channel or "ipc"),
        app=current.app,
        session_key=current.session_key,
        client_ip=current.client_ip,
        action_name=current.action_name,
        module_name=current.module_name or "core",
        stream_id=current.stream_id,
    )


def _build_task_request_context(
    *,
    task_id: str,
    user_id: int,
    organization_id: int | None,
    current: RequestContext | None,
) -> RequestContext:
    if current is not None:
        request_id = current.request_id
        if not request_id:
            request_id = f"task:{task_id}"
        return RequestContext(
            request_id=request_id,
            user=current.user if current.user is not None else user_id,
            role=current.role,
            organization_id=(
                current.organization_id
                if current.organization_id is not None
                else organization_id
            ),
            access_level=current.access_level,
            channel=str(current.channel or "ipc"),
            app=current.app or app_ctx(),
            session_key=current.session_key,
            client_ip=current.client_ip,
            action_name=current.action_name,
            module_name=current.module_name or "core",
            stream_id=current.stream_id,
        )
    return RequestContext(
        request_id=f"task:{task_id}",
        user=user_id,
        role=None,
        organization_id=organization_id,
        access_level=None,
        channel="ipc",
        app=app_ctx(),
        session_key=None,
        client_ip=None,
        action_name=None,
        module_name="core",
        stream_id=None,
    )


def _registered_module(module_name: str):
    try:
        return getattr(app_ctx(), "modules", None).get_module(module_name)
    except Exception as exc:
        app_ctx().logger.error(
            f"[TaskManager] failed_to_resolve_module_for_sandbox: {module_name} - {exc}"
        )
        raise


def _required_module_name(module_name: str) -> str:
    if not isinstance(module_name, str):
        raise RuntimeError("task_module_name_required")
    if not module_name:
        raise RuntimeError("task_module_name_required")
    return module_name


def _optional_task_key(task_key: str | None) -> str | None:
    if task_key is None:
        return None
    if not isinstance(task_key, str):
        raise RuntimeError("task_key_must_be_string")
    if not task_key:
        return None
    return task_key


def _organization_log_value(organization_id: Optional[int]) -> str:
    return "none" if organization_id is None else str(organization_id)


def _capture_process_guard_state() -> dict[str, Any] | None:
    try:
        from democrai.core.infrastructure.sandbox import process_guard

        state = process_guard._state()
    except Exception:
        return None
    if not isinstance(state, dict) or not state:
        return None
    return {
        "subject": str(state.get("subject") or "").strip(),
        "subject_kind": str(state.get("subject_kind") or "module").strip() or "module",
        "access": tuple(state.get("access") or ()),
        "allowed_imports": list(state.get("allowed_imports") or ()),
        "allowed_subprocess_commands": list(
            state.get("allowed_subprocess_commands") or ()
        ),
        "allow_subprocess": bool(state.get("allow_subprocess")),
        "allow_fork": bool(state.get("allow_fork")),
    }

def _task_execution_context(
    *,
    module_name: str,
    request_context: RequestContext,
    inherited_sandbox_state: dict[str, Any] | None = None,
) -> contextlib.AbstractContextManager[Any]:
    from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

    resolved_module_name = _required_module_name(module_name)
    if resolved_module_name == "core":
        return contextlib.nullcontext()
    if isinstance(inherited_sandbox_state, dict) and inherited_sandbox_state:
        inherited_subject = str(inherited_sandbox_state.get("subject") or resolved_module_name)
        inherited_subject_kind = str(inherited_sandbox_state.get("subject_kind") or "module")
        return process_guard_context(
            subject=inherited_subject,
            subject_kind=inherited_subject_kind,
            access=tuple(inherited_sandbox_state.get("access") or ()),
            allowed_imports=list(inherited_sandbox_state.get("allowed_imports") or ()),
            allowed_subprocess_commands=list(
                inherited_sandbox_state.get("allowed_subprocess_commands") or ()
            ),
            allow_subprocess=bool(inherited_sandbox_state.get("allow_subprocess")),
            allow_fork=bool(inherited_sandbox_state.get("allow_fork")),
            include_runtime_access=True,
            inherit_parent_access=False,
            user_id=request_context.user,
            organization_id=request_context.organization_id,
            session_key=request_context.session_key,
        )
    registered = _registered_module(resolved_module_name)
    return process_guard_context(
        subject=resolved_module_name,
        subject_kind="module",
        access=registered.access,
        user_id=request_context.user,
        organization_id=request_context.organization_id,
        session_key=request_context.session_key,
    )


_DURABLE_EXTERNAL_TASK_KEY_PREFIXES = ("knowledge.extraction:",)


def _is_durable_external_task_key(task_key: str | None) -> bool:
    if task_key is None:
        return False
    if not isinstance(task_key, str):
        raise RuntimeError("task_key_must_be_string")
    return any(
        task_key.startswith(prefix)
        for prefix in _DURABLE_EXTERNAL_TASK_KEY_PREFIXES
    )


@dataclass
class BackgroundTask:
    """
    Represents a long-running operation with progress tracking and persistence.

    Tasks can be submitted by modules and tracked by the TaskManager. They support
    checkpoints for resumption and can store a final result or error message.
    """

    id: str
    user_id: int
    module: str
    label: str
    organization_id: Optional[int] = None
    task_key: Optional[str] = None
    status: str = "pending"
    progress: float = 0.0
    checkpoint: dict = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now_naive)
    updated_at: datetime = field(default_factory=utc_now_naive)
    _asyncio_task: Optional[asyncio.Task | ConcurrentFuture] = field(default=None, repr=False)
    _confirmation_future: Optional[asyncio.Future] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "taskId": self.id,
            "userId": self.user_id,
            "organizationId": self.organization_id,
            "taskKey": self.task_key,
            "module": self.module,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
            "checkpoint": self.checkpoint,
            "result": self.result,
            "error": self.error,
            "createdAt": serialize_app_datetime(self.created_at),
            "updatedAt": serialize_app_datetime(self.updated_at),
            "createdAtLabel": format_app_datetime(self.created_at),
            "updatedAtLabel": format_app_datetime(self.updated_at),
        }


class TaskManager:
    """
    Orchestrates the execution and lifecycle of background tasks.

    The TaskManager provides methods for submitting, updating, and managing
    asynchronous tasks. It integrates with the database for persistence and
    the connection registry for real-time notifications.
    """

    def __init__(self):
        self._tasks: Dict[str, BackgroundTask] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def submit(
        self,
        user_id: int,
        task_or_coro,
        label: str,
        module: str = "core",
        organization_id: Optional[int] = None,
        task_key: Optional[str] = None,
        **kwargs,
    ):
        """
        Submits a new background task for execution.

        :param user_id: ID of the user owning the task.
        :param task_or_coro: The task name (str) or a coroutine to run.
        :param label: Human-readable label for the task.
        :param module: Name of the module originating the task.
        :return: The unique task ID.
        """
        user_id = to_required_int(user_id, "user_id")
        organization_id = to_optional_int(organization_id)
        task_key = _optional_task_key(task_key)

        if task_key:
            existing = self._find_active_task_by_key(task_key, organization_id)
            if existing is not None:
                app_ctx().logger.info(
                    f"[TaskManager] Dedup: returning existing task '{existing.id}' for key '{task_key}'"
                )
                if asyncio.iscoroutine(task_or_coro):
                    task_or_coro.close()
                return existing.id

        coro = None
        if asyncio.iscoroutine(task_or_coro):
            coro = task_or_coro
        elif isinstance(task_or_coro, str):
            func = task_registry.get(task_or_coro)
            if not func:
                raise ValueError(f"Task '{task_or_coro}' not found in registry.")
            if inspect.iscoroutinefunction(func):
                coro = func(**kwargs)
            else:
                async def _wrapper():
                    return func(**kwargs)
                coro = _wrapper()
        else:
            raise ValueError("Task must be a coroutine or a registered task name (str).")

        task_id = str(uuid4())
        bg_task = BackgroundTask(
            id=task_id,
            user_id=user_id,
            module=module,
            label=label,
            organization_id=organization_id,
            task_key=task_key,
        )
        self._tasks[task_id] = bg_task
        self._persist_task(bg_task)
        task_request_context = _build_task_request_context(
            task_id=task_id,
            user_id=user_id,
            organization_id=organization_id,
            current=_capture_request_context(),
        )
        inherited_sandbox_state = _capture_process_guard_state()

        async def _runner():
            req_token = set_req_ctx(task_request_context)
            bg_task.status = "running"
            bg_task.updated_at = utc_now_naive()
            self._persist_task(bg_task)
            try:
                with _task_execution_context(
                    module_name=module,
                    request_context=task_request_context,
                    inherited_sandbox_state=inherited_sandbox_state,
                ):
                    result = await coro
                bg_task.status = "completed"
                bg_task.progress = 1.0
                bg_task.result = result
                bg_task.updated_at = utc_now_naive()
                self._persist_task(bg_task)
                self._notify_user(
                    user_id,
                    organization_id,
                    task_id,
                    "completed",
                    {
                        "label": bg_task.label,
                        "result": result,
                        "updatedAt": serialize_app_datetime(bg_task.updated_at),
                        "updatedAtLabel": format_app_datetime(bg_task.updated_at),
                    },
                )
            except asyncio.CancelledError:
                bg_task.status = "interrupted"
                bg_task.updated_at = utc_now_naive()
                self._persist_task(bg_task)
                app_ctx().logger.info(f"[TaskManager] Task {task_id} cancelled")
            except Exception as e:
                bg_task.status = "failed"
                bg_task.error = str(e)
                bg_task.updated_at = utc_now_naive()
                self._persist_task(bg_task)
                app_ctx().logger.error(
                    f"[TaskManager] Task {task_id} failed: {e}\n{traceback.format_exc()}"
                )
                self._notify_user(
                    user_id,
                    organization_id,
                    task_id,
                    "failed",
                    {
                        "label": bg_task.label,
                        "error": str(e),
                        "updatedAt": serialize_app_datetime(bg_task.updated_at),
                        "updatedAtLabel": format_app_datetime(bg_task.updated_at),
                    },
                )
            finally:
                reset_req_ctx(req_token)

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if self._loop and self._loop.is_running() and self._loop is not running_loop:
            bg_task._asyncio_task = asyncio.run_coroutine_threadsafe(_runner(), self._loop)
        else:
            bg_task._asyncio_task = asyncio.create_task(_runner())

        self._send_to_user(
            user_id,
            organization_id,
            {"backgroundTaskStarted": {"taskId": task_id, "label": label, "module": module}},
        )
        app_ctx().logger.info(
            f"[TaskManager] Submitted task '{label}' ({task_id}) for user '{user_id}' org '{_organization_log_value(organization_id)}'"
        )
        return task_id

    async def submit_external(
        self,
        user_id: int,
        label: str,
        module: str = "core",
        organization_id: Optional[int] = None,
        task_key: Optional[str] = None,
    ):
        return self.submit_external_sync(
            user_id=user_id,
            label=label,
            module=module,
            organization_id=organization_id,
            task_key=task_key,
        )

    def submit_external_sync(
        self,
        user_id: int,
        label: str,
        module: str = "core",
        organization_id: Optional[int] = None,
        task_key: Optional[str] = None,
    ):
        user_id = to_required_int(user_id, "user_id")
        organization_id = to_optional_int(organization_id)
        task_key = _optional_task_key(task_key)

        if task_key:
            existing = self._find_active_task_by_key(task_key, organization_id)
            if existing is not None:
                app_ctx().logger.info(
                    f"[TaskManager] External dedup: returning existing task '{existing.id}' for key '{task_key}'"
                )
                return existing.id, False

        task_id = str(uuid4())
        bg_task = BackgroundTask(
            id=task_id,
            user_id=user_id,
            module=module,
            label=label,
            organization_id=organization_id,
            task_key=task_key,
            status="running",
        )
        self._tasks[task_id] = bg_task
        self._persist_task(bg_task)
        self._send_to_user(
            user_id,
            organization_id,
            {"backgroundTaskStarted": {"taskId": task_id, "label": label, "module": module}},
        )
        app_ctx().logger.info(
            f"[TaskManager] External task started '{label}' ({task_id}) for user '{user_id}' org '{_organization_log_value(organization_id)}'"
        )
        return task_id, True

    def update_progress_sync(
        self,
        task_id: str,
        progress: float,
        checkpoint: Optional[dict] = None,
        label: Optional[str] = None,
    ) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.progress = max(0.0, min(1.0, progress))
        if checkpoint is not None:
            task.checkpoint = checkpoint
        if label is not None:
            task.label = label
        task.updated_at = utc_now_naive()
        self._persist_task(task)

        self._send_to_user(
            task.user_id,
            task.organization_id,
            {
                "backgroundTaskProgress": {
                    "taskId": task_id,
                    "progress": task.progress,
                    "label": task.label,
                    "checkpoint": bool(checkpoint),
                    "updatedAt": serialize_app_datetime(task.updated_at),
                    "updatedAtLabel": format_app_datetime(task.updated_at),
                }
            },
        )
        return True

    async def update_progress(
        self,
        task_id: str,
        progress: float,
        checkpoint: Optional[dict] = None,
        label: Optional[str] = None,
    ) -> None:
        """
        Updates the progress percentage and optionally the checkpoint of a task.

        :param task_id: ID of the task to update.
        :param progress: Float between 0.0 and 100.0.
        :param checkpoint: Optional dictionary for task-specific state.
        :return: Boolean indicating success.
        """
        self.update_progress_sync(
            task_id=task_id,
            progress=progress,
            checkpoint=checkpoint,
            label=label,
        )

    async def emit_progress(
        self,
        task_id: str,
        progress: float | None = None,
        label: Optional[str] = None,
        checkpoint: Optional[dict] = None,
    ) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        resolved_progress = task.progress if progress is None else max(0.0, min(1.0, progress))
        updated_at = utc_now_naive()
        self._send_to_user(
            task.user_id,
            task.organization_id,
            {
                "backgroundTaskProgress": {
                    "taskId": task_id,
                    "progress": resolved_progress,
                    "label": str(label) if label is not None else task.label,
                    "checkpoint": bool(checkpoint),
                    "updatedAt": serialize_app_datetime(updated_at),
                    "updatedAtLabel": format_app_datetime(updated_at),
                }
            },
        )

    async def complete_external(self, task_id: str, result: Any = None) -> bool:
        return self.complete_external_sync(task_id, result=result)

    def complete_external_sync(self, task_id: str, result: Any = None) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = "completed"
        task.progress = 1.0
        task.result = result
        task.updated_at = utc_now_naive()
        self._persist_task(task)
        self._notify_user(
            task.user_id,
            task.organization_id,
            task_id,
            "completed",
            {
                "label": task.label,
                "result": result,
                "updatedAt": serialize_app_datetime(task.updated_at),
                "updatedAtLabel": format_app_datetime(task.updated_at),
            },
        )
        return True

    async def fail_external(self, task_id: str, error: str) -> bool:
        return self.fail_external_sync(task_id, error=error)

    def fail_external_sync(self, task_id: str, error: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if not isinstance(error, str) or not error:
            raise RuntimeError("task_error_required")
        task.status = "failed"
        task.error = error
        task.updated_at = utc_now_naive()
        self._persist_task(task)
        self._notify_user(
            task.user_id,
            task.organization_id,
            task_id,
            "failed",
            {
                "label": task.label,
                "error": task.error,
                "updatedAt": serialize_app_datetime(task.updated_at),
                "updatedAtLabel": format_app_datetime(task.updated_at),
            },
        )
        return True

    async def request_confirmation(self, task_id: str, surface_components: list) -> dict:
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = "waiting_confirmation"
        task.updated_at = utc_now_naive()
        self._persist_task(task)

        loop = asyncio.get_event_loop()
        task._confirmation_future = loop.create_future()

        surface_id = f"task_confirm_{task_id}"
        message = {
            "backgroundTaskConfirmation": {
                "taskId": task_id,
                "label": task.label,
                "surfaceId": surface_id,
                "components": surface_components,
                "updatedAt": serialize_app_datetime(task.updated_at),
                "updatedAtLabel": format_app_datetime(task.updated_at),
            }
        }

        self._notify_user(
            task.user_id,
            task.organization_id,
            task_id,
            "confirmation",
            {
                "label": task.label,
                "surfaceId": surface_id,
                "components": surface_components,
                "updatedAt": serialize_app_datetime(task.updated_at),
                "updatedAtLabel": format_app_datetime(task.updated_at),
            },
            direct_message=message,
        )

        response = await task._confirmation_future
        task.status = "running"
        task.updated_at = utc_now_naive()
        self._persist_task(task)
        return response

    async def respond_confirmation(self, task_id: str, response: dict) -> None:
        task = self._tasks.get(task_id)
        if not task:
            app_ctx().logger.warning(
                f"[TaskManager] Confirmation response for unknown task {task_id}"
            )
            return

        if task._confirmation_future and not task._confirmation_future.done():
            task._confirmation_future.set_result(response)
            app_ctx().logger.info(f"[TaskManager] Confirmation received for task {task_id}")
        else:
            app_ctx().logger.warning(f"[TaskManager] No pending confirmation for task {task_id}")

    async def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task._asyncio_task and not task._asyncio_task.done():
            task._asyncio_task.cancel()
            app_ctx().logger.info(f"[TaskManager] Cancelled task {task_id}")
            return True
        return False

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        return self._tasks.get(task_id)

    def _find_active_task_by_key(
        self,
        task_key: str,
        organization_id: Optional[int],
    ) -> "BackgroundTask | None":
        organization_id = to_optional_int(organization_id)
        active_statuses = {"pending", "running", "waiting_confirmation"}
        for task in self._tasks.values():
            if task.task_key != task_key:
                continue
            if task.organization_id != organization_id:
                continue
            if task.status in active_statuses:
                return task
        return None

    def get_tasks_by_key(
        self,
        task_key: str,
        organization_id: Optional[int] = None,
    ) -> List[BackgroundTask]:
        organization_id = to_optional_int(organization_id)
        return [
            task
            for task in self._tasks.values()
            if task.task_key == task_key and task.organization_id == organization_id
        ]

    def get_tasks_by_key_prefix(
        self,
        prefix: str,
        organization_id: Optional[int] = None,
    ) -> List[BackgroundTask]:
        organization_id = to_optional_int(organization_id)
        return [
            task
            for task in self._tasks.values()
            if task.task_key
            and task.task_key.startswith(prefix)
            and task.organization_id == organization_id
        ]

    def get_user_tasks(
        self,
        user_id: int,
        organization_id: Optional[int] = None,
    ) -> List[BackgroundTask]:
        user_id = to_required_int(user_id, "user_id")
        organization_id = to_optional_int(organization_id)
        return [
            task
            for task in self._tasks.values()
            if task.user_id == user_id and task.organization_id == organization_id
        ]

    def get_user_tasks_serialized(
        self,
        user_id: int,
        organization_id: Optional[int] = None,
    ) -> list:
        tasks = self.get_user_tasks(user_id, organization_id)
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [task.to_dict() for task in tasks]

    def recover_from_db(self) -> int:
        db = self._get_db()
        count = 0
        try:
            from democrai.core.application.tasks.models import BackgroundTaskRecord

            rows = (
                db.query(BackgroundTaskRecord)
                .filter(
                    BackgroundTaskRecord.status.in_(
                        ["pending", "running", "waiting_confirmation"]
                    )
                )
                .all()
            )

            for row in rows:
                task_key = getattr(row, "task_key", None) or None
                durable_external = _is_durable_external_task_key(task_key)
                status = row.status if durable_external else "interrupted"
                error = (
                    row.error
                    if durable_external
                    else "Server restarted - task interrupted"
                )
                updated_at = row.updated_at if durable_external else utc_now_naive()
                task = BackgroundTask(
                    id=row.id,
                    user_id=row.user_id,
                    organization_id=row.organization_id,
                    task_key=task_key,
                    module=row.module,
                    label=row.label,
                    status=status,
                    progress=row.progress,
                    checkpoint=json.loads(row.checkpoint) if row.checkpoint else {},
                    error=error,
                    created_at=row.created_at,
                    updated_at=updated_at,
                )
                self._tasks[task.id] = task
                if not durable_external:
                    row.status = "interrupted"
                    row.error = error
                    row.updated_at = updated_at
                count += 1

            db.commit()
            if count:
                app_ctx().logger.info(
                    f"[TaskManager] Recovered {count} interrupted tasks from DB"
                )
        except OperationalError as e:
            db.rollback()
            if "no such table: background_tasks" in str(e).lower():
                app_ctx().logger.warning(
                    "[TaskManager] Recovery skipped: background_tasks table not available yet."
                )
            else:
                app_ctx().logger.error(f"[TaskManager] Recovery error: {e}")
        except Exception as e:
            db.rollback()
            app_ctx().logger.error(f"[TaskManager] Recovery error: {e}")
        finally:
            db.close()

        return count

    def _send_to_user(
        self,
        user_id: int,
        organization_id: Optional[int],
        message: dict,
    ) -> bool:
        user_id = to_required_int(user_id, "user_id")
        organization_id = to_optional_int(organization_id)
        ctx = app_ctx()
        registry = getattr(ctx, "connection_registry", None)
        if not registry:
            return False

        connections = registry.get_connections(user_id, organization_id)
        if not connections:
            bridge = getattr(ctx, "redis_task_bridge", None)
            if bridge:
                bridge.publish(user_id, message, organization_id)
                return True
            return False

        for bus, client_id in connections:
            try:
                bus.send(client_id, message)
            except Exception as e:
                app_ctx().logger.error(f"[TaskManager] Send error: {e}")

        return True

    def _notify_user(
        self,
        user_id: int,
        organization_id: Optional[int],
        task_id: str,
        notif_type: str,
        payload: dict,
        direct_message: Optional[dict] = None,
    ) -> None:
        if direct_message is None:
            from democrai.core.application.tasks.notification_queue import NotificationQueue

            nq = NotificationQueue()
            direct_message = nq._build_message(notif_type, task_id, payload)

        if not self._send_to_user(user_id, organization_id, direct_message):
            from democrai.core.application.tasks.notification_queue import NotificationQueue

            nq = NotificationQueue()
            nq.enqueue(user_id, task_id, notif_type, payload, organization_id)

    def _persist_task(self, task) -> None:
        db = self._get_db()
        try:
            from democrai.core.application.tasks.models import BackgroundTaskRecord

            row = db.get(BackgroundTaskRecord, task.id)
            if row:
                row.organization_id = task.organization_id
                row.task_key = task.task_key
                row.status = task.status
                row.progress = task.progress
                row.checkpoint = json.dumps(task.checkpoint) if task.checkpoint else None
                row.result = (
                    json.dumps(task.result, default=str)
                    if task.result is not None
                    else None
                )
                row.error = task.error
                row.updated_at = task.updated_at
            else:
                row = BackgroundTaskRecord(
                    id=task.id,
                    user_id=task.user_id,
                    organization_id=task.organization_id,
                    task_key=task.task_key,
                    module=task.module,
                    label=task.label,
                    status=task.status,
                    progress=task.progress,
                    checkpoint=json.dumps(task.checkpoint) if task.checkpoint else None,
                    result=(
                        json.dumps(task.result, default=str)
                        if task.result is not None
                        else None
                    ),
                    error=task.error,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                )
                db.add(row)
            db.commit()
        except Exception as e:
            db.rollback()
            app_ctx().logger.error(f"[TaskManager] Persist error for {task.id}: {e}")
        finally:
            db.close()

    def _get_db(self):
        ctx = app_ctx()
        if ctx.db:
            return ctx.db.get_session()
        from democrai.core.infrastructure.database import _default_SessionLocal

        return _default_SessionLocal()
