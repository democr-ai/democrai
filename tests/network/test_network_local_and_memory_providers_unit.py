import asyncio
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.network.providers.stream.memory import MemoryStreamProvider


@pytest.mark.asyncio
async def test_memory_stream_provider_subscribe_broadcast_unsubscribe(monkeypatch):
    logs = []
    monkeypatch.setattr(
        "democrai.core.infrastructure.network.providers.stream.memory.app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                debug=lambda *a, **k: logs.append(("debug", a)),
                error=lambda *a, **k: logs.append(("error", a)),
            )
        ),
    )
    provider = MemoryStreamProvider()
    q = provider.subscribe("room")

    await provider.broadcast("room", {"hello": "world"})
    await asyncio.sleep(0)
    assert q.get_nowait() == {"hello": "world"}

    provider.unsubscribe("room", q)
    assert "room" not in provider._channels
    assert logs


@pytest.mark.asyncio
async def test_memory_stream_provider_broadcast_handles_queue_errors(monkeypatch):
    monkeypatch.setattr(
        "democrai.core.infrastructure.network.providers.stream.memory.app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                debug=lambda *a, **k: None,
                error=lambda *a, **k: None,
            )
        ),
    )

    class _BadQueue:
        _loop = None

        def put_nowait(self, _data):
            raise RuntimeError("queue-fail")

    provider = MemoryStreamProvider()
    provider._channels["room"] = {_BadQueue()}
    await provider.broadcast("room", {"x": 1})
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_memory_stream_provider_broadcast_runtime_loop_fallback(monkeypatch):
    monkeypatch.setattr(
        "democrai.core.infrastructure.network.providers.stream.memory.app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                debug=lambda *a, **k: None,
                error=lambda *a, **k: None,
            )
        ),
    )
    import democrai.core.infrastructure.network.providers.stream.memory as mem_mod

    monkeypatch.setattr(mem_mod.asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError("no-loop")))

    provider = MemoryStreamProvider()
    queue = provider.subscribe("room-fallback")
    await provider.broadcast("room-fallback", {"fallback": True})
    assert queue.get_nowait() == {"fallback": True}


@pytest.mark.asyncio
async def test_memory_stream_provider_branch_matrix_existing_channel_and_missing_broadcast(monkeypatch):
    monkeypatch.setattr(
        "democrai.core.infrastructure.network.providers.stream.memory.app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                debug=lambda *a, **k: None,
                error=lambda *a, **k: None,
            )
        ),
    )
    provider = MemoryStreamProvider()
    q1 = provider.subscribe("room-matrix")
    q2 = provider.subscribe("room-matrix")  # existing-channel branch
    provider.unsubscribe("room-matrix", q1)  # still one subscriber branch
    assert "room-matrix" in provider._channels
    await provider.broadcast("room-missing", {"noop": True})  # missing-channel branch
    provider.unsubscribe("room-matrix", q2)
