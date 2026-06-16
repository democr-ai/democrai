from __future__ import annotations

import asyncio
import json
import threading
import traceback
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_

from democrai.core.infrastructure.ai.engine.invocation.config import (
    EngineInvocationRuntimeConfig,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.config import (
    ENGINE_INVOCATION_QUEUE_NOTIFY_CHANNEL,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.errors import (
    classify_error_retryable,
    error_retry_after_seconds,
    is_node_capacity_error,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.infrastructure.ai.engine.response.factory import (
    resolve_engine_response_stream,
)
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream
from democrai.core.infrastructure.ai.engine.response.writer import (
    EngineResponseStreamWriter,
)
from democrai.core.application.ai.engine.orchestrator.executor import (
    EngineJobResolverRequest,
)
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import app_ctx

from democrai.core.infrastructure.ai.engine.invocation.transports.queue import (
    CONTROL_INVOKE_ENGINE_ACTION,
    CONTROL_INVOKE_ENGINE_RUNTIME,
    CONTROL_REFRESH_REGISTRIES,
    CONTROL_SELECTOR_TYPE,
    CONTROL_STOP_ENGINE,
    CONTROL_SYNC_ACTIVE_ENGINES,
    CONTROL_UNLOAD_MODEL,
)


_CLAIM_PAGE_SIZE = 16


class _QueueJobContext:
    """gRPC-context stand-in: only cancellation matters for queue jobs."""

    def __init__(self) -> None:
        self._cancelled = False
        self.lease_lost = False

    def cancelled(self) -> bool:
        return self._cancelled

    def set_cancelled(self) -> None:
        self._cancelled = True

    def mark_lease_lost(self) -> None:
        # Another node reclaimed the row: this run is a zombie and must stop
        # touching both the queue row and the response stream.
        self.lease_lost = True
        self._cancelled = True

    def time_remaining(self) -> None:
        return None


def _request_from_row(
    row: dict[str, Any],
    *,
    allow_swap_prompt: bool,
    target: dict[str, Any] | None = None,
) -> EngineJobResolverRequest:
    objective = str(row.get("objective") or "")
    selector_type = str(row["selector_type"])
    model_registry_id = int(row.get("model_registry_id") or 0)
    target_model_registry_id = int((target or {}).get("model_registry_id") or 0)
    if target_model_registry_id > 0 and selector_type in {"objective", "capability"}:
        selector_type = "model_registry_id"
        model_registry_id = target_model_registry_id
    return EngineJobResolverRequest(
        request_id=str(row["id"]),
        selector_type=selector_type,
        model_registry_id=model_registry_id,
        objective=objective,
        capability=objective,
        capabilities_json=str(row.get("capabilities_json") or "[]"),
        prefer_local=row.get("prefer_local"),
        confirm_swap=bool(row.get("confirm_swap")),
        method=str(row["method"]),
        payload_json=str(row.get("payload_json") or "{}"),
        request_context_json=str(row.get("request_context_json") or "{}"),
        security_context_json=str(row.get("security_context_json") or "{}"),
        allow_swap_prompt=allow_swap_prompt,
    )


class EngineQueueClaimWorker:
    """Pulls engine invocations from the shared DB queue and executes them
    through the in-process orchestrator service machinery (same registry,
    scheduler and per-engine concurrency as the gRPC path).

    Wake-up is LISTEN/NOTIFY-driven on postgres with the poll interval as a
    failsafe only.
    """

    def __init__(
        self,
        *,
        node_id: str,
        service: Any,
        store: EngineInvocationQueueStore | None = None,
        response_stream: EngineResponseStream | Any | None = None,
        placement: Any | None = None,
    ) -> None:
        config = app_ctx().config
        self._node_id = node_id
        self._service = service
        self._store = store or EngineInvocationQueueStore()
        self._response_stream = resolve_engine_response_stream(response_stream)
        self._placement = placement
        runtime_config = EngineInvocationRuntimeConfig.load(config)
        self._poll_seconds = runtime_config.queue_claim_poll_seconds
        self._lease_seconds = runtime_config.queue_lease_seconds
        self._max_attempts = runtime_config.queue_max_attempts
        self._keepalive_seconds = runtime_config.queue_keepalive_seconds
        self._active_threshold_seconds = (
            runtime_config.node_state_active_threshold_seconds
        )
        self._wake = asyncio.Event()
        self._listener_stop = threading.Event()
        self._tasks: set[asyncio.Task] = set()
        self._engine_in_flight: dict[int, int] = {}
        self._in_flight_lock = threading.Lock()

    # ----- response stream / writer --------------------------------------

    def _writer(self, row: dict[str, Any]) -> EngineResponseStreamWriter:
        return EngineResponseStreamWriter(
            self._response_stream,
            str(row["response_stream_key"]),
            node_id=self._node_id,
        )

    # ----- capacity -------------------------------------------------------

    @staticmethod
    def _engine_capacity_limit(engine_row_id: int) -> int:
        from democrai.core.application.ai.engine.config_access import (
            get_engine_runtime_config,
        )

        config = get_engine_runtime_config(engine_row_id=engine_row_id) or {}
        if not bool(config.get("concurrency_enabled", False)):
            return 1
        return max(1, int(config.get("concurrency_limit", 1) or 1))

    def _predict_target(self, row: dict[str, Any]) -> dict[str, Any]:
        """Resolve which engine/model would serve this row (no side effects)."""
        from democrai.core.application.ai.orchestrator import model_orchestrator

        selector_type = str(row["selector_type"])
        if selector_type == "model_registry_id":
            model = model_orchestrator.get_model_by_registry_id(
                int(row.get("model_registry_id") or 0)
            )
        else:
            capabilities = json.loads(str(row.get("capabilities_json") or "[]"))
            model = model_orchestrator.get_model_for_objective(
                str(row.get("objective") or ""),
                required_capabilities=[item for item in capabilities if item],
                prefer_local=row.get("prefer_local"),
            )
        if model is None:
            raise RuntimeError(
                f"engine_orchestrator_no_model_for_selector:{selector_type}"
            )
        engine = getattr(model, "engine", None)
        return {
            "engine_row_id": int(getattr(engine, "id", 0) or 0),
            "engine_id": str(getattr(engine, "provider", "") or ""),
            "model_registry_id": int(getattr(model, "id", 0) or 0),
        }

    def _load_installed_engines(self) -> tuple[frozenset[str], frozenset[str]]:
        """One snapshot per tick of active engine installs.

        This node counts as active because this worker is running. Other nodes
        count only when their orchestrator heartbeat is fresh.
        """
        from democrai.core.infrastructure.database.models import (
            EngineNodeInstallRegistry,
            RuntimeNodeRegistry,
        )

        cutoff = utc_now_naive() - timedelta(
            seconds=max(0.0, float(self._active_threshold_seconds))
        )
        with SessionLocal() as session:
            rows = (
                session.query(
                    EngineNodeInstallRegistry.engine_id,
                    EngineNodeInstallRegistry.node_id,
                )
                .outerjoin(
                    RuntimeNodeRegistry,
                    RuntimeNodeRegistry.node_id == EngineNodeInstallRegistry.node_id,
                )
                .filter(EngineNodeInstallRegistry.status == "installed")
                .filter(
                    or_(
                        EngineNodeInstallRegistry.node_id == self._node_id,
                        and_(
                            RuntimeNodeRegistry.status == "active",
                            RuntimeNodeRegistry.orchestrator_last_seen_at.isnot(
                                None
                            ),
                            RuntimeNodeRegistry.orchestrator_last_seen_at >= cutoff,
                        ),
                    )
                )
                .all()
            )
        registered = frozenset(str(row[0]) for row in rows)
        mine = frozenset(
            str(row[0]) for row in rows if str(row[1]) == self._node_id
        )
        return registered, mine

    def _engine_install_state(
        self,
        engine_id: str,
        installed: tuple[frozenset[str], frozenset[str]] | None = None,
    ) -> str:
        """Return local|remote|missing for the target engine install state."""
        if not engine_id:
            return "local"
        if installed is None:
            installed = self._load_installed_engines()
        registered, mine = installed
        if engine_id not in registered:
            return "missing"
        if engine_id in mine:
            return "local"
        return "remote"

    def _engine_installed_locally(
        self,
        engine_id: str,
        installed: tuple[frozenset[str], frozenset[str]] | None = None,
    ) -> bool:
        return self._engine_install_state(engine_id, installed) == "local"

    def _has_engine_capacity(
        self,
        engine_row_id: int,
        *,
        reserved: dict[int, int] | None = None,
    ) -> bool:
        limit = self._engine_capacity_limit(engine_row_id)
        with self._in_flight_lock:
            in_flight = self._engine_in_flight.get(engine_row_id, 0)
        reserved_count = int((reserved or {}).get(engine_row_id, 0))
        return in_flight + reserved_count < limit

    def _track_engine(self, engine_row_id: int, delta: int) -> None:
        with self._in_flight_lock:
            current = self._engine_in_flight.get(engine_row_id, 0) + delta
            if current <= 0:
                self._engine_in_flight.pop(engine_row_id, None)
            else:
                self._engine_in_flight[engine_row_id] = current

    # ----- main loop ------------------------------------------------------

    async def run_until_stopped(self, stop_event: asyncio.Event) -> None:
        logger = getattr(app_ctx(), "logger", None)
        # Captured here, on the worker's loop: the listener thread must not
        # resolve a loop itself (it would get a fresh non-running one).
        loop = asyncio.get_running_loop()
        listener = asyncio.create_task(
            asyncio.to_thread(self._listen_notifications, loop),
            name="engine-queue-queue-listener",
        )
        try:
            while not stop_event.is_set():
                drain_more = False
                try:
                    drain_more = await self._tick()
                except Exception as exc:
                    if logger is not None:
                        logger.warning(
                            f"[Engine] claim tick failed: {exc}"
                        )
                if drain_more:
                    continue
                self._wake.clear()
                wake_task = asyncio.create_task(self._wake.wait())
                stop_task = asyncio.create_task(stop_event.wait())
                done, pending = await asyncio.wait(
                    {wake_task, stop_task},
                    timeout=self._poll_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
        finally:
            self._listener_stop.set()
            listener.cancel()
            try:
                await listener
            except (asyncio.CancelledError, Exception):
                pass
            for task in list(self._tasks):
                task.cancel()
            for task in list(self._tasks):
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            try:
                await self._response_stream.aclose()
            except Exception:
                pass

    def _listen_notifications(self, loop: asyncio.AbstractEventLoop) -> None:
        """Blocking LISTEN loop on a dedicated connection (postgres only).

        Failure here degrades to the poll failsafe — logged loudly, never
        silent."""
        logger = getattr(app_ctx(), "logger", None)
        try:
            engine = SessionLocal().get_bind()
            if engine.dialect.name != "postgresql":
                return
        except Exception:
            return
        try:
            import select as select_module

            raw = engine.raw_connection()
            try:
                connection = raw.driver_connection
                connection.autocommit = True
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"LISTEN {ENGINE_INVOCATION_QUEUE_NOTIFY_CHANNEL}"
                    )
                while not self._listener_stop.is_set():
                    ready = select_module.select([connection], [], [], 1.0)
                    if not ready[0]:
                        continue
                    connection.poll()
                    if connection.notifies:
                        connection.notifies.clear()
                        loop.call_soon_threadsafe(self._wake.set)
            finally:
                raw.close()
        except Exception as exc:
            if logger is not None:
                logger.warning(
                    "[Engine] LISTEN/NOTIFY unavailable, claim falls "
                    f"back to {self._poll_seconds}s polling: {exc}"
                )

    async def _tick(self) -> bool:
        views = None
        if self._placement is not None:
            views = await asyncio.to_thread(self._placement.load_views)
        installed = await asyncio.to_thread(self._load_installed_engines)
        score_cache: dict[Any, int | None] = {}
        reserved_engines: dict[int, int] = {}
        offset = 0
        while True:
            rows = await asyncio.to_thread(
                self._store.peek_claimable,
                limit=_CLAIM_PAGE_SIZE,
                offset=offset,
            )
            if not rows:
                return False
            to_claim: list[dict[str, Any]] = []
            to_fail: list[tuple[dict[str, Any], str]] = []
            targets: dict[str, dict[str, Any]] = {}
            for row in rows:
                decision = await self._decide(
                    row,
                    views=views,
                    score_cache=score_cache,
                    installed_engines=installed,
                    reserved_engines=reserved_engines,
                )
                if decision == "claim":
                    to_claim.append(row)
                    target = row.get("_predicted_target") or {}
                    targets[str(row["id"])] = target
                    engine_row_id = int(target.get("engine_row_id") or 0)
                    if engine_row_id:
                        reserved_engines[engine_row_id] = (
                            reserved_engines.get(engine_row_id, 0) + 1
                        )
                elif decision == "fail_missing_engine_install":
                    target = row.get("_predicted_target") or {}
                    engine_id = str(target.get("engine_id") or "")
                    to_fail.append(
                        (
                            row,
                            f"engine_not_installed_on_any_node:{engine_id}",
                        )
                    )
            if to_fail:
                for row, error in to_fail:
                    await self._fail_unclaimable_row(row, error)
                return len(rows) == _CLAIM_PAGE_SIZE
            if to_claim:
                await self._claim_rows(to_claim, targets)
                return len(rows) == _CLAIM_PAGE_SIZE
            if len(rows) < _CLAIM_PAGE_SIZE:
                return False
            offset += _CLAIM_PAGE_SIZE

    async def _claim_rows(
        self,
        rows: list[dict[str, Any]],
        targets: dict[str, dict[str, Any]],
    ) -> None:
        claimed = await asyncio.to_thread(
            self._store.claim,
            [row["id"] for row in rows],
            owner=self._node_id,
            lease_seconds=self._lease_seconds,
        )
        for row in claimed:
            target = targets.get(str(row["id"]), {})
            engine_row_id = int(target.get("engine_row_id") or 0)
            if engine_row_id:
                self._track_engine(engine_row_id, 1)
            task = asyncio.create_task(
                self._execute_row(
                    row,
                    engine_row_id=engine_row_id,
                    target=target,
                ),
                name=f"engine-queue-claim:{row['id']}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _fail_unclaimable_row(self, row: dict[str, Any], error: str) -> None:
        request_id = str(row["id"])
        status = await asyncio.to_thread(
            self._store.fail,
            request_id,
            error=error,
            retriable=False,
            max_attempts=self._max_attempts,
            owner=None,
        )
        if status != "dead_letter":
            return
        try:
            await self._writer(row).error(error)
        except Exception:
            return

    async def _decide(
        self,
        row: dict[str, Any],
        *,
        views: list[Any] | None = None,
        score_cache: dict[Any, int | None] | None = None,
        installed_engines: tuple[frozenset[str], frozenset[str]] | None = None,
        reserved_engines: dict[int, int] | None = None,
    ) -> str:
        if row.get("requires_origin_hitl") and row.get("origin_node_id") != self._node_id:
            return "skip"
        if row.get("selector_type") == CONTROL_SELECTOR_TYPE:
            return self._decide_control(row)
        if self._service.has_running_job(str(row["id"])):
            # This node is still running this request (slow run whose lease
            # expired): re-claiming here would attach a second consumer to
            # the live job. Let the run renew its lease or another node take
            # over and kill it through the lease-lost path.
            return "skip"
        try:
            target = await asyncio.to_thread(self._predict_target, row)
        except Exception:
            # Unresolvable selector: shared registry, so it fails identically
            # everywhere — claim it and let execution dead-letter with the
            # real error instead of leaving the row pending forever.
            row["_predicted_target"] = {}
            return "claim"
        row["_predicted_target"] = target
        engine_row_id = int(target.get("engine_row_id") or 0)
        engine_id = str(target.get("engine_id") or "")
        install_state = self._engine_install_state(engine_id, installed_engines)
        if install_state == "missing":
            return "fail_missing_engine_install"
        if install_state == "remote":
            return "skip"
        if engine_row_id and not self._has_engine_capacity(
            engine_row_id, reserved=reserved_engines
        ):
            return "skip"
        if self._placement is not None:
            should_claim = await asyncio.to_thread(
                self._placement.should_claim,
                row,
                target,
                views,
                score_cache,
            )
            if not should_claim:
                return "skip"
        return "claim"

    def _decide_control(self, row: dict[str, Any]) -> str:
        payload = self._row_payload(row)
        target_node_id = str(payload.get("_target_node_id") or "")
        if target_node_id and target_node_id != self._node_id:
            return "skip"
        return "claim"

    # ----- execution ------------------------------------------------------

    async def _execute_row(
        self,
        row: dict[str, Any],
        *,
        engine_row_id: int,
        target: dict[str, Any] | None = None,
    ) -> None:
        logger = getattr(app_ctx(), "logger", None)
        writer = self._writer(row)
        request_id = str(row["id"])
        context = _QueueJobContext()
        try:
            if row.get("cancel_requested"):
                await asyncio.to_thread(
                    self._store.mark_cancelled,
                    request_id,
                    reason="engine_orchestrator_cancelled",
                    owner=self._node_id,
                )
                await writer.error("engine_orchestrator_cancelled")
                return
            if row.get("response_mode") == "stream" and row.get("first_chunk_at"):
                # Partial output was already delivered by a previous attempt:
                # a re-run would duplicate tokens, so this is terminal.
                status = await asyncio.to_thread(
                    self._store.fail,
                    request_id,
                    owner=self._node_id,
                    error="engine_orchestrator_stream_interrupted",
                    retriable=False,
                    max_attempts=self._max_attempts,
                )
                if status == "dead_letter":
                    await writer.error("engine_orchestrator_stream_interrupted")
                return
            if row.get("selector_type") == CONTROL_SELECTOR_TYPE:
                await self._run_control_row(row, writer, context)
                return
            await writer.accepted(attempt=int(row.get("attempts") or 0))
            await self._run_job(row, writer, context, target=target)
        except asyncio.CancelledError:
            if context.lease_lost:
                # Another node owns the row (and the stream) now: vanish.
                return
            if await asyncio.to_thread(self._store.cancel_requested, request_id):
                # User cancel, not node shutdown: terminal cancelled state.
                await asyncio.to_thread(
                    self._store.mark_cancelled,
                    request_id,
                    reason="engine_orchestrator_cancelled",
                    owner=self._node_id,
                )
                await writer.error("engine_orchestrator_cancelled")
                return
            await self._fail_row(
                row,
                writer,
                error="engine_orchestrator_node_shutdown",
                forced_retriable=True,
                emitted_first_chunk=bool(row.get("_emitted_first_chunk")),
            )
            raise
        except Exception as exc:
            if logger is not None:
                logger.warning(
                    f"[Engine] queue job {request_id} failed: {exc}"
                )
            await self._handle_failure(row, writer, exc)
        finally:
            if engine_row_id:
                self._track_engine(engine_row_id, -1)

    def _evict_stale_terminal_job(self, request_id: str) -> None:
        """Drop a finished job left in the registry by a previous attempt.

        get_or_create_job would otherwise hand back the terminal job
        (created=False): the old result/error would be replayed instead of
        re-executing, and streams would die on stream_already_attached.
        """
        self._service.evict_terminal_job(request_id)

    @staticmethod
    def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(str(row.get("payload_json") or "{}"))
        if not isinstance(payload, dict):
            raise RuntimeError("engine_orchestrator_control_payload_dict_required")
        return payload

    async def _run_control_row(
        self,
        row: dict[str, Any],
        writer: EngineResponseStreamWriter,
        context: _QueueJobContext,
    ) -> None:
        from democrai.core.runtime.foundation.app import request_context_scope

        request_id = str(row["id"])
        request_context = json.loads(str(row.get("request_context_json") or "{}"))
        ancillary = asyncio.create_task(
            self._lease_and_cancel_loop(request_id, context, writer),
            name=f"engine-queue-control-lease:{request_id}",
        )
        try:
            await writer.accepted(attempt=int(row.get("attempts") or 0))
            with request_context_scope(
                request_context if isinstance(request_context, dict) else {}
            ):
                result = await self._execute_control_row(row, context)
            if context.lease_lost:
                raise asyncio.CancelledError()
            await writer.result(result)
            await writer.end()
            await asyncio.to_thread(
                self._store.complete,
                request_id,
                owner=self._node_id,
                result_summary={"node_id": self._node_id},
            )
        finally:
            ancillary.cancel()
            try:
                await ancillary
            except (asyncio.CancelledError, Exception):
                pass

    async def _execute_control_row(
        self,
        row: dict[str, Any],
        context: _QueueJobContext,
    ) -> Any:
        del context
        method = str(row.get("method") or "")
        payload = self._row_payload(row)
        if method == CONTROL_REFRESH_REGISTRIES:
            from democrai.core.application.ai.engine.manifests import (
                sync_engine_manifests_to_registry,
            )

            await asyncio.to_thread(sync_engine_manifests_to_registry)
            return True
        if method == CONTROL_SYNC_ACTIVE_ENGINES:
            from democrai.core.application.ai.engine.runtime import get_engine_runtime

            await get_engine_runtime().sync_active_engines()
            return True
        if method == CONTROL_UNLOAD_MODEL:
            from democrai.core.application.ai.engine.runtime import get_engine_runtime

            model_registry_id = int(payload.get("model_registry_id") or 0)
            if model_registry_id <= 0:
                raise RuntimeError("engine_runtime_model_registry_id_required")
            return get_engine_runtime().unload_model(
                engine_row_id=int(payload.get("engine_registry_id") or 0),
                model_registry_id=model_registry_id,
            )
        if method == CONTROL_STOP_ENGINE:
            from democrai.core.application.ai.engine.runtime import get_engine_runtime

            get_engine_runtime().stop_engine(
                int(payload.get("engine_registry_id") or 0)
            )
            return True
        if method == CONTROL_INVOKE_ENGINE_ACTION:
            return await self._invoke_engine_action(payload)
        if method == CONTROL_INVOKE_ENGINE_RUNTIME:
            return await self._invoke_engine_runtime(payload)
        raise RuntimeError(f"engine_orchestrator_control_method_unknown:{method}")

    @staticmethod
    async def _invoke_engine_action(payload: dict[str, Any]) -> Any:
        method = str(payload.get("method") or "")
        if method not in {"list_available_models"}:
            raise RuntimeError(f"engine_action_method_not_allowed:{method}")
        from democrai.core.application.ai.engine.runtime.methods import (
            invoke_engine_method,
            run_engine_result,
        )
        from democrai.core.application.ai.engine.runtime.worker import (
            EngineWorkerSubject,
        )

        subject = EngineWorkerSubject(
            engine_id=str(payload.get("engine_id") or ""),
            config=payload.get("config") if isinstance(payload.get("config"), dict) else {},
        )
        try:
            return await asyncio.to_thread(
                lambda: run_engine_result(
                    invoke_engine_method(
                        subject,
                        method,
                        payload.get("payload")
                        if isinstance(payload.get("payload"), dict)
                        else {},
                    )
                )
            )
        finally:
            subject.close()

    @staticmethod
    async def _invoke_engine_runtime(payload: dict[str, Any]) -> Any:
        from democrai.core.application.ai.engine.runtime import get_engine_runtime

        model_registry_id = int(payload.get("model_registry_id") or 0)
        if model_registry_id <= 0:
            raise RuntimeError("engine_runtime_model_registry_id_required")
        return await asyncio.to_thread(
            get_engine_runtime().invoke,
            engine_row_id=int(payload.get("engine_registry_id") or 0),
            model_registry_id=model_registry_id,
            engine_id=str(payload.get("engine_id") or ""),
            config=payload.get("config") if isinstance(payload.get("config"), dict) else {},
            method=str(payload.get("method") or ""),
            payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        )

    async def _run_job(
        self,
        row: dict[str, Any],
        writer: EngineResponseStreamWriter,
        context: _QueueJobContext,
        *,
        target: dict[str, Any] | None = None,
    ) -> None:
        from democrai.core.runtime.foundation.app import request_context_scope

        request_id = str(row["id"])
        allow_swap_prompt = row.get("origin_node_id") == self._node_id
        request = _request_from_row(
            row,
            allow_swap_prompt=allow_swap_prompt,
            target=target,
        )
        request_context = json.loads(str(row.get("request_context_json") or "{}"))
        self._evict_stale_terminal_job(request_id)
        ancillary = asyncio.create_task(
            self._lease_and_cancel_loop(request_id, context, writer),
            name=f"engine-queue-lease:{request_id}",
        )
        try:
            with request_context_scope(
                request_context if isinstance(request_context, dict) else {}
            ):
                if row.get("response_mode") == "stream":
                    await self._run_stream_job(row, request, context, writer)
                else:
                    result = await self._service.invoke_request(request, context)
                    if context.lease_lost:
                        raise asyncio.CancelledError()
                    await writer.result(result)
                    await writer.end()
                    await asyncio.to_thread(
                        self._store.complete,
                        request_id,
                        owner=self._node_id,
                        result_summary={"node_id": self._node_id},
                    )
        finally:
            ancillary.cancel()
            try:
                await ancillary
            except (asyncio.CancelledError, Exception):
                pass

    async def _run_stream_job(
        self,
        row: dict[str, Any],
        request: EngineJobResolverRequest,
        context: _QueueJobContext,
        writer: EngineResponseStreamWriter,
    ) -> None:
        request_id = str(row["id"])
        emitted_first_chunk = False
        chunk_count = 0
        async for chunk in self._service.invoke_stream_request(request, context):
            if context.lease_lost:
                raise asyncio.CancelledError()
            kind = getattr(chunk, "kind", "")
            if kind == "chunk":
                await writer.chunk_raw(getattr(chunk, "chunk_json", "") or "null")
                if not emitted_first_chunk:
                    emitted_first_chunk = True
                    row["_emitted_first_chunk"] = True
                    await asyncio.to_thread(
                        self._store.mark_first_chunk,
                        request_id,
                        owner=self._node_id,
                    )
                chunk_count += 1
            elif kind == "message":
                await writer.message_raw(getattr(chunk, "chunk_json", "") or "null")
        if context.lease_lost:
            raise asyncio.CancelledError()
        await writer.end()
        await asyncio.to_thread(
            self._store.complete,
            request_id,
            owner=self._node_id,
            result_summary={"node_id": self._node_id, "chunks": chunk_count},
        )

    async def _lease_and_cancel_loop(
        self,
        request_id: str,
        context: _QueueJobContext,
        writer: EngineResponseStreamWriter,
    ) -> None:
        from democrai.core.application.ai.engine.runtime.requests import (
            cancel_runtime_request,
        )

        interval = max(0.5, min(self._lease_seconds / 3.0, self._keepalive_seconds))
        elapsed_since_keepalive = 0.0
        while True:
            await asyncio.sleep(interval)
            elapsed_since_keepalive += interval
            renewed, cancel_requested = await asyncio.to_thread(
                self._store.renew_lease_and_check_cancel,
                request_id,
                owner=self._node_id,
                lease_seconds=self._lease_seconds,
            )
            if not renewed:
                # The row is no longer ours (lease expired and reclaimed):
                # stop this run without touching row or stream.
                context.mark_lease_lost()
                self._service.cancel_job(
                    request_id, "engine_orchestrator_lease_lost"
                )
                try:
                    cancel_runtime_request(request_id)
                except Exception:
                    pass
                return
            if elapsed_since_keepalive >= self._keepalive_seconds:
                elapsed_since_keepalive = 0.0
                try:
                    await writer.keepalive()
                except Exception:
                    pass
            if cancel_requested and not context.cancelled():
                context.set_cancelled()
                self._service.cancel_job(
                    request_id, "engine_orchestrator_cancelled"
                )
                try:
                    cancel_runtime_request(request_id)
                except Exception:
                    pass

    async def _handle_failure(
        self,
        row: dict[str, Any],
        writer: EngineResponseStreamWriter,
        exc: Exception,
    ) -> None:
        request_id = str(row["id"])
        message = str(exc)
        if row.get("cancel_requested") or await asyncio.to_thread(
            self._store.cancel_requested, request_id
        ):
            await asyncio.to_thread(
                self._store.mark_cancelled,
                request_id,
                reason="engine_orchestrator_cancelled",
                owner=self._node_id,
            )
            await writer.error("engine_orchestrator_cancelled")
            return
        if is_node_capacity_error(message):
            # Serving here would need a resource swap this node cannot
            # confirm: hand the job to the origin node, where HITL works.
            await asyncio.to_thread(
                self._store.release,
                request_id,
                owner=self._node_id,
                defer_seconds=1.0,
                reason=message,
                requires_origin_hitl=True,
            )
            return
        await self._fail_row(
            row,
            writer,
            error=message,
            traceback_text=traceback.format_exc(),
            emitted_first_chunk=bool(row.get("_emitted_first_chunk")),
        )

    async def _fail_row(
        self,
        row: dict[str, Any],
        writer: EngineResponseStreamWriter,
        *,
        error: str,
        traceback_text: str = "",
        forced_retriable: bool | None = None,
        emitted_first_chunk: bool = False,
    ) -> None:
        request_id = str(row["id"])
        retriable = self._is_retriable(
            row,
            error=error,
            forced_retriable=forced_retriable,
            emitted_first_chunk=emitted_first_chunk,
        )
        status = await asyncio.to_thread(
            self._store.fail,
            request_id,
            owner=self._node_id,
            error=error,
            retriable=retriable,
            max_attempts=self._max_attempts,
            retry_after_seconds=error_retry_after_seconds(error),
        )
        if status in {"missing", "stale"}:
            # No owned row was settled: another owner may now control the
            # outcome, so this worker stays silent on the live stream.
            return
        if status == "failed":
            await writer.retry(
                attempt=int(row.get("attempts") or 0), error=error
            )
        else:
            await writer.error(error, traceback_text=traceback_text)

    def _is_retriable(
        self,
        row: dict[str, Any],
        *,
        error: str,
        forced_retriable: bool | None,
        emitted_first_chunk: bool,
    ) -> bool:
        if emitted_first_chunk:
            # Tokens already delivered: a retry would replay them.
            return False
        if forced_retriable is not None:
            return forced_retriable
        error_class = classify_error_retryable(error)
        if error_class is False:
            return False
        job = self._service.active_job(str(row["id"]))
        phase_retriable = getattr(job, "retriable", None) if job is not None else None
        if phase_retriable is False and row.get("response_mode") == "stream":
            return False
        if error_class is True:
            return True
        # Unknown error class: the durable queue with bounded attempts makes
        # retrying the safer default.
        return phase_retriable is not False
