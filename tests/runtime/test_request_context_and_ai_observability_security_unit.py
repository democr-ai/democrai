from __future__ import annotations

from types import SimpleNamespace

from democrai.core.application.ai.engine.runtime.environment import (
    runtime_config_public,
    runtime_config_signature,
)
from democrai.core.application.ai.engine.runtime.invocation import record_usage_or_fail
from democrai.core.runtime.foundation.app import (
    RequestContext,
    current_request_context_payload,
    request_context_from_dict,
    reset_req_ctx,
    set_req_ctx,
)


def _request_context() -> RequestContext:
    return RequestContext(
        request_id="req-original",
        user=7,
        role="admin",
        organization_id=11,
        access_level=90,
        channel="ws",
        session_key="sess-original",
        client_ip="127.0.0.1",
        action_name="system.install_engine",
        module_name="system",
        stream_id="stream-1",
    )


def test_request_context_roundtrip_preserves_original_request_fields():
    token = set_req_ctx(_request_context())
    try:
        payload = current_request_context_payload()
    finally:
        reset_req_ctx(token)

    restored = request_context_from_dict(payload)
    assert restored is not None
    assert restored.request_id == "req-original"
    assert restored.user == 7
    assert restored.organization_id == 11
    assert restored.session_key == "sess-original"
    assert restored.action_name == "system.install_engine"
    assert restored.module_name == "system"


def test_install_events_include_original_request_context(monkeypatch):
    import democrai.core.application.ai.engine.install_events as engine_events
    import democrai.core.application.knowledge.extractor.install_events as extractor_events

    monkeypatch.setattr(engine_events, "get_engine_manifest", lambda _engine_id: {})
    monkeypatch.setattr(extractor_events, "get_extractor_manifest", lambda _extractor_id: {})
    monkeypatch.setattr(engine_events, "get_runtime_node_id", lambda: "node-1")
    monkeypatch.setattr(extractor_events, "get_runtime_node_id", lambda: "node-1")

    token = set_req_ctx(_request_context())
    try:
        engine_event = engine_events.build_install_requested_event(engine_id="demo")
        extractor_event = extractor_events.build_install_requested_event(
            extractor_id="docling"
        )
    finally:
        reset_req_ctx(token)

    assert engine_event["request_context"]["request_id"] == "req-original"
    assert engine_event["request_context"]["session_key"] == "sess-original"
    assert extractor_event["request_context"]["request_id"] == "req-original"
    assert extractor_event["request_context"]["session_key"] == "sess-original"


def test_runtime_config_signature_and_usage_metadata_do_not_expose_secrets(monkeypatch):
    config = {
        "model": "gpt-test",
        "api_key": "sk-secret",
        "password": "pw-secret",
        "temperature": 0.2,
        "test_results": {"raw": "ignored"},
    }
    public_config = runtime_config_public(config)
    signature = runtime_config_signature(config)
    assert public_config == {"model": "gpt-test", "temperature": 0.2}
    assert "sk-secret" not in signature
    assert len(signature) == 64

    calls = []
    import democrai.core.application.observability.service as observability_mod

    monkeypatch.setattr(
        observability_mod.observability_service,
        "record_ai_model_usage",
        lambda **kwargs: calls.append(kwargs) or {"id": 1},
    )
    provider = SimpleNamespace(
        engine_row_id=3,
        model_registry_id=5,
        engine_id="openai",
        config=config,
    )
    record_usage_or_fail(
        provider,
        method="generate_completion",
        result={"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
        duration_ms=12.5,
        success=True,
        error=None,
    )
    metadata = calls[0]["metadata"]
    assert metadata["config_signature"] == signature
    assert "sk-secret" not in str(metadata)
    assert "pw-secret" not in str(metadata)
