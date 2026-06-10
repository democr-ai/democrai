from __future__ import annotations

import asyncio
import contextlib
import contextvars
import inspect
import json
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from pydantic import BaseModel, Field

from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.timezone import utc_now_naive


_PIPELINE_CONTEXT: contextvars.ContextVar[
    "AIPipelineContext | None"
] = contextvars.ContextVar(
    "ai_pipeline_context",
    default=None,
)


class AiPipelineMessage(BaseModel):
    # Schema in evoluzione: rappresenta eventi intermedi della pipeline AI e verrà stabilizzato con i prossimi step di telemetry/UI.
    type: str
    pipeline_id: str
    current_pipeline_id: str
    parent_pipeline_id: str | None = None
    request_id: str
    root_method: str
    step_id: str | None = None
    name: str | None = None
    status: str | None = None
    duration_ms: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@dataclass
class AIPipelineContext:
    pipeline_id: str
    current_pipeline_id: str
    parent_pipeline_id: str | None
    request_id: str
    root_method: str
    provider: str | None = None
    engine: str | None = None
    engine_row_id: int | None = None
    model_registry_id: int | None = None
    model_name: str | None = None
    caller_module: str | None = None
    user_id: int | None = None
    organization_id: int | None = None
    session_id: str | None = None
    node_id: str | None = None
    on_message: Callable[[AiPipelineMessage], Any] | None = None
    selected_skills: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    _step_stack: list[str] = field(default_factory=list)


def current_ai_pipeline_context() -> AIPipelineContext | None:
    return _PIPELINE_CONTEXT.get()


def create_ai_pipeline_context(
    *,
    root_method: str,
    request_id: str | None = None,
    provider: str | None = None,
    engine: str | None = None,
    engine_row_id: int | None = None,
    model_registry_id: int | None = None,
    model_name: str | None = None,
    caller_module: str | None = None,
    metadata: dict[str, Any] | None = None,
    on_message: Callable[[AiPipelineMessage], Any] | None = None,
) -> AIPipelineContext:
    parent = current_ai_pipeline_context()
    request_meta = _request_metadata()
    resolved_metadata = parent.metadata.copy() if parent is not None else {}
    if isinstance(metadata, dict):
        resolved_metadata.update(metadata)
    resolved_request_id = (
        request_id
        or (parent.request_id if parent is not None else None)
        or request_meta.get("request_id")
        or uuid.uuid4().hex
    )
    current_pipeline_id = uuid.uuid4().hex
    return AIPipelineContext(
        pipeline_id=parent.pipeline_id if parent is not None else current_pipeline_id,
        current_pipeline_id=current_pipeline_id,
        parent_pipeline_id=(parent.current_pipeline_id if parent is not None else None),
        request_id=resolved_request_id,
        root_method=(parent.root_method if parent is not None else root_method),
        provider=provider,
        engine=engine,
        engine_row_id=to_optional_int(engine_row_id),
        model_registry_id=to_optional_int(model_registry_id),
        model_name=model_name,
        caller_module=(
            caller_module
            or (parent.caller_module if parent is not None else None)
            or request_meta.get("module_name")
        ),
        user_id=to_optional_int(request_meta.get("user_id")),
        organization_id=to_optional_int(request_meta.get("organization_id")),
        session_id=request_meta.get("session_id"),
        node_id=_runtime_node_id(),
        on_message=on_message or (parent.on_message if parent is not None else None),
        metadata=resolved_metadata,
    )


@contextlib.contextmanager
def ai_pipeline_context(context: AIPipelineContext):
    token = _PIPELINE_CONTEXT.set(context)
    try:
        yield context
    finally:
        _PIPELINE_CONTEXT.reset(token)


