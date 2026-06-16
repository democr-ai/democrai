from __future__ import annotations

import asyncio
import contextlib

from democrai.core.runtime.foundation.app import app_ctx


def ensure_stream_piped(network, bus, client_id, stream_id: str):
    key = (id(bus), client_id)
    if key not in network._active_subscriptions:
        network._active_subscriptions[key] = {}

    if stream_id in network._active_subscriptions[key]:
        return

    queue = network.stream_manager.subscribe(stream_id)

    async def _pipe():
        try:
            while True:
                data = await queue.get()
                app_ctx().logger.debug(
                    f"[Network] Piping data to client {client_id}: {data}"
                )
                bus.send(client_id, data)
                queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            app_ctx().logger.error(f"[Network] Pipe error: {exc}")
        finally:
            network.stream_manager.unsubscribe(stream_id, queue)
            if key in network._active_subscriptions:
                network._active_subscriptions[key].pop(stream_id, None)

    task = asyncio.create_task(_pipe())
    network._active_subscriptions[key][stream_id] = task


async def pipe_media_stream(network, stream_id: str, *, client, upstream) -> None:
    from democrai.core.application.handler.services.runtime.access import encode_media_stream_chunk

    try:
        index = 0
        async for chunk in upstream.aiter_bytes():
            if not chunk:
                continue
            await network.stream_manager.broadcast(
                stream_id,
                {
                    "type": "media_stream_chunk",
                    "mediaStreamChunk": {
                        "stream_id": stream_id,
                        "index": index,
                        "data": encode_media_stream_chunk(chunk),
                    },
                },
            )
            index += 1
        await network.stream_manager.broadcast(
            stream_id,
            {
                "type": "media_stream_end",
                "mediaStreamEnd": {"stream_id": stream_id},
            },
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await network.stream_manager.broadcast(
            stream_id,
            {
                "type": "media_stream_error",
                "mediaStreamError": {
                    "stream_id": stream_id,
                    "error": str(exc),
                },
            },
        )
    finally:
        network._media_stream_tasks.pop(stream_id, None)
        with contextlib.suppress(Exception):
            await upstream.aclose()
        with contextlib.suppress(Exception):
            await client.aclose()


async def close_media_stream(network, bus, client_id, stream_id: str) -> None:
    task = network._media_stream_tasks.pop(stream_id, None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    key = (id(bus), client_id)
    streams = network._client_media_streams.get(key)
    if streams is not None:
        streams.discard(stream_id)
        if not streams:
            network._client_media_streams.pop(key, None)

    if key in network._active_subscriptions:
        pipe_task = network._active_subscriptions[key].pop(stream_id, None)
        if pipe_task is not None:
            pipe_task.cancel()
        if not network._active_subscriptions[key]:
            network._active_subscriptions.pop(key, None)

    network._stream_owners.pop(stream_id, None)


async def cleanup_client(network, bus, client_id):
    key = (id(bus), client_id)
    session_scope = network._session_scope_key(bus, client_id)
    from democrai.core.infrastructure.network.flows.stream_bindings import cleanup_stream_bindings

    cleanup_stream_bindings(network, bus, client_id)
    reject_client_queries = getattr(network, "_reject_client_queries_for_owner", None)
    if callable(reject_client_queries):
        reject_client_queries(key)

    for stream_id in list(network._client_media_streams.get(key, set())):
        await network._close_media_stream(bus, client_id, stream_id)

    active_subscriptions = network._active_subscriptions.pop(key, {})
    if active_subscriptions:
        app_ctx().logger.info(
            f"[Network] Cleaning up {len(active_subscriptions)} streams for client {client_id}"
        )
        for _, task in list(active_subscriptions.items()):
            task.cancel()

    network._authenticated_clients.pop(key, None)
    # Remove in-memory session approvals only for client:* (connection-scoped) approvals.
    # user:* approvals are intentionally preserved across reconnections: the user has
    # already approved and should not be prompted again in the same process lifetime.
    # Permanent approvals are backed by the DB; user:* is an in-memory cache of them.
    if session_scope.startswith("client:"):
        network._session_external_approvals.pop(session_scope, None)
    network._client_session_keys.pop(key, None)
    getattr(network, "_client_ips", {}).pop(key, None)
    network._stream_owners.pop(network._default_stream_id(client_id), None)


def on_bus_disconnect(network, bus, client_id) -> None:
    network.connection_registry.unregister(bus, client_id)
    if network._loop and network._loop.is_running():
        asyncio.run_coroutine_threadsafe(
            network._cleanup_client(bus, client_id),
            network._loop,
        )
