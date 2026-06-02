from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from democrai.core.application.session.service import SessionService
from democrai.core.infrastructure.database.session_store import SessionStore
from democrai.core.infrastructure.session.providers.memory import MemoryJsonStore
from democrai.core.platform.events import emit_module_event
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.registry import module_event_registry


def _silent_logger() -> SimpleNamespace:
    return SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )


def _snapshot_event_registry():
    return (
        dict(module_event_registry._listeners),  # pylint: disable=protected-access
        dict(module_event_registry._definitions),  # pylint: disable=protected-access
        module_event_registry._registration_order,  # pylint: disable=protected-access
    )


def _restore_event_registry(snapshot) -> None:
    listeners, definitions, order = snapshot
    module_event_registry._listeners = listeners  # pylint: disable=protected-access
    module_event_registry._definitions = definitions  # pylint: disable=protected-access
    module_event_registry._registration_order = order  # pylint: disable=protected-access


@pytest.mark.security_p0
@pytest.mark.asyncio
async def test_security_p0_event_flood_sequential_5000():
    snapshot = _snapshot_event_registry()
    seen = {"count": 0}

    async def _listener(payload, event_name):
        del payload
        del event_name
        seen["count"] += 1
        return True

    try:
        module_event_registry._listeners = {}  # pylint: disable=protected-access
        module_event_registry._definitions = {}  # pylint: disable=protected-access
        module_event_registry._registration_order = 0  # pylint: disable=protected-access
        module_event_registry.register("security.stress.p0", _listener, module_name="core")

        start = time.monotonic()
        for i in range(5_000):
            await emit_module_event("security.stress.p0", payload={"i": i}, session={})
        elapsed = time.monotonic() - start

        assert seen["count"] == 5_000
        assert elapsed < 10.0
    finally:
        _restore_event_registry(snapshot)


@pytest.mark.security_p0
def test_security_p0_session_isolation_parallel_64_users():
    ctx = app_ctx()
    previous_logger = getattr(ctx, "logger", None)
    ctx.logger = _silent_logger()
    try:
        store = SessionStore()
        store.identity_store = MemoryJsonStore()
        store.ui_state_store = MemoryJsonStore()
        store.cache_store = MemoryJsonStore()
        service = SessionService(store)
        errors: list[str] = []

        def _worker(user_id: int):
            try:
                key = service._storage_key_for_identity(user_id)
                for i in range(80):
                    session = service.get_or_create(user_id, "User")
                    marker = f"u{user_id}:{i}"
                    session["marker"] = marker
                    session["payload"] = {"user": user_id, "iter": i}
                    service.persist(key)

                    loaded = service.get_or_create(user_id, "User")
                    if loaded.get("marker") != marker:
                        errors.append(f"marker_mismatch:{user_id}:{i}")
                    payload = loaded.get("payload") or {}
                    if payload.get("user") != user_id:
                        errors.append(f"payload_user_mismatch:{user_id}:{i}")
            except Exception as exc:  # pragma: no cover - defensive for thread visibility
                errors.append(f"thread_exception:{user_id}:{exc}")

        threads = [threading.Thread(target=_worker, args=(uid,)) for uid in range(1, 65)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
    finally:
        ctx.logger = previous_logger


@pytest.mark.security_p1
@pytest.mark.asyncio
async def test_security_p1_event_flood_concurrent_20000():
    snapshot = _snapshot_event_registry()
    seen = {"count": 0}

    async def _listener(payload, event_name):
        del payload
        del event_name
        seen["count"] += 1
        return True

    async def _producer(prefix: int, total: int):
        for i in range(total):
            await emit_module_event(
                "security.stress.p1",
                payload={"p": prefix, "i": i},
                session={},
            )

    try:
        module_event_registry._listeners = {}  # pylint: disable=protected-access
        module_event_registry._definitions = {}  # pylint: disable=protected-access
        module_event_registry._registration_order = 0  # pylint: disable=protected-access
        module_event_registry.register("security.stress.p1", _listener, module_name="core")

        start = time.monotonic()
        await asyncio.wait_for(
            asyncio.gather(*[_producer(p, 2_000) for p in range(10)]),
            timeout=30.0,
        )
        elapsed = time.monotonic() - start

        assert seen["count"] == 20_000
        assert elapsed < 30.0
    finally:
        _restore_event_registry(snapshot)


@pytest.mark.security_p1
def test_security_p1_session_isolation_high_contention_100_users():
    ctx = app_ctx()
    previous_logger = getattr(ctx, "logger", None)
    ctx.logger = _silent_logger()
    try:
        store = SessionStore()
        store.identity_store = MemoryJsonStore()
        store.ui_state_store = MemoryJsonStore()
        store.cache_store = MemoryJsonStore()
        service = SessionService(store)
        errors: list[str] = []

        def _worker(user_id: int):
            try:
                key = service._storage_key_for_identity(user_id)
                for i in range(120):
                    session = service.get_or_create(user_id, "User")
                    marker = f"user-{user_id}-it-{i}"
                    session["marker"] = marker
                    session["counter"] = i
                    service.persist(key)

                    loaded = service.get_or_create(user_id, "User")
                    if loaded.get("marker") != marker:
                        errors.append(f"marker:{user_id}:{i}")
                    if loaded.get("counter") != i:
                        errors.append(f"counter:{user_id}:{i}")
            except Exception as exc:  # pragma: no cover - defensive for thread visibility
                errors.append(f"thread_exception:{user_id}:{exc}")

        threads = [threading.Thread(target=_worker, args=(uid,)) for uid in range(1, 101)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
    finally:
        ctx.logger = previous_logger