@contextlib.asynccontextmanager
async def ai_pipeline_step(
    *,
    type: str,
    name: str,
    input: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:

    from democrai.core.runtime.foundation.app import app_ctx

    context = current_ai_pipeline_context()
    if context is None:
        yield {}
        return
    step_id = uuid.uuid4().hex
    parent_step_id = context._step_stack[-1] if context._step_stack else None
    started_at = utc_now_naive()
    started = time.perf_counter()
    step: dict[str, Any] = {
        "step_id": step_id,
        "parent_step_id": parent_step_id,
        "type": type,
        "name": name,
        "input": _safe_json(input or {}),
        "output": {},
        "stats": {},
        "metadata": _safe_json(metadata or {}),
    }
    context._step_stack.append(step_id)
    step["_last_activity"] = started

    # watchdog_task = _start_ai_pipeline_step_watchdog(
    # context,
    # step_id=step_id,
    # type=step["type"],
    # name=step["name"],
    # started=started,
    # task=asyncio.current_task(),
    # step=step,
    # )
    await emit_ai_pipeline_message(
        {
            **_message_base(context),
            "type": f"{step['type']}.started",
            "step_id": step_id,
            "name": step["name"],
            "input": step["input"],
            "metadata": step["metadata"],
        }
    )
    error: BaseException | None = None
    cancelled = False
    try:
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.debug(f"[PIPELINE STEP] STARTING PIPELINE STEP {step["name"]}\n", name="PIPELINE_STEP")
        yield step
    except asyncio.CancelledError as exc:
        error = exc
        cancelled = True
        step["status"] = "cancelled"
        step["error"] = "request_cancelled"
        raise
    except Exception as exc:
        error = exc
        step["error"] = str(exc)
        raise
    finally:
        if context._step_stack and context._step_stack[-1] == step_id:
            context._step_stack.pop()
        status = (
            "cancelled"
            if cancelled
            else "error"
            if error is not None
            else step.get("status", "ok")
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        step_error = step.get("error") or (str(error) if error is not None else None)
        if status == "error":
            # Never let logging failures mask the original step error.
            logger = getattr(app_ctx(), "logger", None)
            if logger is not None:
                logger.error(f"[PIPELINE STEP] ERROR PIPELINE STEP {step["name"]} {step["type"]}: {error} {step_error}\n", name="PIPELINE_STEP")
            #_log_ai_pipeline_step_error(
                #context,
                #step_id=step_id,
                #type=step["type"],
                #name=step["name"],
                #error=error,
                #error_message=step_error,
            #)
        #if watchdog_task is not None:
            #watchdog_task.cancel()
            #with contextlib.suppress(asyncio.CancelledError):
                #await watchdog_task
        try:
            _record_step(
                context,
                step_id=step_id,
                parent_step_id=parent_step_id,
                type=step["type"],
                name=step["name"],
                status=status,
                started_at=started_at,
                duration_ms=duration_ms,
                input=step.get("input") if isinstance(step.get("input"), dict) else {},
                output=_safe_json(step.get("output") or {}),
                stats=_safe_json(step.get("stats") or {}),
                error=step_error,
                metadata={
                    **pipeline_usage_metadata(step_id),
                    **_safe_json(step.get("metadata") or {}),
                },
            )
        except Exception as exc:
            app_ctx().logger.error(f"[PIPELINE STEP] ERROR PIPELINE STEP RECORD {step["name"]} {step["type"]}: {exc}\n", name="PIPELINE_STEP")
            #_log_ai_pipeline_step_error(
                #context,
                #step_id=step_id,
                #type="observability.pipeline_step",
                #name="record_ai_model_pipeline_step",
                #error=exc,
                #error_message=str(exc),
            #)
            if error is None:
                raise
        await emit_ai_pipeline_message(
            {
                **_message_base(context),
                "type": (
                    f"{step['type']}.cancelled"
                    if cancelled
                    else f"{step['type']}.finished"
                    if error is None
                    else f"{step['type']}.failed"
                ),
                "step_id": step_id,
                "name": step["name"],
                "status": status,
                "duration_ms": duration_ms,
                "output": _safe_json(step.get("output") or {}),
                "stats": _safe_json(step.get("stats") or {}),
                "metadata": _safe_json(step.get("metadata") or {}),
                "error": step_error,
            }
        )


async def emit_ai_pipeline_event(
    *,
    type: str,
    name: str | None = None,
    payload: dict[str, Any] | None = None,
    status: str | None = None,
) -> None:
    context = current_ai_pipeline_context()
    if context is None:
        return
    message = {
        **_message_base(context),
        "type": type,
    }
    if name is not None:
        message["name"] = name
    if status is not None:
        message["status"] = status
    message.update(_safe_json(payload or {}))
    await emit_ai_pipeline_message(message)


async def emit_ai_pipeline_message(message: dict[str, Any]) -> None:
    context = current_ai_pipeline_context()
    if context is None:
        return
    payload = _safe_json(message)
    _print_dev_pipeline_message(payload)
    if context.on_message is None:
        return
    result = context.on_message(_ai_pipeline_message(payload))
    if inspect.isawaitable(result):
        await result


def pipeline_usage_metadata(step_id: str | None = None) -> dict[str, Any]:
    context = current_ai_pipeline_context()
    if context is None:
        return {}
    metadata = {
        **context.metadata,
        "pipeline_id": context.pipeline_id,
        "current_pipeline_id": context.current_pipeline_id,
        "parent_pipeline_id": context.parent_pipeline_id,
        "request_id": context.request_id,
    }
    resolved_step_id = step_id or (
        context._step_stack[-1] if context._step_stack else ""
    )
    if resolved_step_id:
        metadata["step_id"] = resolved_step_id
    return metadata


def _record_step(
    context: AIPipelineContext,
    *,
    step_id: str,
    parent_step_id: str | None,
    type: str,
    name: str,
    status: str,
    started_at: object,
    duration_ms: float,
    input: dict[str, Any],
    output: dict[str, Any],
    stats: dict[str, Any],
    error: str | None,
    metadata: dict[str, Any],
) -> None:
    from democrai.core.application.observability.service import observability_service

    event = observability_service.record_ai_model_pipeline_step(
        pipeline_id=context.pipeline_id,
        request_id=context.request_id,
        step_id=step_id,
        parent_step_id=parent_step_id,
        root_method=context.root_method,
        type=type,
        name=name,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        provider=context.provider,
        engine=context.engine,
        engine_row_id=context.engine_row_id,
        model_registry_id=context.model_registry_id,
        model_name=context.model_name,
        user_id=context.user_id,
        organization_id=context.organization_id,
        session_id=context.session_id,
        node_id=context.node_id,
        input=input,
        output=output,
        stats=stats,
        error=error,
        metadata=metadata,
    )
    if event is None:
        raise RuntimeError("ai_model_pipeline_step_not_persisted")


def _log_ai_pipeline_step_error(
    context: AIPipelineContext,
    *,
    step_id: str,
    type: str,
    name: str,
    error: BaseException | None,
    error_message: str | None,
) -> None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        error_type = (
            error.__class__.__name__ if error is not None else "pipeline_step_error"
        )
        logger = app_ctx().logger
        if logger is None:
            return
        logger.error(
            "[AI Pipeline] step failed "
            f"generator={type}:{name} error_type={error_type} "
            f"pipeline_id={context.pipeline_id} request_id={context.request_id} "
            f"step_id={step_id} error={error_message or error_type}",
            exc_info=sys.exc_info() if error is not None else None,
        )
    except Exception:
        pass


def mark_step_progress(step: Any, *, chunks: int | None = None) -> None:
    """Segna che lo step e' ancora vivo (un chunk e' appena passato).

    Serve al watchdog per distinguere un engine **piantato** (nessun chunk da
    secondi) da una generazione **degenere** del modello (chunk che continuano
    ad arrivare ma lo step supera la soglia). I loop di streaming la chiamano a
    ogni chunk; ``step`` e' il dict yieldato da :func:`ai_pipeline_step`.
    """
    if not isinstance(step, dict):
        return
    step["_last_activity"] = time.perf_counter()
    if chunks is not None:
        step["_chunks"] = chunks


def _start_ai_pipeline_step_watchdog(
    context: AIPipelineContext,
    *,
    step_id: str,
    type: str,
    name: str,
    started: float,
    task: asyncio.Task | None,
    step: dict[str, Any] | None = None,
) -> asyncio.Task | None:
    delay_seconds = _ai_pipeline_step_stall_seconds()
    if delay_seconds <= 0:
        return None

    async def _watchdog() -> None:
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        now = time.perf_counter()
        last_activity = (
            step.get("_last_activity", started) if isinstance(step, dict) else started
        )
        _log_ai_pipeline_step_stalled(
            context,
            step_id=step_id,
            type=type,
            name=name,
            elapsed_ms=(now - started) * 1000.0,
            idle_ms=(now - last_activity) * 1000.0,
            chunks=step.get("_chunks") if isinstance(step, dict) else None,
            task=task,
        )

    return asyncio.create_task(
        _watchdog(),
        name=f"ai-pipeline-step-watchdog:{step_id}",
    )


def _ai_pipeline_step_stall_seconds() -> float:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        config = getattr(app_ctx(), "config", None)
        if config is None:
            return 30.0
        value = config.get("ai.pipeline.step_stall_seconds", 30.0)
        seconds = float(value)
    except Exception:
        return 30.0
    return seconds if seconds > 0 else 0.0


def _log_ai_pipeline_step_stalled(
    context: AIPipelineContext,
    *,
    step_id: str,
    type: str,
    name: str,
    elapsed_ms: float,
    idle_ms: float,
    chunks: int | None,
    task: asyncio.Task | None,
) -> None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        logger = app_ctx().logger
        if logger is None:
            return
        # Le chiamate unary (generate_completion) tornano tutto in un colpo: non
        # hanno segnale di progresso, quindi a 30s sembrano sempre ferme anche se
        # stanno solo caricando il modello o generando a lungo. Non gridare al
        # lupo: per loro slow e hung sono indistinguibili da qui.
        streaming = "stream" in str(name or "").lower()
        if not streaming:
            verdict = "unary_no_progress"
        elif chunks is not None and idle_ms < elapsed_ms * 0.5:
            # chunk che continuano ad arrivare => il modello sta ancora generando
            # (loop degenere / stop token mancato)
            verdict = "model_generating"
        else:
            # nessun chunk dall'inizio dello stream => engine piantato / hang IPC
            verdict = "no_output"
        message = (
            "[AI Pipeline] step stalled "
            f"generator={type}:{name} error_type=pipeline_step_stalled "
            f"verdict={verdict} "
            f"pipeline_id={context.pipeline_id} request_id={context.request_id} "
            f"step_id={step_id} engine={context.engine or context.provider or '-'} "
            f"model={context.model_name or '-'} "
            f"chunks={chunks if chunks is not None else '-'} "
            f"elapsed_ms={elapsed_ms:.1f} idle_ms={idle_ms:.1f}"
        )
        # Per le unary il dump dei task asyncio non dice nulla (lavoro nel thread,
        # task sempre idle): solo riga + thread stacks. Per lo streaming, dump pieno.
        if streaming:
            stack = _format_all_task_stacks(task)
            if stack:
                message = f"{message}\n{stack}"
        thread_stack = _format_thread_stacks()
        if thread_stack:
            message = f"{message}\n{thread_stack}"
        logger.error(message)
    except Exception:
        pass


_STACK_TASK_LIMIT = 12
_AI_STACK_MARKERS = ("/ai/engine/", "/ai/orchestrator", "engines/", "/ai/security/")


def _task_stack_lines(task: asyncio.Task, *, frame_limit: int) -> list[str]:
    frames = task.get_stack(limit=frame_limit)
    out: list[str] = []
    for frame in frames:
        out.extend(traceback.format_stack(frame, limit=1))
    return out


def _format_all_task_stacks(captured: asyncio.Task | None) -> str:
    """Dump dello stack del task catturato + di tutti i task vivi che toccano
    il codice AI engine.

    Il task catturato e' quello dello scheduler, spesso fermo su
    ``await self._executor(job)``: da solo non dice nulla. La generazione vera
    e l'eventuale hang stanno in altri task (batch worker, bridge IPC): li
    cerchiamo tra ``asyncio.all_tasks()`` filtrando per percorso del frame.
    """
    sections: list[str] = []
    seen: set[int] = set()

    def _emit(task: asyncio.Task, label: str, frame_limit: int) -> None:
        seen.add(id(task))
        lines = _task_stack_lines(task, frame_limit=frame_limit)
        header = f"-- {label} name={task.get_name()!r}"
        sections.append(
            header + "\n" + ("".join(lines) if lines else "  <no python frames>\n")
        )

    if captured is not None:
        _emit(captured, "captured (scheduler) task", 16)

    try:
        all_tasks = list(asyncio.all_tasks())
    except RuntimeError:
        all_tasks = []
    matched = 0
    for task in all_tasks:
        if id(task) in seen or task.done():
            continue
        lines = _task_stack_lines(task, frame_limit=20)
        if not any(marker in line for line in lines for marker in _AI_STACK_MARKERS):
            continue
        _emit(task, "live AI task", 20)
        matched += 1
        if matched >= _STACK_TASK_LIMIT:
            break

    if not sections:
        return ""
    return "Stack for stalled AI pipeline task(s):\n" + "\n".join(sections)


def _format_thread_stacks() -> str:
    """Dump degli stack dei **thread**, che ``asyncio.all_tasks()`` non vede.

    Le chiamate engine unary girano in un thread via ``asyncio.to_thread``: se
    l'hang e' li', i task asyncio mostrano solo l'event loop fermo. Qui si vede
    *dove* e' parcheggiato il thread: ``socket``/``httpx`` => sta aspettando il
    server esterno (Ollama); codice nostro / lock / coda => e' l'applicativo.
    Si saltano i worker idle del thread-pool (in attesa di lavoro).
    """
    import threading

    try:
        frames = sys._current_frames()
    except Exception:
        return ""
    names = {t.ident: t.name for t in threading.enumerate()}
    main_ident = threading.main_thread().ident
    sections: list[str] = []
    count = 0
    for ident, frame in frames.items():
        if ident == main_ident:
            continue  # event loop: gia' coperto dal dump dei task
        text = "".join(traceback.format_stack(frame, limit=14))
        if "concurrent/futures/thread.py" in text and "_work_queue.get" in text:
            continue  # worker del pool in idle
        name = names.get(ident, str(ident))
        sections.append(f"-- thread name={name!r} id={ident}\n{text}")
        count += 1
        if count >= _STACK_TASK_LIMIT:
            break
    if not sections:
        return ""
    return "Thread stacks (fuori dal radar asyncio):\n" + "\n".join(sections)


def _message_base(context: AIPipelineContext) -> dict[str, Any]:
    return {
        "pipeline_id": context.pipeline_id,
        "current_pipeline_id": context.current_pipeline_id,
        "parent_pipeline_id": context.parent_pipeline_id,
        "request_id": context.request_id,
        "root_method": context.root_method,
    }


def _print_dev_pipeline_message(payload: dict[str, Any]) -> None:
    if not _dev_pipeline_debug_enabled():
        return
    event_type = payload.get("type") or ""
    name = payload.get("name") or ""
    status = payload.get("status") or ""
    step_id = payload.get("step_id") or ""
    current_pipeline_id = payload.get("current_pipeline_id") or ""
    parent_pipeline_id = payload.get("parent_pipeline_id") or ""
    details = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "type",
            "pipeline_id",
            "current_pipeline_id",
            "parent_pipeline_id",
            "request_id",
            "root_method",
            "step_id",
            "name",
            "status",
            "duration_ms",
        }
        and value not in (None, "", {}, [])
    }
    parts = [event_type]
    if name:
        parts.append(name)
    if status:
        parts.append(f"status={status}")
    if step_id:
        parts.append(f"step={step_id[:8]}")
    if current_pipeline_id:
        parts.append(f"pipe={current_pipeline_id[:8]}")
    if parent_pipeline_id:
        parts.append(f"parent={parent_pipeline_id[:8]}")
    duration_ms = payload.get("duration_ms")
    if duration_ms not in (None, ""):
        try:
            parts.append(f"{float(duration_ms):.1f}ms")
        except (TypeError, ValueError):
            parts.append(f"duration={duration_ms}")
    if details:
        parts.append(_compact_json(details))
    # print("[AI_PIPELINE] " + " | ".join(parts), flush=True)


