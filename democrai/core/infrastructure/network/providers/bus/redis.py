from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, Optional, Tuple

from democrai.core.infrastructure.network.contracts import BusProvider
from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.runtime.foundation.app import app_ctx

try:
    import redis.asyncio as redis

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


ResolvedTarget = Tuple[str, Any]


class RedisBusProvider(BusProvider):
    """
    Redis-based cross-node bus.

    It forwards direct messages to a specific node channel and broadcasts via a
    shared global channel. Local delivery is delegated to injected callbacks.
    """

    def __init__(
        self,
        node_id: str,
        redis_url: str = "redis://localhost:6379",
        *,
        local_send: Optional[Callable[[Any, Dict[str, Any]], None]] = None,
        local_broadcast: Optional[Callable[[Dict[str, Any]], None]] = None,
        resolve_client_node: Optional[Callable[[Any], Optional[ResolvedTarget]]] = None,
    ):
        if not HAS_REDIS:
            raise ProviderNotAvailableError(
                "The 'redis' package is required for RedisBusProvider. Install it with 'pip install redis'."
            )
        self.node_id = node_id
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pubsub: Optional[Any] = None
        self.local_send = local_send
        self.local_broadcast = local_broadcast
        self.resolve_client_node = resolve_client_node

        self.on_message: Optional[Callable[[Any, Dict[str, Any]], None]] = None
        self.on_disconnect: Optional[Callable[[Any], None]] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def _ensure_connected(self):
        if self.redis is None:
            self.redis = redis.from_url(self.redis_url)

    def start(self) -> None:
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError as exc:
                raise RuntimeError("redis_bus_loop_required") from exc
            self._loop = loop
        self._listener_task = self._schedule(self._listen_for_node_messages())
        app_ctx().logger.info(
            f"[RedisBus] Listening for cross-node messages on 'node:{self.node_id}'"
        )

    def stop(self) -> None:
        if self._listener_task:
            task = self._listener_task
            loop = self._loop
            if loop and loop.is_running():
                loop.call_soon_threadsafe(task.cancel)
            else:
                task.cancel()
        app_ctx().logger.info("[RedisBus] Stopped.")

    def _schedule(self, coroutine) -> asyncio.Task:
        loop = self._loop
        if loop is None:
            return asyncio.create_task(coroutine)
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(coroutine, loop)
        return loop.create_task(coroutine)

    def _resolve_target(self, client_id: Any) -> Optional[ResolvedTarget]:
        if isinstance(client_id, dict):
            node_id = client_id.get("node_id")
            resolved_client_id = client_id.get("client_id")
            if node_id is not None and resolved_client_id is not None:
                return str(node_id), resolved_client_id
        if isinstance(client_id, (tuple, list)) and len(client_id) == 2:
            return str(client_id[0]), client_id[1]
        if self.resolve_client_node:
            return self.resolve_client_node(client_id)
        return None

    def _deliver_local(self, client_id: Any, message: Dict[str, Any]) -> None:
        if self.local_send:
            self.local_send(client_id, message)
            return
        if self.on_message:
            self.on_message(client_id, message)
            return
        app_ctx().logger.warning(
            f"[RedisBus] No local delivery callback configured for client {client_id!r}"
        )

    def send(self, client_id: Any, message: Dict[str, Any]) -> None:
        target = self._resolve_target(client_id)
        if target is None:
            self._deliver_local(client_id, message)
            return

        target_node, target_client_id = target
        if target_node == self.node_id:
            self._deliver_local(target_client_id, message)
            return

        if not self.redis:
            self._schedule(self._publish_direct(target_node, target_client_id, message))
            return

        payload = {
            "kind": "direct",
            "client_id": target_client_id,
            "message": message,
        }
        self._schedule(self.redis.publish(f"node:{target_node}", json.dumps(payload)))

    async def _publish_direct(
        self, node_id: str, client_id: Any, message: Dict[str, Any]
    ) -> None:
        await self._ensure_connected()
        if not self.redis:
            return
        payload = {"kind": "direct", "client_id": client_id, "message": message}
        await self.redis.publish(f"node:{node_id}", json.dumps(payload))

    def broadcast(self, message: Dict[str, Any]) -> None:
        if self.redis:
            payload = {"kind": "broadcast", "message": message}
            self._schedule(self.redis.publish("global_bus", json.dumps(payload)))
            return
        self._schedule(self._publish_broadcast(message))

    async def _publish_broadcast(self, message: Dict[str, Any]) -> None:
        await self._ensure_connected()
        if self.redis:
            await self.redis.publish(
                "global_bus",
                json.dumps({"kind": "broadcast", "message": message}),
            )

    async def _listen_for_node_messages(self):
        await self._ensure_connected()
        if not self.redis:
            return
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(f"node:{self.node_id}", "global_bus")

        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                raw = message["data"]
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                payload = json.loads(raw)
                kind = payload.get("kind")
                if kind == "direct":
                    self._deliver_local(payload.get("client_id"), payload.get("message", {}))
                    continue
                if kind == "broadcast":
                    if self.local_broadcast:
                        self.local_broadcast(payload.get("message", {}))
                    elif self.local_send:
                        app_ctx().logger.warning(
                            "[RedisBus] Broadcast received without local_broadcast callback."
                        )
                    continue
                app_ctx().logger.debug(f"[RedisBus] Ignoring unknown payload kind: {kind}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_ctx().logger.error(f"[RedisBus] listener error: {e}")
        finally:
            if self._pubsub is not None:
                try:
                    await self._pubsub.unsubscribe(f"node:{self.node_id}", "global_bus")
                except Exception:
                    pass
                await self._pubsub.close()
                self._pubsub = None
            if self.redis is not None:
                await self.redis.close()
                self.redis = None
