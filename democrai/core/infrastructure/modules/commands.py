from __future__ import annotations

import asyncio
import inspect
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Dict, Optional

from democrai.core.infrastructure.modules.compat import next_cron_run
from democrai.core.infrastructure.modules.command_state_store import module_command_state_store
from democrai.core.infrastructure.modules.constants import (
    DEFAULT_LEASE_TTL_SECONDS,
    SCHEDULE_POLL_SECONDS,
)
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.registry import module_command_registry


def start_background_commands(module):
    if not module.is_active or module._background_tasks:
        return

    definitions = module_command_registry.get_all(module_name=module.name)
    for definition in definitions:
        module_command_state_store.ensure_registered(definition)
        if definition.lifecycle == "schedule":
            module._start_scheduled_command(definition)
        elif definition.lifecycle == "long_run":
            module._start_managed_command(
                definition,
                restart_on_exit=definition.restart_on_exit,
                run_once_after_completion=False,
            )
        elif definition.lifecycle == "single_run":
            module._start_managed_command(
                definition,
                restart_on_exit=False,
                run_once_after_completion=True,
            )

    if module._background_tasks:
        app_ctx().logger.debug(f"Started {len(module._background_tasks)} background tasks for module: {module.name}")


def state_for(module, definition):
    state = module._command_states.get(definition.name)
    if state is None:
        from democrai.core.infrastructure.modules import manager as manager_mod

        state = manager_mod.ModuleCommandRunState(name=definition.name, lifecycle=definition.lifecycle)
        module._command_states[definition.name] = state
    return state


def refresh_state(module, definition):
    snapshot = module_command_state_store.get(definition.name)
    state = module._state_for(definition)
    if snapshot is None:
        return state
    state.runs = snapshot.run_count
    state.last_started_at = snapshot.last_started_at
    state.last_finished_at = snapshot.last_finished_at
    state.last_status = snapshot.status
    state.last_error = snapshot.last_error
    state.next_run_at = snapshot.next_run_at
    return state


async def invoke_command(module, definition, *, stop_event: Optional[asyncio.Event] = None):
    from democrai.core.infrastructure.modules.runtime import get_module_runtime

    state = module._refresh_state(definition)
    state.last_status = "running"
    state.last_error = None

    try:
        kwargs: Dict[str, object] = {}
        for param_name in inspect.signature(definition.func).parameters:
            if param_name == "stop_event":
                continue
            elif param_name == "command_name":
                kwargs[param_name] = definition.name
            elif param_name == "module_name":
                kwargs[param_name] = module.name

        await get_module_runtime().invoke(
            module=module,
            operation="command",
            payload={
                "handler_module": definition.handler_module,
                "handler_name": definition.handler_name,
                "command_name": definition.name,
                "call_args": [],
                "call_kwargs": dict(kwargs),
                "include_stop_event": ("stop_event" in inspect.signature(definition.func).parameters),
            },
            session={},
            metadata={"mode": "module_command", "command_name": definition.name},
            persistent=definition.lifecycle == "long_run",
            reuse_key=(
                f"module:{module.name}:command:{definition.name}"
                if definition.lifecycle == "long_run"
                else f"module:{module.name}"
            ),
        )
        module._refresh_state(definition)
    except asyncio.CancelledError:
        state.last_status = "cancelled"
        raise
    except Exception as exc:
        state.last_status = "failed"
        state.last_error = str(exc)
        raise


def track_task(module, task: asyncio.Task) -> None:
    module._background_tasks.append(task)

    def _cleanup(done_task: asyncio.Task) -> None:
        with suppress(ValueError):
            module._background_tasks.remove(done_task)

    task.add_done_callback(_cleanup)


