from __future__ import annotations

import contextlib
import contextvars
import os
import time
import zlib
from dataclasses import dataclass, field
from typing import Dict, Iterator

from democrai.core.runtime.foundation.app import app_ctx


_current_profiler: contextvars.ContextVar["RequestProfiler | None"] = contextvars.ContextVar(
    "request_profiler", default=None
)


def _profile_enabled() -> bool:
    return os.getenv("DEMOCRAI_PROFILE_REQUESTS", "0") == "1"


def _profile_every() -> int:
    raw = os.getenv("DEMOCRAI_PROFILE_EVERY", "100")
    try:
        return max(1, int(raw))
    except ValueError:
        return 100


def _should_profile(request_id: str) -> bool:
    if not _profile_enabled():
        return False
    every = _profile_every()
    if every <= 1:
        return True
    return (zlib.crc32(request_id.encode("utf-8")) % every) == 0


@dataclass
class _ActiveSpan:
    name: str
    started_at: float
    child_ms: float = 0.0


@dataclass
class RequestProfiler:
    """
    Tracks execution time of various spans within a single request.

    The profiler records timing data for named spans and logs the total
    execution time upon completion if profiling is enabled.
    """
    request_id: str
    request_kind: str
    enabled: bool
    started_at: float = field(default_factory=time.perf_counter)
    spans_ms: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    _stack: list[_ActiveSpan] = field(default_factory=list)

    @contextlib.contextmanager
    def span(self, name: str) -> Iterator[None]:
        """
        Context manager to measure the execution time of a code block.

        :param name: The name of the span to record.
        """
        if not self.enabled:
            yield
            return
        active = _ActiveSpan(name=name, started_at=time.perf_counter())
        self._stack.append(active)
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - active.started_at) * 1000.0
            child_ms = max(0.0, active.child_ms)
            self.add_ms(name, elapsed_ms)
            self.add_ms(f"{name}.self", max(0.0, elapsed_ms - child_ms))
            if self._stack and self._stack[-1] is active:
                self._stack.pop()
            else:
                try:
                    self._stack.remove(active)
                except ValueError:
                    pass
            if self._stack:
                self._stack[-1].child_ms += elapsed_ms

    def add_ms(self, name: str, value_ms: float) -> None:
        if not self.enabled:
            return
        self.spans_ms[name] = self.spans_ms.get(name, 0.0) + value_ms

    def add_metric(self, name: str, value: float) -> None:
        if not self.enabled:
            return
        self.metrics[name] = value

    def finish(self) -> None:
        if not self.enabled:
            return
        total_ms = (time.perf_counter() - self.started_at) * 1000.0
        parts = [
            f"{name}={value:.2f}ms" for name, value in sorted(self.spans_ms.items())
        ]
        parts.extend(
            f"{name}={value:.0f}" for name, value in sorted(self.metrics.items())
        )
        ordered = ", ".join(parts)
        app_ctx().logger.info(
            f"[RequestProfile] req={self.request_id} kind={self.request_kind} total={total_ms:.2f}ms {ordered}",
            "profile",
        )


def start_request_profile(request_id: str, request_kind: str) -> tuple[RequestProfiler, contextvars.Token]:
    profiler = RequestProfiler(
        request_id=request_id,
        request_kind=request_kind,
        enabled=_should_profile(request_id),
    )
    token = _current_profiler.set(profiler)
    return profiler, token


def stop_request_profile(token: contextvars.Token) -> None:
    _current_profiler.reset(token)


def current_request_profiler() -> RequestProfiler | None:
    return _current_profiler.get()


def ensure_request_profile(
    request_id: str, request_kind: str
) -> tuple[RequestProfiler, contextvars.Token | None, bool]:
    current = current_request_profiler()
    if current is not None:
        return current, None, False
    profiler, token = start_request_profile(request_id, request_kind)
    return profiler, token, True
