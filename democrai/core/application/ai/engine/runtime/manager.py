from __future__ import annotations

import asyncio
import threading
from typing import Any

from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.dependencies.engine_env import (
    engine_env_context,
)
from democrai.core.application.ai.engine.runtime.events import begin_runtime_event
from democrai.core.application.ai.engine.runtime.access import (
    get_engine_access,
    get_engine_allowed_imports,
)
from democrai.core.application.ai.engine.runtime.environment import (
    runtime_config_public,
    runtime_config_signature,
    runtime_node_id,
    get_engine_runtime_env,
)
from democrai.core.application.ai.engine.runtime.handles import (
    EngineHandle,
    create_engine_handle,
)
from democrai.core.application.ai.engine.runtime.methods import (
    invoke_engine_method,
    run_engine_result,
)
from democrai.core.application.ai.engine.runtime.state import (
    active_engine_registry_rows,
    is_compile_failure,
    mark_engine_compile_failure,
)


_ENGINE_RUNTIME_LOCK = threading.Lock()


class EngineRuntime:
    def __init__(self) -> None:
        self._handles: dict[tuple[int, int], EngineHandle] = {}
        self._row_locks: dict[int, threading.Lock] = {}
        self._lock = threading.Lock()

    def _row_lock(self, engine_row_id: int) -> threading.Lock:
        with self._lock:
            return self._row_locks.setdefault(engine_row_id, threading.Lock())

    @staticmethod
    def _handle_key(*, engine_row_id: int, model_registry_id: int) -> tuple[int, int]:
        if model_registry_id <= 0:
            raise ValueError("engine_runtime_model_registry_id_required")
        return engine_row_id, model_registry_id

    def _has_matching_handle(
        self,
        *,
        engine_row_id: int,
        model_registry_id: int,
        engine_id: str,
        config: dict[str, Any],
    ) -> bool:
        key = self._handle_key(
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
        )
        with self._lock:
            handle = self._handles.get(key)
            return bool(
                handle is not None
                and handle.engine_id == engine_id
                and handle.config == config
            )

    @staticmethod
    def _runtime_guard(engine_id: str, config: dict[str, Any]):
        return process_guard_context(
            subject=engine_id,
            subject_kind="engine",
            access=get_engine_access(
                engine_id,
                "runtime",
                config=config,
            ),
            allowed_imports=get_engine_allowed_imports(
                engine_id,
                "runtime",
            ),
            allow_subprocess=True,
            allow_fork=True,
            include_network_access=False,
        )

    @staticmethod
    def _concurrency_enabled(config: dict[str, Any]) -> bool:
        return bool(config.get("concurrency_enabled", False))

    def _ensure_handle(
        self,
        *,
        engine_row_id: int,
        engine_id: str,
        config: dict[str, Any],
        model_registry_id: int,
    ) -> EngineHandle:
        key = self._handle_key(
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
        )
        with self._row_lock(engine_row_id):
            with self._lock:
                handle = self._handles.get(key)
                if (
                    handle is not None
                    and handle.engine_id == engine_id
                    and handle.config == config
                ):
                    return handle
                if handle is not None:
                    self._handles.pop(key, None)
            if handle is not None:
                handle.close()
            created = create_engine_handle(
                engine_id=engine_id,
                config=config,
                model_registry_id=model_registry_id,
            )
            with self._lock:
                self._handles[key] = created
            self._record_instance_running(
                engine_row_id=engine_row_id,
                model_registry_id=model_registry_id,
                handle=created,
            )
            return created

    @staticmethod
    def _record_instance_running(
        *, engine_row_id: int, model_registry_id: int, handle: EngineHandle
    ) -> None:
        from democrai.core.application.ai.engine.orchestrator.node_state import (
            record_instance_running,
        )

        process = getattr(handle.subject, "_process", None)
        record_instance_running(
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
            engine_id=handle.engine_id,
            model=str(handle.config.get("model") or ""),
            config_signature=runtime_config_signature(handle.config),
            pid=getattr(process, "pid", None),
        )

    @staticmethod
    def _record_instance_removed(
        *, engine_row_id: int, model_registry_id: int | None = None
    ) -> None:
        from democrai.core.application.ai.engine.orchestrator.node_state import (
            record_instance_removed,
        )

        record_instance_removed(
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
        )

    def ensure_running(
        self,
        *,
        engine_row_id: int,
        engine_id: str,
        config: dict[str, Any],
        model_registry_id: int,
    ) -> None:
        with self._runtime_guard(engine_id, config):
            using_existing = self._has_matching_handle(
                engine_row_id=engine_row_id,
                model_registry_id=model_registry_id,
                engine_id=engine_id,
                config=config,
            )
            event = begin_runtime_event(
                using_existing=using_existing,
                engine_row_id=engine_row_id,
                model_registry_id=model_registry_id,
                engine_id=engine_id,
                config=config,
            )
            try:
                self._ensure_handle(
                    engine_row_id=engine_row_id,
                    engine_id=engine_id,
                    config=config,
                    model_registry_id=model_registry_id,
                )
            except Exception as exc:
                event.finish(success=False, error=str(exc))
                raise
            event.finish(success=True)

    def invoke(
        self,
        *,
        engine_row_id: int,
        model_registry_id: int,
        engine_id: str,
        config: dict[str, Any],
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        with self._runtime_guard(engine_id, config):
            using_existing = self._has_matching_handle(
                engine_row_id=engine_row_id,
                model_registry_id=model_registry_id,
                engine_id=engine_id,
                config=config,
            )
            event = begin_runtime_event(
                using_existing=using_existing,
                engine_row_id=engine_row_id,
                model_registry_id=model_registry_id,
                engine_id=engine_id,
                config=config,
            )
            try:
                handle = self._ensure_handle(
                    engine_row_id=engine_row_id,
                    engine_id=engine_id,
                    config=config,
                    model_registry_id=model_registry_id,
                )
            except Exception as exc:
                event.finish(success=False, error=str(exc))
                raise
            event.finish(success=True)
            def _invoke() -> Any:
                try:
                    result = invoke_engine_method(handle.subject, method, payload)
                    return run_engine_result(result)
                except Exception as exc:
                    if is_compile_failure(exc):
                        mark_engine_compile_failure(engine_row_id)
                    raise

            if self._concurrency_enabled(config):
                return _invoke()

            with handle.lock:
                with engine_env_context(
                    engine_id,
                    env=get_engine_runtime_env(engine_id),
                ):
                    return _invoke()

    async def invoke_stream(
        self,
        *,
        engine_row_id: int,
        model_registry_id: int,
        engine_id: str,
        config: dict[str, Any],
        method: str,
        payload: dict[str, Any] | None = None,
    ):
        with self._runtime_guard(engine_id, config):
            using_existing = self._has_matching_handle(
                engine_row_id=engine_row_id,
                model_registry_id=model_registry_id,
                engine_id=engine_id,
                config=config,
            )
            event = begin_runtime_event(
                using_existing=using_existing,
                engine_row_id=engine_row_id,
                model_registry_id=model_registry_id,
                engine_id=engine_id,
                config=config,
            )
            try:
                handle = self._ensure_handle(
                    engine_row_id=engine_row_id,
                    engine_id=engine_id,
                    config=config,
                    model_registry_id=model_registry_id,
                )
            except Exception as exc:
                event.finish(success=False, error=str(exc))
                raise
            event.finish(success=True)
            if self._concurrency_enabled(config):
                try:
                    async for item in handle.subject.invoke_stream(method, payload):
                        yield item
                except Exception as exc:
                    if is_compile_failure(exc):
                        mark_engine_compile_failure(engine_row_id)
                    raise
                return

            await asyncio.to_thread(handle.lock.acquire)
            try:
                with engine_env_context(
                    engine_id,
                    env=get_engine_runtime_env(engine_id),
                ):
                    async for item in handle.subject.invoke_stream(method, payload):
                        yield item
            except Exception as exc:
                if is_compile_failure(exc):
                    mark_engine_compile_failure(engine_row_id)
                raise
            finally:
                handle.lock.release()

    def stop_engine(self, engine_row_id: int) -> None:
        with self._lock:
            handles = [
                self._handles.pop(key)
                for key in list(self._handles)
                if key[0] == engine_row_id
            ]
            self._row_locks.pop(engine_row_id, None)
        for handle in handles:
            handle.close()
        if handles:
            self._record_instance_removed(engine_row_id=engine_row_id)

    def unload_model(self, *, engine_row_id: int, model_registry_id: int) -> bool:
        key = self._handle_key(
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
        )
        with self._lock:
            handle = self._handles.pop(key, None)
            if not any(item_key[0] == engine_row_id for item_key in self._handles):
                self._row_locks.pop(engine_row_id, None)
        if handle is None:
            return False
        handle.close()
        self._record_instance_removed(
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
        )
        return True

    def cancel_request(self, *, engine_row_id: int, request_id: str) -> bool:
        with self._lock:
            handles = [
                handle
                for key, handle in self._handles.items()
                if key[0] == engine_row_id
            ]
        for handle in handles:
            if handle.subject.cancel(request_id):
                return True
        return False

    def shutdown(self) -> None:
        with self._lock:
            keys = list(self._handles)
            handles = list(self._handles.values())
            self._handles.clear()
            self._row_locks.clear()
        for handle in handles:
            handle.close()
        for engine_row_id, model_registry_id in keys:
            self._record_instance_removed(
                engine_row_id=engine_row_id,
                model_registry_id=model_registry_id,
            )

    def keys(self) -> list[str]:
        with self._lock:
            return [
                f"engine:{engine_row_id}:model:{model_registry_id}"
                for engine_row_id, model_registry_id in self._handles
            ]

    def active_instances(self) -> list[dict[str, Any]]:
        node_id = runtime_node_id()
        rows: list[dict[str, Any]] = []
        with self._lock:
            items = list(self._handles.items())
        for (engine_row_id, model_registry_id), handle in items:
            process = getattr(handle.subject, "_process", None)
            rows.append(
                {
                    "node_id": node_id,
                    "engine_row_id": engine_row_id,
                    "engine_id": handle.engine_id,
                    "model_registry_id": model_registry_id,
                    "model": handle.config.get("model") or "",
                    "model_path": handle.config.get("model_path") or "",
                    "config": runtime_config_public(handle.config),
                    "config_signature": runtime_config_signature(handle.config),
                    "pid": getattr(process, "pid", None),
                    "status": (
                        "running"
                        if process is not None and process.poll() is None
                        else "stopped"
                    ),
                }
            )
        return rows

    async def sync_active_engines(self) -> None:
        rows = active_engine_registry_rows()
        active_ids = {row.id for row in rows}
        with self._lock:
            active_engine_ids = {key[0] for key in self._handles}
        for engine_row_id in active_engine_ids:
            if engine_row_id not in active_ids:
                self.stop_engine(engine_row_id)


def get_engine_runtime() -> EngineRuntime:
    ctx = app_ctx()
    with _ENGINE_RUNTIME_LOCK:
        runtime = getattr(ctx, "engine_runtime", None)
        if runtime is None:
            runtime = EngineRuntime()
            ctx.engine_runtime = runtime
        return runtime