def start_managed_command(module, definition, *, restart_on_exit: bool, run_once_after_completion: bool) -> None:
    stop_event = asyncio.Event()
    module._stop_events[definition.name] = stop_event

    async def _runner() -> None:
        while True:
            acquired = module_command_state_store.try_acquire_lease(
                definition,
                owner=module.owner_id,
                lease_ttl_seconds=DEFAULT_LEASE_TTL_SECONDS,
                increment_run_count=True,
            )
            if not acquired:
                snapshot = module_command_state_store.get(definition.name)
                if run_once_after_completion and snapshot is not None and snapshot.run_count > 0 and snapshot.status == "completed":
                    module._refresh_state(definition)
                    return
                await asyncio.sleep(SCHEDULE_POLL_SECONDS)
                continue

            heartbeat_task = asyncio.create_task(module._lease_heartbeat(definition.name), name=f"{definition.name}.heartbeat")
            try:
                await module._invoke_command(definition, stop_event=stop_event)
                module_command_state_store.finish_run(definition.name, owner=module.owner_id, status="completed")
                module._refresh_state(definition)
                if not restart_on_exit:
                    return
                app_ctx().logger.warning(f"Long-running command '{definition.name}' exited; restarting in 1s")
            except asyncio.CancelledError:
                if acquired:
                    module_command_state_store.finish_run(definition.name, owner=module.owner_id, status="cancelled")
                    module._refresh_state(definition)
                raise
            except Exception as exc:
                if acquired:
                    module_command_state_store.finish_run(
                        definition.name,
                        owner=module.owner_id,
                        status="failed",
                        last_error=str(exc),
                    )
                    module._refresh_state(definition)
                app_ctx().logger.error(f"Module command '{definition.name}' failed: {exc}")
                if not restart_on_exit:
                    return
            finally:
                heartbeat_task.cancel()
            await asyncio.sleep(1)

    module._track_task(asyncio.create_task(_runner(), name=definition.name))


def start_scheduled_command(module, definition) -> None:
    async def _scheduler() -> None:
        while True:
            heartbeat_task: asyncio.Task | None = None
            acquired = False
            try:
                now = utc_now_naive()
                state = module._refresh_state(definition)
                next_run = state.next_run_at
                if next_run is None:
                    next_run = module._compute_next_run(definition, now)
                    module_command_state_store.set_next_run(definition.name, next_run)
                    state.next_run_at = next_run
                wait_seconds = max(0.0, (next_run - now).total_seconds())
                if wait_seconds > 0:
                    await asyncio.sleep(min(wait_seconds, 5.0))
                    continue

                acquired = module_command_state_store.try_acquire_lease(
                    definition,
                    owner=module.owner_id,
                    lease_ttl_seconds=DEFAULT_LEASE_TTL_SECONDS,
                    increment_run_count=True,
                )
                if not acquired:
                    await asyncio.sleep(SCHEDULE_POLL_SECONDS)
                    continue

                heartbeat_task = asyncio.create_task(module._lease_heartbeat(definition.name), name=f"{definition.name}.heartbeat")
                await module._invoke_command(definition)
                next_run = module._compute_next_run(definition, utc_now_naive())
                module_command_state_store.finish_run(
                    definition.name,
                    owner=module.owner_id,
                    status="completed",
                    next_run_at=next_run,
                )
                module._refresh_state(definition)
            except asyncio.CancelledError:
                if acquired:
                    module_command_state_store.finish_run(definition.name, owner=module.owner_id, status="cancelled")
                    module._refresh_state(definition)
                raise
            except Exception as exc:
                if acquired:
                    next_run = module._compute_next_run(definition, utc_now_naive())
                    module_command_state_store.finish_run(
                        definition.name,
                        owner=module.owner_id,
                        status="failed",
                        last_error=str(exc),
                        next_run_at=next_run,
                    )
                    module._refresh_state(definition)
                app_ctx().logger.error(f"Scheduled command '{definition.name}' failed: {exc}")
                await asyncio.sleep(1)
            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()

    module._track_task(asyncio.create_task(_scheduler(), name=definition.name))


def compute_next_run(module, definition, now: datetime) -> datetime:
    if definition.interval_seconds is not None:
        return now + timedelta(seconds=max(0.0, definition.interval_seconds))
    if definition.cron:
        return next_cron_run(definition.cron, now)
    raise ValueError(f"Scheduled command '{definition.name}' requires cron or interval_seconds")


async def lease_heartbeat(module, command_name: str) -> None:
    interval = max(1.0, DEFAULT_LEASE_TTL_SECONDS / 3.0)
    while True:
        await asyncio.sleep(interval)
        renewed = module_command_state_store.heartbeat(
            command_name,
            owner=module.owner_id,
            lease_ttl_seconds=DEFAULT_LEASE_TTL_SECONDS,
        )
        if not renewed:
            app_ctx().logger.warning(f"Lease heartbeat lost for module command '{command_name}'")
            return
