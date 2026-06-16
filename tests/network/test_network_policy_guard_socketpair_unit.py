from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.network import policy_guard as mod


@pytest.fixture(autouse=True)
def _reset_policy_state():
    mod._ORIGINALS.clear()
    mod._ACTIVE = False
    mod._ACTIVE_COUNT = 0
    mod._STATE.set(None)
    yield
    mod._ORIGINALS.clear()
    mod._ACTIVE = False
    mod._ACTIVE_COUNT = 0
    mod._STATE.set(None)


def _deny_all(monkeypatch):
    monkeypatch.setattr(mod, "_network_access_allowed", lambda *a, **k: False)
    monkeypatch.setattr(
        mod,
        "check_external_access",
        lambda **k: SimpleNamespace(
            allowed=False, requires_approval=True, message="approve", code=""
        ),
    )


def test_socketpair_depth_exempts_loopback_for_subject(monkeypatch):
    # A subject whose loopback access is normally enforced.
    mod._STATE.set({"subject_type": "extractor", "subject_name": "ai_image"})
    _deny_all(monkeypatch)

    # Without the socketpair depth, a subject loopback connect is denied.
    with pytest.raises(mod.ExternalAccessApprovalRequired):
        mod._check_target("127.0.0.1", 1234, operation="connect")

    # Inside socket.socketpair() (depth > 0), the loopback self-pipe is exempt.
    token = mod._SOCKETPAIR_DEPTH.set(1)
    try:
        mod._check_target("127.0.0.1", 1234, operation="connect")  # must not raise
    finally:
        mod._SOCKETPAIR_DEPTH.reset(token)

    # The exemption is loopback-only: a non-loopback target stays blocked.
    token = mod._SOCKETPAIR_DEPTH.set(1)
    try:
        with pytest.raises(mod.ExternalAccessApprovalRequired):
            mod._check_target("1.1.1.1", 443, operation="connect")
    finally:
        mod._SOCKETPAIR_DEPTH.reset(token)


def test_real_socketpair_works_under_active_guard_with_subject(monkeypatch):
    # End-to-end: the guard is active (socket.* patched) with a subject and no
    # loopback rules. socket.socketpair() must succeed (its emulated loopback
    # connect on Windows is exempted), while a real external connect still raises.
    _deny_all(monkeypatch)
    with mod.network_policy_context(subject_name="ai_image", subject_type="extractor"):
        a, b = socket.socketpair()
        a.close()
        b.close()

        external = socket.socket()
        try:
            with pytest.raises(mod.ExternalAccessApprovalRequired):
                external.connect(("1.1.1.1", 443))
        finally:
            external.close()

    # Patch restored on exit.
    assert "socket.socketpair" not in mod._ORIGINALS
