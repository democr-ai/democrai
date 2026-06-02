from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class ActionLockRecord:
    request_id: str
    acquired_at: float
    expires_at: float


class ActionLockManager:
    """Best-effort single-flight guard for user actions."""

    def __init__(self, *, ttl_seconds: float = 30.0) -> None:
        self._ttl_seconds = max(1.0, ttl_seconds)
        self._lock = asyncio.Lock()
        self._active: Dict[str, ActionLockRecord] = {}

    async def acquire(self, key: str, request_id: str) -> bool:
        if not key or not request_id:
            return True
        now = time.monotonic()
        async with self._lock:
            self._purge_expired(now)
            existing = self._active.get(key)
            if existing is not None and existing.request_id != request_id:
                return False
            self._active[key] = ActionLockRecord(
                request_id=request_id,
                acquired_at=now,
                expires_at=now + self._ttl_seconds,
            )
            return True

    async def release(self, key: str, request_id: str) -> None:
        if not key or not request_id:
            return
        async with self._lock:
            existing = self._active.get(key)
            if existing is None or existing.request_id != request_id:
                return
            self._active.pop(key, None)

    def _purge_expired(self, now: float) -> None:
        expired = [
            key
            for key, record in self._active.items()
            if record.expires_at <= now
        ]
        for key in expired:
            self._active.pop(key, None)
