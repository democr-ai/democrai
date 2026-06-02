from __future__ import annotations

import asyncio
import contextlib
import threading
from types import SimpleNamespace


def test_functional_allowlist_refresh_stream_flow_end_to_end(monkeypatch):
    events_mod = __import__(
        "democrai.core.infrastructure.sandbox.os.events", fromlist=["*"]
    )
    stream_mod = __import__(
        "democrai.core.infrastructure.network.providers.stream.memory", fromlist=["*"]
    )

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    processed = []
    processed_event = threading.Event()

    async def _emit_module_event(name, payload, session):
        processed.append((name, dict(payload), dict(session)))
        processed_event.set()
        return ["ok"]

    stream = stream_mod.MemoryStreamProvider()
    stream_ctx = SimpleNamespace(
        logger=SimpleNamespace(
            debug=lambda *a, **k: None,
            error=lambda *a, **k: None,
        )
    )
    ctx = SimpleNamespace(
        network=SimpleNamespace(stream_manager=stream, _loop=loop),
        node_id="node-functional",
        config=SimpleNamespace(get=lambda _k, default="": default),
    )
    monkeypatch.setattr(events_mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(stream_mod, "app_ctx", lambda: stream_ctx)
    monkeypatch.setattr(events_mod, "emit_module_event", _emit_module_event)
    monkeypatch.setattr(events_mod, "debug_os_sandbox_flow", lambda *a, **k: None)
    monkeypatch.setattr(events_mod, "_PROCESSED_EVENT_IDS", set())
    monkeypatch.setattr(events_mod, "_PROCESSED_EVENT_IDS_ORDER", [])
    consumer_task = None

    try:
        async def _start_consumer():
            return asyncio.create_task(
                events_mod._consume_application_network_allowlist_refresh_stream()
            )

        consumer_task = asyncio.run_coroutine_threadsafe(
            _start_consumer(), loop
        ).result(timeout=1)

        future = asyncio.run_coroutine_threadsafe(
            events_mod.emit_application_network_allowlist_refresh_event(
                payload={"reason": "functional-flow", "mode": "functional"}
            ),
            loop,
        )
        assert future.result(timeout=2) == []
        assert processed_event.wait(timeout=2), "stream consumer did not process event"
        assert len(processed) == 1
        assert processed[0][0] == events_mod.APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT
        assert processed[0][1]["reason"] == "functional-flow"
        assert processed[0][1]["mode"] == "functional"
        assert "event_id" not in processed[0][1]
    finally:
        if consumer_task is not None:
            async def _stop_consumer(task):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(
                    _stop_consumer(consumer_task), loop
                ).result(timeout=1)
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2)
        loop.close()
