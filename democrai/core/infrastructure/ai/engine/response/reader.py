from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
    TERMINAL_STATUSES,
)
from democrai.core.infrastructure.ai.engine.response.factory import (
    resolve_engine_response_stream,
)
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream


@dataclass(frozen=True)
class EngineResponseEntry:
    kind: str
    data: Any = None
    node: str = ""
    attempt: int = 0
    seq: int | None = None


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class EngineResponseStreamReader:
    """Consumer side of the per-request response stream.

    Reads live events from the configured response stream provider. When the
    stream goes silent past the keepalive window, the queue row is the authority: a
    terminal row without a received ``end``/``error`` means the producer died
    after finishing or the job was killed — surfaced as an error instead of
    hanging forever.
    """

    def __init__(
        self,
        response_stream: EngineResponseStream | Any,
        key: str,
        *,
        request_id: str,
        store: EngineInvocationQueueStore | None = None,
        keepalive_timeout_seconds: float = 30.0,
        total_timeout_seconds: float | None = None,
        block_ms: int = 1_000,
    ) -> None:
        self._stream = resolve_engine_response_stream(response_stream)
        self._key = key
        self._request_id = request_id
        self._store = store or EngineInvocationQueueStore()
        self._keepalive_timeout = max(1.0, float(keepalive_timeout_seconds))
        self._total_timeout = total_timeout_seconds
        self._block_ms = max(100, int(block_ms))
        self._subscription = self._stream.subscribe(key)
        self._expected_seq: int | None = None
        self._terminal_grace_until: float | None = None

    async def entries(self) -> AsyncIterator[EngineResponseEntry]:
        started = time.monotonic()
        last_activity = time.monotonic()
        terminal_seen = False
        try:
            while True:
                if (
                    self._total_timeout is not None
                    and time.monotonic() - started > self._total_timeout
                ):
                    raise TimeoutError("engine_orchestrator_deadline_exceeded")
                try:
                    fields = await asyncio.wait_for(
                        self._subscription.get(),
                        timeout=self._block_ms / 1000.0,
                    )
                except asyncio.CancelledError:
                    raise
                except asyncio.TimeoutError:
                    fields = None
                except Exception as exc:
                    raise RuntimeError(
                        f"engine_orchestrator_response_stream_unavailable:{exc}"
                    ) from exc
                if fields is None:
                    if self._terminal_grace_until is not None:
                        if time.monotonic() >= self._terminal_grace_until:
                            await self._raise_terminated_without_end()
                        continue
                    if time.monotonic() - last_activity > self._keepalive_timeout:
                        await self._check_row_authoritative()
                        last_activity = time.monotonic()
                    continue
                if not isinstance(fields, dict):
                    continue
                entry = self._parse(fields)
                if entry.kind in {"queued", "keepalive"}:
                    last_activity = time.monotonic()
                    continue
                last_activity = time.monotonic()
                self._check_chunk_sequence(entry)
                if entry.kind in {"end", "error"}:
                    terminal_seen = True
                    yield entry
                    return
                yield entry
        finally:
            if not terminal_seen:
                await self._request_cancel()
            await self._cleanup()

    async def _request_cancel(self) -> None:
        try:
            await asyncio.to_thread(self._store.request_cancel, self._request_id)
        except Exception:
            return None

    def _check_chunk_sequence(self, entry: EngineResponseEntry) -> None:
        """Detect chunks lost to MAXLEN trimming: a gap in the sequence means
        output already skipped, which must surface as an error rather than a
        silently spliced stream."""
        if entry.kind == "retry" or entry.kind == "accepted":
            # New attempt: its writer restarts the sequence.
            self._expected_seq = 0
            return
        if entry.kind != "chunk" or entry.seq is None:
            return
        if self._expected_seq is None:
            if entry.seq != 0:
                raise RuntimeError(
                    "engine_orchestrator_response_stream_gap:"
                    f"expected=0:got={entry.seq}"
                )
        elif entry.seq != self._expected_seq:
            raise RuntimeError(
                "engine_orchestrator_response_stream_gap:"
                f"expected={self._expected_seq}:got={entry.seq}"
            )
        self._expected_seq = entry.seq + 1

    async def _cleanup(self) -> None:
        try:
            await self._stream.unsubscribe_async(self._key, self._subscription)
        except Exception:
            return None

    async def _raise_terminated_without_end(self) -> None:
        status = await asyncio.to_thread(self._store.get_status, self._request_id)
        await self._cleanup()
        resolved = (status or {}).get("status", "missing")
        error = (status or {}).get("last_error") or ""
        raise RuntimeError(
            "engine_orchestrator_stream_terminated_without_end:"
            f"status={resolved}:error={error}"
        )

    async def _check_row_authoritative(self) -> None:
        status = await asyncio.to_thread(self._store.get_status, self._request_id)
        if status is None:
            raise RuntimeError(
                "engine_orchestrator_request_row_missing:" + self._request_id
            )
        if status["status"] in TERMINAL_STATUSES:
            # The row settled but the closing stream entry may still be in
            # flight (the DB write lands before the XADD): give the stream a
            # short grace window before declaring it truncated.
            self._terminal_grace_until = time.monotonic() + 2.0
            return
        # pending/failed/processing: a retry or a slow producer — keep waiting.

    @staticmethod
    def _parse(fields: dict[Any, Any]) -> EngineResponseEntry:
        decoded = {_decode(key): _decode(value) for key, value in fields.items()}
        kind = decoded.get("kind", "")
        raw = decoded.get("data")
        data: Any = None
        if raw is not None:
            try:
                data = json.loads(raw)
            except Exception:
                data = raw
        attempt = 0
        try:
            attempt = int(decoded.get("attempt") or 0)
        except Exception:
            attempt = 0
        seq: int | None = None
        if decoded.get("seq") is not None:
            try:
                seq = int(decoded["seq"])
            except Exception:
                seq = None
        return EngineResponseEntry(
            kind=kind,
            data=data,
            node=decoded.get("node", ""),
            attempt=attempt,
            seq=seq,
        )
