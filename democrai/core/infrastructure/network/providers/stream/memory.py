import asyncio
from typing import Dict, Set, Any
from democrai.core.infrastructure.network.contracts import StreamProvider
from democrai.core.runtime.foundation.app import app_ctx


class MemoryStreamProvider(StreamProvider):
    """In-memory implementation of StreamProvider."""

    def __init__(self):
        self._channels: Dict[str, Set[asyncio.Queue]] = {}

    def subscribe(self, channel_id: str) -> asyncio.Queue:
        if channel_id not in self._channels:
            self._channels[channel_id] = set()
        queue: asyncio.Queue = asyncio.Queue(maxsize=4096)  # Limit queue size to prevent memory issues
        self._channels[channel_id].add(queue)
        app_ctx().logger.debug(
            f"[MemoryStream] Client subscribed to channel: {channel_id}"
        )
        return queue

    def unsubscribe(self, channel_id: str, queue: asyncio.Queue):
        if channel_id in self._channels:
            self._channels[channel_id].discard(queue)
            if not self._channels[channel_id]:
                del self._channels[channel_id]
        app_ctx().logger.debug(
            f"[MemoryStream] Client unsubscribed from channel: {channel_id}"
        )

    async def broadcast(self, channel_id: str, data: Any):
        if channel_id in self._channels:
            for queue in list(self._channels[channel_id]):
                try:
                    # Get the loop associated with the queue (if any)
                    loop = getattr(queue, "_loop", None)
                    if not loop:
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            pass

                    if loop and loop.is_running():
                        loop.call_soon_threadsafe(queue.put_nowait, data)
                    else:
                        # Fallback to direct put if we are already in the right thread/loop
                        # but in a cluster/distributed context, call_soon_threadsafe is usually safest.
                        queue.put_nowait(data)
                except Exception as e:
                    app_ctx().logger.error(
                        f"[MemoryStream] Broadcast error on channel {channel_id}: {e}"
                    )
