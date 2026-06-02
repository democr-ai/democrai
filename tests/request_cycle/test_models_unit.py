from democrai.core.application.request_cycle import RequestEnvelope, infer_request_kind


def test_infer_request_kind_covers_supported_protocol_shapes():
    assert infer_request_kind({"userAction": {"name": "go"}}) == "userAction"
    assert infer_request_kind({"bindingAction": {"name": "bind"}}) == "bindingAction"
    assert infer_request_kind({"type": "ping"}) == "ping"
    assert infer_request_kind({}) == "unknown"


def test_request_envelope_normalizes_message_shape():
    envelope = RequestEnvelope.from_message(
        {"request_id": "req-1", "userAction": {"name": "demo.run"}, "stream_id": "s1"}
    )

    assert envelope.request_id == "req-1"
    assert envelope.kind == "userAction"
    assert envelope.has_user_action is True
    assert envelope.has_binding_action is False
    assert envelope.is_ping is False
    assert envelope.is_init is False
    assert envelope.message["stream_id"] == "s1"


def test_request_envelope_flags_ping_and_init_paths():
    ping = RequestEnvelope.from_message({"request_id": "req-ping", "type": "ping"})
    init = RequestEnvelope.from_message({"request_id": "req-init", "type": "init"})
    empty = RequestEnvelope.from_message({})

    assert ping.is_ping is True
    assert ping.is_init is False
    assert init.is_ping is False
    assert init.is_init is True
    assert empty.is_init is True
