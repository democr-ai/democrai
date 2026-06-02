from democrai.core.application import notifications


def test_apply_external_access_decision_uses_request_session_key(monkeypatch):
    captured = {}

    def approve_for_session(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        notifications.external_access,
        "approve_for_session",
        approve_for_session,
    )

    notifications.apply_external_access_decision(
        {
            "subject_type": "module",
            "subject_name": "system",
            "resource_type": "network",
            "operation": "connect",
            "target": "example.test:443",
            "decision": "session",
            "request_session_key": "origin-session",
            "session_key": "desktop-client-session",
        }
    )

    assert captured["session_key"] == "origin-session"

