from __future__ import annotations

import base64
import threading
import uuid
from dataclasses import dataclass
from multiprocessing import resource_tracker
from multiprocessing import shared_memory
from typing import Any, Callable


SHARED_MEMORY_THRESHOLD_BYTES = 1024 * 1024
_SHARED_MEMORY_MARKER = "__democrai_shared_memory__"
_ACK_MARKER = "__democrai_shared_memory_ack__"
_LOCAL_OWNED_NAMES: set[str] = set()
_LOCAL_OWNED_NAMES_LOCK = threading.Lock()


@dataclass
class _PendingSharedMemory:
    name: str
    size: int
    handle: shared_memory.SharedMemory

    def cleanup(self) -> None:
        try:
            self.handle.close()
        except Exception:
            pass
        try:
            self.handle.unlink()
        except FileNotFoundError:
            pass


class LocalBinaryPayloadChannel:
    def __init__(
        self,
        connection: Any,
        *,
        threshold_bytes: int = SHARED_MEMORY_THRESHOLD_BYTES,
    ) -> None:
        self._connection = connection
        self._threshold = max(1, int(threshold_bytes or SHARED_MEMORY_THRESHOLD_BYTES))
        self._send_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, _PendingSharedMemory] = {}

    def send(self, value: Any) -> None:
        tokens: list[str] = []
        try:
            packed = self._pack(value, tokens, encode_small_bytes=False)
            with self._send_lock:
                self._connection.send(packed)
        except Exception:
            self._cleanup_tokens(tokens)
            raise

    def send_json(
        self,
        value: Any,
        json_value_func: Callable[..., Any],
    ) -> None:
        tokens: list[str] = []
        try:
            payload = json_value_func(
                value,
                binary_packer=lambda current: self._pack_bytes(current, tokens),
            )
            with self._send_lock:
                self._connection.send(payload)
        except Exception:
            self._cleanup_tokens(tokens)
            raise

    def _pack(
        self,
        value: Any,
        tokens: list[str],
        *,
        encode_small_bytes: bool,
    ) -> Any:
        if isinstance(value, bytes | bytearray):
            return self._pack_bytes(
                value,
                tokens,
                encode_small_bytes=encode_small_bytes,
            )
        if isinstance(value, dict):
            return {
                key: self._pack(
                    current,
                    tokens,
                    encode_small_bytes=encode_small_bytes,
                )
                for key, current in value.items()
            }
        if isinstance(value, list):
            return [
                self._pack(item, tokens, encode_small_bytes=encode_small_bytes)
                for item in value
            ]
        if isinstance(value, tuple):
            return tuple(
                self._pack(item, tokens, encode_small_bytes=encode_small_bytes)
                for item in value
            )
        return value

    def _pack_bytes(
        self,
        value: bytes | bytearray,
        tokens: list[str],
        *,
        encode_small_bytes: bool = True,
    ) -> Any:
        payload = bytes(value)
        if len(payload) < self._threshold:
            if not encode_small_bytes:
                return payload
            return {"__bytes__": base64.b64encode(payload).decode("ascii")}
        shm = shared_memory.SharedMemory(create=True, size=len(payload))
        try:
            shm.buf[: len(payload)] = payload
            token = uuid.uuid4().hex
            with self._pending_lock:
                self._pending[token] = _PendingSharedMemory(
                    name=shm.name,
                    size=len(payload),
                    handle=shm,
                )
            self._remember_local_owned_name(shm)
            tokens.append(token)
            return {
                _SHARED_MEMORY_MARKER: True,
                "token": token,
                "name": shm.name,
                "size": len(payload),
            }
        except Exception:
            try:
                shm.close()
            finally:
                try:
                    shm.unlink()
                except FileNotFoundError:
                    pass
            raise

    def recv(self) -> Any:
        while True:
            value = self._connection.recv()
            if self._handle_ack(value):
                continue
            tokens: list[str] = []
            try:
                unpacked = self._unpack(value, tokens)
            finally:
                if tokens:
                    self._send_ack(tokens)
            return unpacked

    def close(self) -> None:
        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for item in pending:
            self._forget_local_owned_name(item.name)
            item.cleanup()

    def _handle_ack(self, value: Any) -> bool:
        if not isinstance(value, dict) or value.get(_ACK_MARKER) is not True:
            return False
        tokens = [
            str(item)
            for item in list(value.get("tokens") or [])
            if str(item).strip()
        ]
        if not tokens:
            return True
        self._cleanup_tokens(tokens)
        return True

    def _cleanup_tokens(self, tokens: list[str]) -> None:
        if not tokens:
            return
        with self._pending_lock:
            pending = [self._pending.pop(token, None) for token in tokens]
        for item in pending:
            if item is not None:
                self._forget_local_owned_name(item.name)
                item.cleanup()

    def _send_ack(self, tokens: list[str]) -> None:
        with self._send_lock:
            self._connection.send({_ACK_MARKER: True, "tokens": tokens})

    def _unpack(self, value: Any, tokens: list[str]) -> Any:
        if isinstance(value, dict):
            if value.get(_SHARED_MEMORY_MARKER) is True:
                return self._read_shared_descriptor(value, tokens)
            return {key: self._unpack(current, tokens) for key, current in value.items()}
        if isinstance(value, list):
            return [self._unpack(item, tokens) for item in value]
        return value

    def _read_shared_descriptor(self, value: dict[str, Any], tokens: list[str]) -> bytes:
        token = str(value.get("token") or "").strip()
        name = str(value.get("name") or "").strip()
        size = int(value.get("size") or 0)
        if not token or not name or size < 0:
            raise RuntimeError("local_binary_payload_descriptor_invalid")
        shm = shared_memory.SharedMemory(name=name)
        tracked_name = str(getattr(shm, "_name", name) or name)
        try:
            payload = bytes(shm.buf[:size])
        finally:
            shm.close()
            if not self._is_local_owned_name(tracked_name):
                self._unregister_receiver(tracked_name)
        tokens.append(token)
        return payload

    def _remember_local_owned_name(self, shm: shared_memory.SharedMemory) -> None:
        names = self._shared_memory_names(shm.name, str(getattr(shm, "_name", "") or ""))
        with _LOCAL_OWNED_NAMES_LOCK:
            _LOCAL_OWNED_NAMES.update(names)

    def _forget_local_owned_name(self, name: str) -> None:
        names = self._shared_memory_names(name)
        with _LOCAL_OWNED_NAMES_LOCK:
            for item in names:
                _LOCAL_OWNED_NAMES.discard(item)

    def _is_local_owned_name(self, name: str) -> bool:
        names = self._shared_memory_names(name)
        with _LOCAL_OWNED_NAMES_LOCK:
            return any(item in _LOCAL_OWNED_NAMES for item in names)

    def _shared_memory_names(self, *names: str) -> set[str]:
        values: set[str] = set()
        for name in names:
            raw = str(name or "").strip()
            if not raw:
                continue
            values.add(raw)
            if raw.startswith("/"):
                values.add(raw[1:])
            else:
                values.add(f"/{raw}")
        return values

    def _unregister_receiver(self, name: str) -> None:
        try:
            resource_tracker.unregister(name, "shared_memory")
        except Exception:
            pass
