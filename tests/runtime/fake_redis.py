"""In-process response stream fake used by engine invocation tests."""

from __future__ import annotations

import asyncio

from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream


class FakeRedisStream(EngineResponseStream):
    def __init__(self):
        self.streams: dict[str, list[tuple[str, dict]]] = {}
        self.expirations: dict[str, int] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.subscriptions: dict[str, set[asyncio.Queue]] = {}
        self._sequence = 0
        self._condition = asyncio.Condition()

    def subscribe(self, channel_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscriptions.setdefault(channel_id, set()).add(queue)
        return queue

    def unsubscribe(self, channel_id: str, queue: asyncio.Queue) -> None:
        queues = self.subscriptions.get(channel_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            self.subscriptions.pop(channel_id, None)

    async def publish(self, channel_id: str, data: dict) -> None:
        async with self._condition:
            self._sequence += 1
            entry_id = f"{self._sequence}-0"
            fields = dict(data)
            self.streams.setdefault(channel_id, []).append((entry_id, fields))
            for queue in list(self.subscriptions.get(channel_id, ())):
                await queue.put(fields)
            self._condition.notify_all()

    async def xadd(self, key, fields, maxlen=None, approximate=True):
        async with self._condition:
            self._sequence += 1
            entry_id = f"{self._sequence}-0"
            self.streams.setdefault(key, []).append((entry_id, dict(fields)))
            self._condition.notify_all()
            return entry_id

    async def eval(self, script, numkeys, *keys_and_args):
        del script, numkeys
        stream_key = keys_and_args[0]
        subscribers_key = keys_and_args[1]
        maxlen = int(keys_and_args[2])
        ttl = int(keys_and_args[3])
        now = float(keys_and_args[4])
        no_active_subscriber = str(keys_and_args[5])
        raw_fields = keys_and_args[6:]
        fields = {
            str(raw_fields[index]): str(raw_fields[index + 1])
            for index in range(0, len(raw_fields), 2)
        }
        async with self._condition:
            subscribers = self.zsets.setdefault(subscribers_key, {})
            stale = [
                token
                for token, expires_at in subscribers.items()
                if float(expires_at) <= now
            ]
            for token in stale:
                subscribers.pop(token, None)
            if len(self.streams.get(stream_key, ())) >= maxlen:
                if not subscribers:
                    return no_active_subscriber
                return None
            self._sequence += 1
            entry_id = f"{self._sequence}-0"
            self.streams.setdefault(stream_key, []).append((entry_id, fields))
            self.expirations[stream_key] = ttl
            self.expirations[subscribers_key] = ttl
            self._condition.notify_all()
            return entry_id

    async def xread(self, streams, count=None, block=None):
        key, last_id = next(iter(streams.items()))

        def _pending():
            entries = self.streams.get(key, [])
            return [
                (entry_id, fields)
                for entry_id, fields in entries
                if self._after(entry_id, last_id)
            ]

        items = _pending()
        if items:
            return [(key, items[: count or len(items)])]
        if not block:
            return []
        async with self._condition:
            try:
                await asyncio.wait_for(
                    self._condition.wait(), timeout=block / 1000.0
                )
            except asyncio.TimeoutError:
                return []
        items = _pending()
        if items:
            return [(key, items[: count or len(items)])]
        return []

    async def xlen(self, key):
        return len(self.streams.get(key, ()))

    async def xdel(self, key, *entry_ids):
        entries = self.streams.get(key)
        if not entries:
            return 0
        remove = {str(entry_id) for entry_id in entry_ids}
        kept = [
            (entry_id, fields)
            for entry_id, fields in entries
            if str(entry_id) not in remove
        ]
        self.streams[key] = kept
        return len(entries) - len(kept)

    async def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(
            {str(member): float(score) for member, score in mapping.items()}
        )
        return len(mapping)

    async def zrem(self, key, *members):
        zset = self.zsets.get(key)
        if not zset:
            return 0
        removed = 0
        for member in members:
            if str(member) in zset:
                zset.pop(str(member), None)
                removed += 1
        return removed

    async def zremrangebyscore(self, key, min_score, max_score):
        del min_score
        zset = self.zsets.get(key)
        if not zset:
            return 0
        max_value = float(max_score)
        stale = [
            member
            for member, score in zset.items()
            if float(score) <= max_value
        ]
        for member in stale:
            zset.pop(member, None)
        return len(stale)

    async def zcard(self, key):
        return len(self.zsets.get(key, ()))

    @staticmethod
    def _after(entry_id, last_id):
        def _parts(value):
            major, _, minor = str(value).partition("-")
            return int(major), int(minor or 0)

        return _parts(entry_id) > _parts(last_id)

    async def expire(self, key, ttl):
        self.expirations[key] = ttl

    async def delete(self, key):
        self.streams.pop(key, None)

    async def aclose(self):
        return None
