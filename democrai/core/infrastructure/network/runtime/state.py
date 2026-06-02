from __future__ import annotations

import threading

from democrai.core.infrastructure.network.registry.connection_registry import ConnectionRegistry


def init_state(network) -> None:
    from democrai.core.infrastructure.network.runtime import network as network_mod

    network.core = network_mod.Core()
    network._loop = None
    network._loop_thread = None
    network._active_subscriptions = {}
    network._authenticated_clients = {}
    network._client_session_keys = {}
    network._session_external_approvals = {}
    network._stream_owners = {}
    network._media_stream_tasks = {}
    network._client_media_streams = {}
    network._stream_bindings = {}
    network._stream_binding_specs = {}
    network._pending_client_queries = {}
    network._pending_access_watchers = {}
    network._pending_network_messages = 0
    network._pending_network_messages_lock = threading.Lock()

    network.connection_registry = ConnectionRegistry()
    network_mod.app_ctx().connection_registry = network.connection_registry

    network.task_manager = network_mod.TaskManager()
    network_mod.app_ctx().task_manager = network.task_manager

    network._notification_queue = network_mod.NotificationQueue()
    network.redis_task_bridge = None
    network._http_thread = None
    network._http_server = None
