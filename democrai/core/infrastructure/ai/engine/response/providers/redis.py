from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as redis

from democrai.core.infrastructure.ai.engine.response.backpressure import (
    put_with_backpressure,
)
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream
from democrai.core.runtime.foundation.app import app_ctx


@dataclass
class _ChannelState:
    queues: set[asyncio.Queue] = field(default_factory=set)
    tokens: dict[asyncio.Queue, str] = field(default_factory=dict)
    task: asyncio.Task | None = None
    heartbeat_task: asyncio.Task | None = None
    register_tasks: dict[str, asyncio.Task] = field(default_factory=dict)


@dataclass
class _LoopState:
    channels: dict[str, _ChannelState] = field(default_factory=dict)
    client: redis.Redis | None = None


_NO_ACTIVE_SUBSCRIBER = "__ENGINE_RESPONSE_STREAM_NO_ACTIVE_SUBSCRIBER__"
_SUBSCRIBER_TTL_SECONDS = 5.0
_SUBSCRIBER_HEARTBEAT_SECONDS = 1.0
_BOUNDED_XADD_SCRIPT = """
local stream_key = KEYS[1]
local subscribers_key = KEYS[2]
local maxlen = tonumber(ARGV[1])
local ttl_seconds = tonumber(ARGV[2])
local now_seconds = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', subscribers_key, '-inf', now_seconds)
if redis.call('XLEN', stream_key) >= maxlen then
    if redis.call('ZCARD', subscribers_key) <= 0 then
        return ARGV[4]
    end
    return nil
end
local id = redis.call('XADD', stream_key, '*', unpack(ARGV, 5))
redis.call('EXPIRE', stream_key, ttl_seconds)
redis.call('EXPIRE', subscribers_key, ttl_seconds)
return id
"""


def _log_warning(message: str) -> None:
    logger = getattr(app_ctx(), "logger", None)
    warning = getattr(logger, "warning", None)
    if callable(warning):
        warning(message)