def _dev_pipeline_debug_enabled() -> bool:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        return app_ctx().dev
    except Exception:
        return False


def _compact_json(value: Any, *, max_chars: int = 2000) -> str:
    try:
        text = json.dumps(_safe_json(value), ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...<truncated>"


def _ai_pipeline_message(payload: dict[str, Any]) -> AiPipelineMessage:
    reserved = {
        "type",
        "pipeline_id",
        "current_pipeline_id",
        "parent_pipeline_id",
        "request_id",
        "root_method",
        "step_id",
        "name",
        "status",
        "duration_ms",
    }
    return AiPipelineMessage(
        type=payload["type"],
        pipeline_id=payload["pipeline_id"],
        current_pipeline_id=payload["current_pipeline_id"],
        parent_pipeline_id=payload.get("parent_pipeline_id"),
        request_id=payload["request_id"],
        root_method=payload["root_method"],
        step_id=payload.get("step_id"),
        name=payload.get("name"),
        status=payload.get("status"),
        duration_ms=payload.get("duration_ms"),
        payload={key: value for key, value in payload.items() if key not in reserved},
    )


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _safe_json(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _request_metadata() -> dict[str, Any]:
    try:
        from democrai.core.runtime.foundation.app import req_ctx

        ctx = req_ctx()
    except Exception:
        return {}
    return {
        "request_id": ctx.request_id,
        "user_id": ctx.user,
        "organization_id": ctx.organization_id,
        "session_id": ctx.session_key,
        "module_name": ctx.module_name or "core",
    }


def _runtime_node_id() -> str | None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        ctx = app_ctx()
        configured = ctx.node_id
        if configured:
            return configured
        cfg = ctx.config
        if cfg is not None:
            configured = cfg.get("network.node_id", "")
            if configured:
                return configured
    except Exception:
        return None
    return None
