import asyncio
import json
import redis.asyncio as redis
from typing import Any, Dict, List, Optional
from democrai.core.infrastructure.network.contracts import StreamProvider
from democrai.core.runtime.foundation.app import app_ctx


class RedisStreamProvider(StreamProvider):
    """
    Redis implementation of StreamProvider.
    Uses Redis Pub/Sub to synchronize streams across multiple server nodes.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None
        self._local_queues: Dict[str, List[asyncio.Queue]] = {}
        self._listener_tasks: Dict[str, asyncio.Task] = {}

    async def _ensure_connected(self):
        if self.redis is None:
            self.redis = redis.from_url(self.redis_url)

    def subscribe(self, channel_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        if channel_id not in self._local_queues:
            self._local_queues[channel_id] = []
            # Start a background task to listen to this Redis channel
            task = asyncio.create_task(self._redis_listener(channel_id))
            self._listener_tasks[channel_id] = task

        self._local_queues[channel_id].append(queue)
        return queue

    def unsubscribe(self, channel_id: str, queue: asyncio.Queue) -> None:
        if channel_id in self._local_queues:
            if queue in self._local_queues[channel_id]:
                self._local_queues[channel_id].remove(queue)

            if not self._local_queues[channel_id]:
                # Stop listener if no more local subscribers
                del self._local_queues[channel_id]
                task = self._listener_tasks.pop(channel_id, None)
                if task:
                    task.cancel()

    async def broadcast(self, channel_id: str, data: Any) -> None:
        await self._ensure_connected()
        payload = json.dumps(data)
        if self.redis:
            await self.redis.publish(channel_id, payload)

    async def _redis_listener(self, channel_id: str):
        """Listens to a Redis channel and pushes messages to all local queues."""
        await self._ensure_connected()
        if not self.redis:
            return
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel_id)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    # Distribute to all local subscribers
                    for queue in self._local_queues.get(channel_id, []):
                        await queue.put(data)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(channel_id)
        except Exception as e:
            app_ctx().logger.error(f"[RedisStream] Listener error on {channel_id}: {e}")
        finally:
            await pubsub.close()
