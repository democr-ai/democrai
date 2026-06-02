from __future__ import annotations

import asyncio
import threading  # noqa: F401
from typing import Any, Dict, List, Optional, Tuple

from democrai.core.application.handler.request import Core  # noqa: F401
from democrai.core.application.tasks.notification_queue import NotificationQueue  # noqa: F401
from democrai.core.application.tasks.task_manager import TaskManager  # noqa: F401
from democrai.core.infrastructure.network.contracts import BusProvider, StreamProvider
from democrai.core.infrastructure.network.flows import legacy_requests as legacy_flow
from democrai.core.infrastructure.network.flows import media as media_flow
from democrai.core.infrastructure.network.flows import request_launch as request_flow
from democrai.core.infrastructure.network.flows import streams as stream_flow
from democrai.core.infrastructure.network.flows import stream_bindings as stream_binding_flow
from democrai.core.infrastructure.network.protocol import ProtocolDispatcher
from democrai.core.infrastructure.network.protocol import auth as protocol_auth
from democrai.core.infrastructure.network.protocol import handlers as protocol_handlers
from democrai.core.infrastructure.network.runtime import callbacks as runtime_callbacks
from democrai.core.infrastructure.network.runtime import lifecycle as runtime_lifecycle
from democrai.core.infrastructure.network.runtime.state import init_state
from democrai.core.runtime.foundation.app import app_ctx  # noqa: F401
from democrai.core.runtime.observability.profiling import (  # noqa: F401
    ensure_request_profile,
    stop_request_profile,
)


class Network:
    _GUEST_ALLOWED_MESSAGE_TYPES = {"init", "ping"}

    # Runtime entrypoints.
    start = runtime_lifecycle.start
    init_http_ws = runtime_lifecycle.init_http_ws
    stop_http_ws = runtime_lifecycle.stop_http_ws
    _run_network_loop = runtime_lifecycle.run_network_loop
    stop = runtime_lifecycle.stop

    # Callback / dispatch wiring.
    _on_bus_message = runtime_callbacks.on_bus_message
    _process_message = runtime_callbacks.process_message
    _init_dispatcher = runtime_callbacks.init_dispatcher

    # Protocol handlers.
    _handle_action = protocol_handlers.handle_action
    _handle_task_response = protocol_handlers.handle_task_response
    _handle_task_cancel = protocol_handlers.handle_task_cancel
    _handle_task_get = protocol_handlers.handle_task_get
    _handle_client_query_result = protocol_handlers.handle_client_query_result
    _handle_stream_piping = protocol_handlers.handle_stream_piping
    _handle_legacy_launch = legacy_flow.handle_legacy_launch

    # Media handlers.
    _handle_media_resolve = media_flow.handle_media_resolve
    _handle_media_stream_open = media_flow.handle_media_stream_open
    _handle_media_stream_close = media_flow.handle_media_stream_close
    _handle_stream_binding_subscribe = stream_binding_flow.handle_stream_binding_subscribe
    _handle_stream_binding_unsubscribe = stream_binding_flow.handle_stream_binding_unsubscribe

    # Helper operations used across protocol/media/stream flows.
    _build_context = protocol_handlers.build_context
    register_authenticated_client = protocol_handlers.register_authenticated_client
    register_client_session_key = protocol_handlers.register_client_session_key
    _default_stream_id = staticmethod(protocol_handlers.default_stream_id)
    _bind_stream_to_owner = protocol_handlers.bind_stream_to_owner
    _stream_owner_matches = protocol_handlers.stream_owner_matches
    ask_client = protocol_handlers.ask_client
    _reject_client_queries_for_owner = protocol_handlers.reject_client_queries_for_owner
    _send_auth_error = protocol_handlers.send_auth_error
    _send_invalid_media_request = protocol_handlers.send_invalid_media_request
    _is_action_allowed_for_context = staticmethod(
        protocol_handlers.is_action_allowed_for_context
    )
    _is_legacy_message_allowed_for_context = (
        protocol_handlers.is_legacy_message_allowed_for_context
    )
    _authorize_and_bind_stream = protocol_handlers.authorize_and_bind_stream

    _launch_request = request_flow.launch_request
    _response_clears_auth = staticmethod(request_flow.response_clears_auth)

    _ensure_stream_piped = stream_flow.ensure_stream_piped
    _pipe_media_stream = stream_flow.pipe_media_stream
    _close_media_stream = stream_flow.close_media_stream
    _cleanup_client = stream_flow.cleanup_client
    _on_bus_disconnect = stream_flow.on_bus_disconnect

    _extract_auth = staticmethod(protocol_auth.extract_auth_state)
    _session_scope_key = protocol_auth.session_scope_key

    def __init__(
        self,
        buses: List[BusProvider],
        streams: StreamProvider,
    ) -> None:
        self.buses = buses
        self.stream_manager = streams

        # Mutable runtime attributes initialized centrally for testability.
        init_state(self)

        # Mapping (id(bus), client_id) -> {stream_id: asyncio.Task}
        self._active_subscriptions: Dict[Tuple[int, Any], Dict[str, asyncio.Task]]
        self._authenticated_clients: Dict[
            Tuple[int, Any], Tuple[int, Optional[str], Optional[int], Optional[int]]
        ]
        self._client_session_keys: Dict[Tuple[int, Any], str]
        self._session_external_approvals: Dict[str, set[str]]
        self._stream_owners: Dict[str, Tuple[int, Any]]
        self._media_stream_tasks: Dict[str, asyncio.Task]
        self._client_media_streams: Dict[Tuple[int, Any], set[str]]
        self._stream_bindings: Dict[Tuple[int, Any, str], asyncio.Task]
        self._stream_binding_specs: Dict[Tuple[int, Any, str], Dict[str, Any]]

        runtime_callbacks.configure_bus_callbacks(self)
        self.dispatcher = ProtocolDispatcher()
        self._init_dispatcher()

    def notify_external_access_approved(
        self,
        *,
        subject_type: str,
        subject_name: str,
        resource_type: str,
        operation: str,
        target: str,
    ) -> None:
        media_flow.notify_external_access_approved(
            self,
            subject_type=subject_type,
            subject_name=subject_name,
            resource_type=resource_type,
            operation=operation,
            target=target,
        )
