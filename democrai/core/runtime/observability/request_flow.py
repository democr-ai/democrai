from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List

from democrai.core.runtime.foundation.app import app_ctx


def _config_get(key: str, default: Any) -> Any:
    ctx = app_ctx()
    config = getattr(ctx, "config", None)
    if config is None:
        return default
    getter = getattr(config, "get", None)
    if not callable(getter):
        return default
    try:
        return getter(key, default)
    except Exception:
        return default


def request_flow_level() -> str:
    raw = os.getenv(
        "DEMOCRAI_REQUEST_FLOW_DEBUG",
        str(_config_get("debug.request_flow.level", "off")),
    )
    if raw is None:
        level = "off"
    else:
        level = str(raw).strip().lower()
    if level not in {"off", "summary", "verbose"}:
        return "off"
    return level


def _buffer_size() -> int:
    raw = os.getenv(
        "DEMOCRAI_REQUEST_FLOW_BUFFER_SIZE",
        str(_config_get("debug.request_flow.buffer_size", 200)),
    )
    try:
        return max(10, int(raw))
    except Exception:
        return 200


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= 160:
            return value
        return value[:157] + "..."
    if isinstance(value, (list, tuple, set)):
        return f"<{type(value).__name__} len={len(value)}>"
    if isinstance(value, dict):
        return f"<dict keys={sorted(str(k) for k in value.keys())[:8]}>"
    return repr(value)


def _sanitize_details(details: Dict[str, Any]) -> Dict[str, Any]:
    return {
        str(key): _sanitize_value(value)
        for key, value in details.items()
        if value is not None
    }


@dataclass
class RequestFlowEvent:
    step: str
    at_ms: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestFlowRecord:
    request_id: str
    request_kind: str
    started_at: float
    details: Dict[str, Any] = field(default_factory=dict)
    events: List[RequestFlowEvent] = field(default_factory=list)


class RequestFlowTracer:
    def __init__(self, *, buffer_size: int | None = None) -> None:
        self._lock = threading.Lock()
        self._active: Dict[str, RequestFlowRecord] = {}
        self._completed: Deque[Dict[str, Any]] = deque(maxlen=buffer_size or _buffer_size())

    def start(self, request_id: str, request_kind: str, **details: Any) -> None:
        if not request_id:
            return
        now = time.perf_counter()
        sanitized = _sanitize_details(details)
        with self._lock:
            record = RequestFlowRecord(
                request_id=request_id,
                request_kind=request_kind,
                started_at=now,
                details=sanitized,
            )
            self._active[request_id] = record
        self._maybe_log_verbose(request_id, request_kind, "request.received", sanitized)

    def step(self, request_id: str, step: str, **details: Any) -> None:
        if not request_id:
            return
        now = time.perf_counter()
        sanitized = _sanitize_details(details)
        with self._lock:
            record = self._active.get(request_id)
            if record is None:
                raw_request_kind = details.get("request_kind")
                request_kind = (
                    raw_request_kind.strip()
                    if isinstance(raw_request_kind, str) and raw_request_kind.strip()
                    else "unknown"
                )
                record = RequestFlowRecord(
                    request_id=request_id,
                    request_kind=request_kind,
                    started_at=now,
                )
                self._active[request_id] = record
            record.events.append(
                RequestFlowEvent(
                    step=step,
                    at_ms=(now - record.started_at) * 1000.0,
                    details=sanitized,
                )
            )
            record.details.update(
                {
                    key: value
                    for key, value in sanitized.items()
                    if key in {"message_type", "action_name", "module_name", "user", "organization_id", "response_count", "error", "outcome"}
                }
            )
        self._maybe_log_verbose(request_id, None, step, sanitized)

    def finish(self, request_id: str, *, outcome: str = "ok", **details: Any) -> Dict[str, Any] | None:
        if not request_id:
            return None
        now = time.perf_counter()
        sanitized = _sanitize_details(details)
        with self._lock:
            record = self._active.pop(request_id, None)
            if record is None:
                return None
            duration_ms = (now - record.started_at) * 1000.0
            summary = {
                "request_id": record.request_id,
                "request_kind": record.request_kind,
                "duration_ms": round(duration_ms, 2),
                "outcome": outcome,
                **record.details,
                **sanitized,
                "steps": [event.step for event in record.events],
                "events": [
                    {
                        "step": event.step,
                        "at_ms": round(event.at_ms, 2),
                        **({"details": event.details} if event.details else {}),
                    }
                    for event in record.events
                ],
            }
            self._completed.append(summary)
        self._maybe_log_summary(summary)
        return summary

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        limit = max(1, limit)
        with self._lock:
            items = list(self._completed)
        return items[-limit:]

    def get(self, request_id: str) -> Dict[str, Any] | None:
        with self._lock:
            for item in reversed(self._completed):
                if item.get("request_id") == request_id:
                    return dict(item)
        return None

    def _maybe_log_verbose(
        self,
        request_id: str,
        request_kind: str | None,
        step: str,
        details: Dict[str, Any],
    ) -> None:
        if request_flow_level() != "verbose":
            return
        logger = getattr(app_ctx(), "logger", None)
        if logger is None:
            return
        payload = " ".join(f"{key}={value}" for key, value in sorted(details.items()))
        prefix = f"[RequestFlow] req={request_id}"
        if request_kind:
            prefix += f" kind={request_kind}"
        message = f"{prefix} step={step}"
        if payload:
            message += f" {payload}"
        logger.info(message, "request_flow")

    def _maybe_log_summary(self, summary: Dict[str, Any]) -> None:
        level = request_flow_level()
        if level not in {"summary", "verbose"}:
            return
        logger = getattr(app_ctx(), "logger", None)
        if logger is None:
            return
        message = (
            f"[RequestFlow] req={summary.get('request_id')} "
            f"kind={summary.get('request_kind')} "
            f"outcome={summary.get('outcome')} "
            f"duration={summary.get('duration_ms')}ms "
            f"message_type={summary.get('message_type')} "
            f"action={summary.get('action_name')} "
            f"module={summary.get('module_name')} "
            f"user={summary.get('user')} "
            f"org={summary.get('organization_id')} "
            f"responses={summary.get('response_count')} "
            f"steps={','.join(summary.get('steps', []))}"
        )
        logger.info(message, "request_flow")


def get_request_flow_tracer() -> RequestFlowTracer:
    ctx = app_ctx()
    tracer = getattr(ctx, "request_flow_tracer", None)
    if tracer is None:
        tracer = RequestFlowTracer()
        ctx.request_flow_tracer = tracer
    return tracer


def start_request_flow(request_id: str, request_kind: str, **details: Any) -> None:
    get_request_flow_tracer().start(request_id, request_kind, **details)


def trace_request_step(request_id: str, step: str, **details: Any) -> None:
    get_request_flow_tracer().step(request_id, step, **details)


def finish_request_flow(request_id: str, *, outcome: str = "ok", **details: Any) -> Dict[str, Any] | None:
    return get_request_flow_tracer().finish(request_id, outcome=outcome, **details)


def recent_request_flows(limit: int = 20) -> List[Dict[str, Any]]:
    return get_request_flow_tracer().recent(limit=limit)
