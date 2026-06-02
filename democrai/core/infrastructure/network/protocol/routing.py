from __future__ import annotations


PROTOCOL_HANDLER_METHODS: tuple[tuple[str, str], ...] = (
    ("userAction", "_handle_action"),
    ("bindingAction", "_handle_action"),
    ("backgroundTaskResponse", "_handle_task_response"),
    ("backgroundTaskCancel", "_handle_task_cancel"),
    ("backgroundTaskGet", "_handle_task_get"),
    ("clientQueryResult", "_handle_client_query_result"),
    ("stream_id", "_handle_stream_piping"),
    ("mediaResolve", "_handle_media_resolve"),
    ("mediaStreamOpen", "_handle_media_stream_open"),
    ("mediaStreamClose", "_handle_media_stream_close"),
    ("streamBindingSubscribe", "_handle_stream_binding_subscribe"),
    ("streamBindingUnsubscribe", "_handle_stream_binding_unsubscribe"),
)

DEFAULT_PROTOCOL_HANDLER_METHOD = "_handle_legacy_launch"
