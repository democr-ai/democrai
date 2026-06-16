from __future__ import annotations

import json
from typing import Any

from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.infrastructure.ai.engine.response.factory import (
    resolve_engine_response_stream,
)
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream


class EngineResponseStreamWriter:
    """Producer side of the per-request response stream.

    Entry fields: ``kind`` (queued|accepted|keepalive|chunk|message|result|
    end|error|retry), ``data`` (JSON, same wire format as the gRPC
    chunk_json), ``node``, ``attempt``.
    """

    def __init__(
        self,
        response_stream: EngineResponseStream | Any,
        key: str,
        *,
        node_id: str = "",
    ) -> None:
        self._stream = resolve_engine_response_stream(response_stream)
        self._key = key
        self._node_id = node_id
        # Monotonic per-writer chunk counter: lets the reader detect entries
        # lost by a volatile stream provider instead of silently splicing output.
        self._chunk_seq = 0

    @property
    def key(self) -> str:
        return self._key

    async def _emit(self, kind: str, fields: dict[str, Any] | None = None) -> None:
        entry: dict[str, Any] = {"kind": kind, "node": self._node_id}
        if fields:
            entry.update(fields)
        await self._stream.publish(self._key, entry)

    @staticmethod
    def _data(value: Any) -> str:
        return json.dumps(json_value(value), ensure_ascii=True)

    async def queued(self) -> None:
        await self._emit("queued")

    async def accepted(self, *, attempt: int) -> None:
        await self._emit("accepted", {"attempt": int(attempt)})

    async def keepalive(self) -> None:
        await self._emit("keepalive")

    async def chunk(self, value: Any) -> None:
        await self._emit(
            "chunk", {"data": self._data(value), "seq": self._next_seq()}
        )

    async def chunk_raw(self, data_json: str) -> None:
        await self._emit(
            "chunk", {"data": data_json or "null", "seq": self._next_seq()}
        )

    def _next_seq(self) -> int:
        seq = self._chunk_seq
        self._chunk_seq += 1
        return seq

    async def message(self, value: Any) -> None:
        await self._emit("message", {"data": self._data(value)})

    async def message_raw(self, data_json: str) -> None:
        await self._emit("message", {"data": data_json or "null"})

    async def result(self, value: Any) -> None:
        await self._emit("result", {"data": self._data(value)})

    async def end(self) -> None:
        await self._emit("end")

    async def error(
        self,
        message: str,
        *,
        traceback_text: str = "",
    ) -> None:
        await self._emit(
            "error",
            {
                "data": json.dumps(
                    {"error": str(message), "traceback": traceback_text},
                    ensure_ascii=True,
                )
            },
        )

    async def retry(self, *, attempt: int, error: str) -> None:
        await self._emit(
            "retry",
            {
                "attempt": int(attempt),
                "data": json.dumps({"error": str(error)}, ensure_ascii=True),
            },
        )
