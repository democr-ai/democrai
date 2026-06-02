from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.database.session_store import SessionStore
from democrai.core.infrastructure.session.providers.memory import MemoryJsonStore
from democrai.core.runtime.foundation.app import app_ctx
from clients.qtdesktop.state_store import _deep_copy, _deep_merge, _flatten_paths


def _silent_logger() -> SimpleNamespace:
    return SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )


@pytest.mark.security_p1
def test_session_store_same_session_concurrent_mutation():
    """Test concurrent mutation of same session dict via external reference.

    Scenario: get() returns direct reference to _cache dict. If multiple threads
    mutate same session in-place concurrently, dict may raise RuntimeError or
    exhibit corrupted structure. GIL does not guarantee atomicity for
    read-modify-write operations on dicts.
    """
    ctx = app_ctx()
    previous_logger = getattr(ctx, "logger", None)
    ctx.logger = _silent_logger()
    try:
        store = SessionStore()
        store.identity_store = MemoryJsonStore()
        store.ui_state_store = MemoryJsonStore()
        store.cache_store = MemoryJsonStore()

        user_key = "user:concurrent:mutation:1"
        initial_session = store.create(user_key, {"counter": 0})

        errors: list[str] = []
        thread_count = 20
        iterations = 100

        def _worker(thread_id: int):
            try:
                for i in range(iterations):
                    session = store.get(user_key)
                    if session is None:
                        errors.append(f"thread_{thread_id}_session_none")
                        continue
                    current = session.get("counter", 0)
                    session["counter"] = current + 1
                    session[f"thread_{thread_id}_mark_{i}"] = True
            except RuntimeError as exc:
                if "dict changed size" in str(exc):
                    errors.append(f"thread_{thread_id}_dict_corruption:{exc}")
                else:
                    raise
            except Exception as exc:
                errors.append(f"thread_{thread_id}_exception:{exc}")

        threads = [threading.Thread(target=_worker, args=(tid,)) for tid in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5.0)

        assert errors == []
        final_session = store.get(user_key)
        assert final_session is not None
        assert isinstance(final_session.get("counter"), int)
    finally:
        ctx.logger = previous_logger


@pytest.mark.security_p1
def test_session_store_save_all_concurrent_delete():
    """Test save_all() interleaved with delete() on same key.

    Scenario: save_all() copies dirty_keys inside lock, then calls save()
    outside the outer lock. If delete() is called on same key between copy
    and save(), sub-stores may see inconsistent state (delete after save,
    or save on non-existent cache entry). Verify no exceptions or corruption.
    """
    ctx = app_ctx()
    previous_logger = getattr(ctx, "logger", None)
    ctx.logger = _silent_logger()
    try:
        store = SessionStore()
        store.identity_store = MemoryJsonStore()
        store.ui_state_store = MemoryJsonStore()
        store.cache_store = MemoryJsonStore()

        user_key = "user:save_delete:1"
        errors: list[str] = []
        stop_flag = {"value": False}

        def _saver():
            try:
                for iteration in range(50):
                    store.create(user_key, {"saver_iter": iteration})
                    store.mark_dirty(user_key)
                    store.save_all()
                    time.sleep(0.001)
            except Exception as exc:
                errors.append(f"saver_exception:{exc}")

        def _deleter():
            try:
                for iteration in range(50):
                    time.sleep(0.001)
                    store.delete(user_key)
            except Exception as exc:
                errors.append(f"deleter_exception:{exc}")

        saver_thread = threading.Thread(target=_saver)
        deleter_thread = threading.Thread(target=_deleter)

        saver_thread.start()
        deleter_thread.start()

        saver_thread.join(timeout=5.0)
        deleter_thread.join(timeout=5.0)

        assert errors == []
    finally:
        ctx.logger = previous_logger


@pytest.mark.security_p1
def test_session_store_concurrent_operations_mixed():
    """Test concurrent create/get/touch/mark_dirty on same key.

    Scenario: 16 threads perform mixed operations on same user_key.
    RLock should prevent deadlock and corruption. Verify no exceptions
    and correct final state.
    """
    ctx = app_ctx()
    previous_logger = getattr(ctx, "logger", None)
    ctx.logger = _silent_logger()
    try:
        store = SessionStore()
        store.identity_store = MemoryJsonStore()
        store.ui_state_store = MemoryJsonStore()
        store.cache_store = MemoryJsonStore()

        user_key = "user:mixed:ops:1"
        store.create(user_key, {"initialized": True})

        errors: list[str] = []
        thread_count = 16
        operations_per_thread = 80

        def _worker(thread_id: int):
            try:
                for op_index in range(operations_per_thread):
                    op_type = op_index % 4

                    if op_type == 0:
                        session = store.get(user_key)
                        if session is not None:
                            session[f"thread_{thread_id}_get_{op_index}"] = True
                    elif op_type == 1:
                        store.touch(user_key)
                    elif op_type == 2:
                        store.mark_dirty(user_key)
                    else:
                        session = store.get(user_key)
                        if session is not None:
                            session[f"thread_{thread_id}_update_{op_index}"] = op_index
            except Exception as exc:
                errors.append(f"thread_{thread_id}_operation_{op_index}:{exc}")

        start = time.monotonic()
        threads = [threading.Thread(target=_worker, args=(tid,)) for tid in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5.0)
        elapsed = time.monotonic() - start

        assert errors == []
        assert elapsed < 10.0

        final_session = store.get(user_key)
        assert final_session is not None
        assert final_session.get("initialized") is True
    finally:
        ctx.logger = previous_logger


def test_desktop_store_utilities_thread_safe():
    """Test thread safety of desktop Store utility functions.

    NOTE: Store(QObject) itself is not thread-safe by design and must run
    on Qt main thread only. However, the pure utility functions (_deep_merge,
    _deep_copy, _flatten_paths) should be thread-safe for concurrent use.

    This test verifies these utilities can be called concurrently without
    exceptions or data corruption.
    """
    errors: list[str] = []
    thread_count = 8

    def _worker(thread_id: int):
        try:
            for iteration in range(100):
                data = {
                    f"key_{thread_id}_{iteration}": {
                        "nested": [1, 2, {"deep": "value"}],
                        "count": iteration,
                    }
                }
                copied = _deep_copy(data)
                assert copied == data
                assert copied is not data

                base = {"existing": {"field": 1}}
                incoming = {f"new_{iteration}": {"val": thread_id}}
                merged = _deep_merge(base.copy(), incoming)
                assert f"new_{iteration}" in merged

                paths = _flatten_paths(data)
                assert isinstance(paths, list)
                assert all(isinstance(p, str) for p in paths)
        except Exception as exc:
            errors.append(f"thread_{thread_id}:{exc}")

    threads = [threading.Thread(target=_worker, args=(tid,)) for tid in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert errors == []
