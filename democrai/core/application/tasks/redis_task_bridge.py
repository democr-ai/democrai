"""
RedisTaskBridge — cross-node message relay for background task notifications.

When a TaskManager on node A needs to notify a user connected on node B,
local ConnectionRegistry lookup fails. The bridge publishes the message to
Redis Pub/Sub channel `task_notify:{user_id}:{organization_id}`, and the listener on every
node checks its local registry and delivers if the user is connected.

Activated only when `network.redis.enabled` is True in the config.
"""

from __future__ import annotations
import asyncio
import json
from typing import Optional
from urllib.parse import quote, unquote

import redis.asyncio as aioredis

from democrai.core.runtime.foundation.app import app_ctx

CHANNEL_PREFIX = "task_notify"


def _organization_channel_segment(organization_id: Optional[int]) -> str:
    return "" if organization_id is None else str(organization_id)


def _organization_log_value(organization_id: Optional[int]) -> str:
    return "none" if organization_id is None else str(organization_id)


def _channel_name(user_id: int, organization_id: Optional[int] = None) -> str:
    return (
        f"{CHANNEL_PREFIX}:{quote(str(user_id), safe='')}:"
        f"{quote(_organization_channel_segment(organization_id), safe='')}"
    )


def _parse_channel_name(channel: str) -> tuple[Optional[int], Optional[int]]:
    parts = channel.split(":", 2)
    if len(parts) != 3 or parts[0] != CHANNEL_PREFIX:
        return None, None
    user_id_text = unquote(parts[1])
    organization_id_text = unquote(parts[2])
    try:
        user_id = int(user_id_text) if user_id_text else None
    except Exception:
        user_id = None
    try:
        organization_id = int(organization_id_text) if organization_id_text else None
    except Exception:
        organization_id = None
    return user_id, organization_id


class RedisTaskBridge:
    """
    Pub/Sub bridge for cross-node task notification delivery.

    Publish path:  TaskManager._send_to_user → local miss → bridge.publish()
    Listen path:   bridge._listener() → local ConnectionRegistry → bus.send()
    """

    def __init__(self, redis_url: str, connection_registry):
        self._redis_url = redis_url
        self._registry = connection_registry
        self._redis: Optional[aioredis.Redis] = None
        self._sub_redis: Optional[aioredis.Redis] = (
            None  # Separate connection for subscriber
        )
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False

    async def _ensure_connected(self):
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url)

    async def start(self):
        """Start the cross-node listener. Call from Network.start()."""
        if self._running and self._listener_task is not None:
            return
        self._sub_redis = aioredis.from_url(self._redis_url)
        self._running = True
        self._listener_task = asyncio.create_task(self._listener())
        app_ctx().logger.info(f"[RedisTaskBridge] Listening on {CHANNEL_PREFIX}:*")

    async def stop(self):
        """Stop the listener and close connections."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        if self._sub_redis:
            await self._sub_redis.aclose()
            self._sub_redis = None
        app_ctx().logger.info("[RedisTaskBridge] Stopped.")

    def publish(
        self, user_id: int, message: dict, organization_id: Optional[int] = None
    ) -> None:
        """
        Publish a task notification for cross-node delivery.
        Called when local ConnectionRegistry has no connections for the user.
        """

        async def _do_publish():
            try:
                await self._ensure_connected()
                channel = _channel_name(user_id, organization_id)
                payload = json.dumps(message, default=str)
                await self._redis.publish(channel, payload)
                app_ctx().logger.debug(f"[RedisTaskBridge] Published to {channel}")
            except Exception as e:
                app_ctx().logger.error(f"[RedisTaskBridge] Publish error: {e}")

        # Schedule on the running event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_do_publish())
            else:
                loop.run_until_complete(_do_publish())
        except RuntimeError:
            app_ctx().logger.error("[RedisTaskBridge] No event loop for publish")

    async def _listener(self):
        """
        Listen on task_notify:* pattern and deliver to local connections.
        Uses a separate Redis connection (required by redis.asyncio for pub/sub).
        """
        if self._sub_redis is None:
            app_ctx().logger.error("[RedisTaskBridge] Listener started without subscriber connection")
            return
        pubsub = self._sub_redis.pubsub()
        await pubsub.psubscribe(f"{CHANNEL_PREFIX}:*")

        try:
            while self._running:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    await asyncio.sleep(0.05)
                    continue

                if message["type"] != "pmessage":
                    continue

                # Extract scoped identity from channel name.
                channel: str = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode("utf-8")
                user_id, organization_id = _parse_channel_name(channel)
                if not user_id:
                    continue

                # Try local delivery
                connections = self._registry.get_connections(user_id, organization_id)
                if not connections:
                    continue  # User not on this node, ignore

                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                try:
                    msg_dict = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    app_ctx().logger.warning(
                        f"[RedisTaskBridge] Invalid JSON on {channel}"
                    )
                    continue

                for bus, client_id in connections:
                    try:
                        bus.send(client_id, msg_dict)
                    except Exception as e:
                        app_ctx().logger.error(
                            f"[RedisTaskBridge] Local send error: {e}"
                        )

                app_ctx().logger.debug(
                    f"[RedisTaskBridge] Delivered to {len(connections)} local connection(s) for '{user_id}' org '{_organization_log_value(organization_id)}'"
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            app_ctx().logger.error(f"[RedisTaskBridge] Listener error: {e}")
        finally:
            await pubsub.punsubscribe(f"{CHANNEL_PREFIX}:*")
            await pubsub.close()