class RedisEngineResponseStream(EngineResponseStream):
    """Per-request engine response stream backed by Redis Streams.

    Engine response channels are request-scoped. The stream is used as a bounded
    transport buffer: producers wait when the request stream is full, and entries
    are removed after delivery to active local subscribers. One active response
    reader per request is supported across processes; multiple local subscribers
    inside the same provider instance receive the same delivered entries.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        maxlen: int = 10_000,
        ttl_seconds: int = 3_600,
    ) -> None:
        self._redis_url = redis_url
        self._redis: redis.Redis | None = None
        self._loop_states: dict[int, _LoopState] = {}
        self._maxlen = max(100, int(maxlen))
        self._ttl_seconds = max(60, int(ttl_seconds))

    @property
    def _states(self) -> dict[str, _ChannelState]:
        return self._loop_state().channels

    def _loop_state(self) -> _LoopState:
        loop_id = id(asyncio.get_running_loop())
        state = self._loop_states.get(loop_id)
        if state is None:
            state = _LoopState()
            self._loop_states[loop_id] = state
        return state

    async def _client(self) -> redis.Redis:
        if self._redis is not None:
            return self._redis
        state = self._loop_state()
        if state.client is None:
            state.client = redis.from_url(self._redis_url)
        return state.client

    async def _close_client(self, client: Any) -> None:
        try:
            await client.aclose()
        except Exception:
            pass

    async def _release_idle_loop_state(self, loop_id: int, loop_state: _LoopState) -> None:
        if loop_state.channels:
            return
        self._loop_states.pop(loop_id, None)
        if loop_state.client is not None:
            client = loop_state.client
            loop_state.client = None
            await self._close_client(client)

    def subscribe(self, channel_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=4096)
        loop_state = self._loop_state()
        channel_state = loop_state.channels.get(channel_id)
        if channel_state is None:
            channel_state = _ChannelState()
            loop_state.channels[channel_id] = channel_state
            channel_state.task = asyncio.create_task(
                self._read_channel(channel_id, channel_state),
                name=f"engine-response-stream:{channel_id}",
            )
            channel_state.heartbeat_task = asyncio.create_task(
                self._heartbeat_subscribers(channel_id, channel_state),
                name=f"engine-response-subscribers:{channel_id}",
            )
        channel_state.queues.add(queue)
        token = uuid.uuid4().hex
        channel_state.tokens[queue] = token
        task = asyncio.create_task(self._register_subscriber(channel_id, token))
        channel_state.register_tasks[token] = task
        task.add_done_callback(
            lambda _task, token=token: channel_state.register_tasks.pop(token, None)
        )
        return queue

    def unsubscribe(self, channel_id: str, queue: asyncio.Queue) -> None:
        asyncio.create_task(self.unsubscribe_async(channel_id, queue))

    async def unsubscribe_async(self, channel_id: str, queue: asyncio.Queue) -> None:
        loop_id = id(asyncio.get_running_loop())
        loop_state = self._loop_state()
        channel_state = loop_state.channels.get(channel_id)
        if channel_state is None:
            return
        channel_state.queues.discard(queue)
        token = channel_state.tokens.pop(queue, None)
        register_task = (
            channel_state.register_tasks.pop(token, None) if token else None
        )
        if register_task is not None:
            register_task.cancel()
            try:
                await register_task
            except asyncio.CancelledError:
                pass
        if channel_state.queues:
            if token:
                await self._remove_subscriber(channel_id, token)
            return
        loop_state.channels.pop(channel_id, None)
        tasks: list[asyncio.Task] = []
        for task in list(channel_state.register_tasks.values()):
            task.cancel()
            tasks.append(task)
        if channel_state.task is not None:
            channel_state.task.cancel()
            tasks.append(channel_state.task)
        if channel_state.heartbeat_task is not None:
            channel_state.heartbeat_task.cancel()
            tasks.append(channel_state.heartbeat_task)
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if token:
            await self._remove_subscriber(channel_id, token)
        await self._release_idle_loop_state(loop_id, loop_state)

    async def aclose(self) -> None:
        loop_id = id(asyncio.get_running_loop())
        loop_state = self._loop_states.pop(loop_id, None)
        states = list(loop_state.channels.items()) if loop_state is not None else []
        if loop_state is not None:
            loop_state.channels.clear()
        tasks: list[asyncio.Task] = []
        subscriber_tokens: list[tuple[str, str]] = []
        for channel_id, state in states:
            subscriber_tokens.extend(
                (channel_id, token) for token in state.tokens.values()
            )
            for task in list(state.register_tasks.values()):
                task.cancel()
                tasks.append(task)
            if state.task is not None:
                state.task.cancel()
                tasks.append(state.task)
            if state.heartbeat_task is not None:
                state.heartbeat_task.cancel()
                tasks.append(state.heartbeat_task)
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        clients = []
        if loop_state is not None and loop_state.client is not None:
            clients.append(loop_state.client)
        if self._redis is not None:
            clients.append(self._redis)
        self._redis = None
        seen_clients: set[int] = set()
        for client in clients:
            if id(client) in seen_clients:
                continue
            seen_clients.add(id(client))
            for channel_id, token in subscriber_tokens:
                try:
                    await client.zrem(self._subscribers_key(channel_id), token)
                except Exception:
                    pass
            await self._close_client(client)

    async def publish(self, channel_id: str, data: dict[str, Any]) -> None:
        client = await self._client()
        await self._bounded_xadd(client, channel_id, self._fields(data))

    async def _bounded_xadd(
        self,
        client: redis.Redis,
        channel_id: str,
        fields: dict[str, str],
    ) -> None:
        flat_fields = [
            item
            for key, value in fields.items()
            for item in (str(key), str(value))
        ]
        while True:
            result = await client.eval(
                _BOUNDED_XADD_SCRIPT,
                2,
                channel_id,
                self._subscribers_key(channel_id),
                self._maxlen,
                self._ttl_seconds,
                time.time(),
                _NO_ACTIVE_SUBSCRIBER,
                *flat_fields,
            )
            decoded = self._decode_entry_id(result) if result is not None else None
            if decoded == _NO_ACTIVE_SUBSCRIBER:
                if self._has_local_subscribers(channel_id):
                    try:
                        await self._refresh_local_subscribers(channel_id)
                    except Exception as exc:
                        _log_warning(
                            "[Engine] Redis response subscriber refresh "
                            f"failed: {exc}"
                        )
                    await asyncio.sleep(0.01)
                    continue
                raise RuntimeError("engine_response_stream_no_active_subscriber")
            if decoded:
                return
            await asyncio.sleep(0.01)

    async def _heartbeat_subscribers(
        self,
        channel_id: str,
        state: _ChannelState,
    ) -> None:
        while True:
            try:
                tokens = list(state.tokens.values())
                if not tokens:
                    return
                client = await self._client()
                await self._register_subscribers(client, channel_id, tokens)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _log_warning(
                    f"[Engine] Redis response subscriber heartbeat failed: {exc}"
                )
            await asyncio.sleep(_SUBSCRIBER_HEARTBEAT_SECONDS)

    async def _register_subscriber(self, channel_id: str, token: str) -> None:
        try:
            client = await self._client()
            await self._register_subscribers(client, channel_id, [token])
        except Exception:
            return None

    async def _refresh_local_subscribers(self, channel_id: str) -> None:
        state = self._states.get(channel_id)
        if state is None:
            return
        tokens = list(state.tokens.values())
        if not tokens:
            return
        client = await self._client()
        await self._register_subscribers(client, channel_id, tokens)

    async def _register_subscribers(
        self,
        client: redis.Redis,
        channel_id: str,
        tokens: list[str],
    ) -> None:
        if not tokens:
            return
        expires_at = time.time() + _SUBSCRIBER_TTL_SECONDS
        subscribers_key = self._subscribers_key(channel_id)
        await client.zadd(
            subscribers_key,
            {token: expires_at for token in tokens},
        )
        await client.expire(subscribers_key, self._ttl_seconds)

    def _has_local_subscribers(self, channel_id: str) -> bool:
        state = self._states.get(channel_id)
        return bool(state is not None and state.queues)

    async def _remove_subscriber(self, channel_id: str, token: str) -> None:
        try:
            client = await self._client()
            await client.zrem(self._subscribers_key(channel_id), token)
        except Exception:
            return None

    async def _read_channel(self, channel_id: str, state: _ChannelState) -> None:
        last_id = "0-0"
        while True:
            try:
                client = await self._client()
                response = await client.xread(
                    {channel_id: last_id},
                    count=100,
                    block=1_000,
                )
                for _key, entries in response:
                    for entry_id, fields in entries:
                        last_id = self._decode_entry_id(entry_id)
                        for queue in list(state.queues):
                            await put_with_backpressure(
                                queue,
                                dict(fields),
                                is_active=lambda queue=queue: queue in state.queues,
                            )
                        await client.xdel(channel_id, entry_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _log_warning(f"[Engine] Redis response stream read failed: {exc}")
                await asyncio.sleep(1.0)

    @staticmethod
    def _decode_entry_id(entry_id: Any) -> str:
        if isinstance(entry_id, bytes):
            return entry_id.decode("utf-8", errors="replace")
        return str(entry_id)

    @staticmethod
    def _fields(data: dict[str, Any]) -> dict[str, str]:
        return {str(key): str(value) for key, value in data.items()}

    @staticmethod
    def _subscribers_key(channel_id: str) -> str:
        return f"{channel_id}:subscribers"
