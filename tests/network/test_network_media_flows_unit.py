from __future__ import annotations

import asyncio
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from democrai.core.runtime.foundation.app import RequestContext, reset_req_ctx, set_req_ctx


@contextmanager
def _request_context(*, user=1, organization_id=2, session_key="sess", request_id="r"):
    token = set_req_ctx(
        RequestContext(
            app=None,
            request_id=request_id,
            user=user,
            role="User" if user is not None else None,
            organization_id=organization_id,
            access_level=None,
            channel="bus",
            session_key=session_key,
        )
    )
    try:
        yield
    finally:
        reset_req_ctx(token)


@pytest.mark.asyncio
async def test_media_flows_paths(monkeypatch):
    from democrai.core.infrastructure.network.flows import media as mod
    import democrai.core.application.handler.services.runtime.access as access_mod

    sent = []
    auth_errors = []
    invalid_errors = []
    dbg = []
    notif = []
    closed = []

    bus = SimpleNamespace(send=lambda cid, payload: sent.append((cid, payload)))
    network = SimpleNamespace(
        _authenticated_clients={(1, "c1"): (1, "Super", None, None), (2, "c2"): (1, "Super", None, None), (3, "c3"): (2, "User", 7, None)},
        connection_registry=SimpleNamespace(
            get_connections=lambda uid: [(bus, "c1"), (bus, "c2")] if uid == 1 else []
        ),
        _send_auth_error=lambda _b, _c, _m, e: auth_errors.append(e),
        _send_invalid_media_request=lambda _b, _c, _m: invalid_errors.append(True),
        _bind_stream_to_owner=lambda sid, **kw: bound.append((sid, kw)),
        _ensure_stream_piped=lambda _b, _c, sid: ensured.append(sid),
        _client_media_streams={},
        _media_stream_tasks={},
        _stream_owners={"ok-stream": (id(bus), "c1")},
        _stream_owner_matches=lambda sid, **kw: sid == "ok-stream",
        _close_media_stream=lambda _b, _c, sid: _close_stream(sid),
        _pipe_media_stream=lambda sid, client, upstream: _pipe_stream(sid, client, upstream),
    )
    bound = []
    ensured = []
    pipe_calls = []

    async def _close_stream(stream_id):
        closed.append(stream_id)

    async def _pipe_stream(stream_id, client, upstream):
        pipe_calls.append((stream_id, client, upstream))

    monkeypatch.setattr(mod, "debug_media_flow", lambda *a, **k: dbg.append((a, k)))
    monkeypatch.setattr(mod, "push_notifications_update", lambda _bus, _cid, count=0: notif.append(count))
    monkeypatch.setattr(mod, "get_pending_access_requests", lambda: [{}] * 5)
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.auth.roles",
        SimpleNamespace(is_super_role=lambda role: role == "Super"),
    )

    class _Req:
        def __init__(self, module_name="m1", url="https://x", client_generation=3, force_refresh=False):
            self.module_name = module_name
            self.url = url
            self.client_generation = client_generation
            self.force_refresh = force_refresh

    parse_calls = []

    def _parse(payload, include_force_refresh=False):
        parse_calls.append((payload, include_force_refresh))
        if payload == "bad":
            raise ValueError("invalid")
        return _Req(force_refresh=include_force_refresh)

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.handler.services.runtime.media_requests",
        SimpleNamespace(
            parse_external_media_request=_parse,
            build_external_media_error=lambda **kw: {"err": kw["error"], "code": kw.get("error_code"), "gen": kw["client_generation"]},
        ),
    )

    access = {"allowed": True, "code": None, "message": ""}

    def _check_access(**kwargs):
        return SimpleNamespace(**access)

    async def _resolve(*_a, **_k):
        return {"path": "/tmp/x", "cache_hit": True}

    async def _open_stream(*_a, **_k):
        return ("client", "upstream", {"content_type": "image/png"})

    monkeypatch.setattr(access_mod, "check_external_media_access", lambda *_a, **_k: _check_access())
    monkeypatch.setattr(access_mod, "resolve_external_media_to_cache", _resolve)
    monkeypatch.setattr(access_mod, "open_external_media_stream", _open_stream)

    # _parse_media_request + _send_media_error
    assert mod._parse_media_request(network, bus, "c1", {"mediaResolve": {}}, "mediaResolve")
    assert mod._parse_media_request(network, bus, "c1", {"mediaResolve": "bad"}, "mediaResolve") is None
    assert invalid_errors
    mod._send_media_error(
        bus,
        "c1",
        {"request_id": "r1"},
        message_type="media_resolved",
        payload_key="mediaResolved",
        error="boom",
        module_name="m1",
        url="https://x",
        client_generation=9,
        error_code="E1",
    )
    assert sent[-1][1]["mediaResolved"]["code"] == "E1"

    # push notifications helper and exported notifier
    mod._push_notifications_to_super_users(network)
    assert notif and len(notif) >= 1
    mod.notify_external_access_approved(network)
    assert len(notif) >= 2
    # Swallow push notification exception branch.
    monkeypatch.setattr(
        mod,
        "push_notifications_update",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("push-fail")),
    )
    mod._push_notifications_to_super_users(network)

    # resolve unauthenticated
    with _request_context(user=None, organization_id=None, session_key=None):
        await mod.handle_media_resolve(network, bus, "c1", {"request_id": "r", "mediaResolve": {}})
    assert auth_errors

    # resolve parse invalid
    invalid_errors.clear()
    with _request_context():
        await mod.handle_media_resolve(network, bus, "c1", {"request_id": "r", "mediaResolve": "bad"})
    assert invalid_errors

    # resolve denied + not_enabled triggers notifications
    access.update({"allowed": False, "code": "not_enabled", "message": "denied"})
    sent.clear()
    with _request_context():
        await mod.handle_media_resolve(network, bus, "c1", {"request_id": "r2", "mediaResolve": {}})
    assert sent[-1][1]["type"] == "media_resolved"
    assert sent[-1][1]["mediaResolved"]["code"] == "not_enabled"

    # resolve denied generic
    access.update({"allowed": False, "code": "forbidden", "message": "nope"})
    with _request_context():
        await mod.handle_media_resolve(network, bus, "c1", {"request_id": "r3", "mediaResolve": {}})
    assert sent[-1][1]["mediaResolved"]["code"] == "forbidden"

    # resolve success
    access.update({"allowed": True, "code": None, "message": ""})
    sent.clear()
    with _request_context():
        await mod.handle_media_resolve(network, bus, "c1", {"request_id": "r4", "mediaResolve": {}})
    assert sent[-1][1]["type"] == "media_resolved"
    assert sent[-1][1]["mediaResolved"]["client_generation"] == 3

    # resolve exception
    async def _resolve_boom(*_a, **_k):
        raise RuntimeError("resolver boom")

    monkeypatch.setattr(access_mod, "resolve_external_media_to_cache", _resolve_boom)
    sent.clear()
    with _request_context():
        await mod.handle_media_resolve(network, bus, "c1", {"request_id": "r5", "mediaResolve": {}})
    assert sent[-1][1]["mediaResolved"]["err"] == "resolver boom"

    # stream open unauthenticated
    with _request_context(user=None, organization_id=None, session_key=None):
        await mod.handle_media_stream_open(network, bus, "c1", {"request_id": "o1", "mediaStreamOpen": {}})
    assert auth_errors

    # stream open parse invalid
    invalid_errors.clear()
    with _request_context():
        await mod.handle_media_stream_open(network, bus, "c1", {"request_id": "o2", "mediaStreamOpen": "bad"})
    assert invalid_errors

    # stream open denied not_enabled
    access.update({"allowed": False, "code": "not_enabled", "message": "denied"})
    sent.clear()
    with _request_context():
        await mod.handle_media_stream_open(network, bus, "c1", {"request_id": "o3", "mediaStreamOpen": {}})
    assert sent[-1][1]["type"] == "media_stream_error"

    # stream open denied generic should not trigger super-user notifications
    notif_before = len(notif)
    access.update({"allowed": False, "code": "forbidden", "message": "denied"})
    with _request_context():
        await mod.handle_media_stream_open(network, bus, "c1", {"request_id": "o3b", "mediaStreamOpen": {}})
    assert sent[-1][1]["mediaStreamError"]["code"] == "forbidden"
    assert len(notif) == notif_before

    # stream open exception from open_external_media_stream
    access.update({"allowed": True, "code": None, "message": ""})

    async def _open_boom(*_a, **_k):
        raise RuntimeError("open boom")

    monkeypatch.setattr(access_mod, "resolve_external_media_to_cache", _resolve)
    monkeypatch.setattr(access_mod, "open_external_media_stream", _open_boom)
    sent.clear()
    with _request_context():
        await mod.handle_media_stream_open(network, bus, "c1", {"request_id": "o4", "mediaStreamOpen": {}})
    assert sent[-1][1]["mediaStreamError"]["err"] == "open boom"

    # stream open success
    monkeypatch.setattr(access_mod, "open_external_media_stream", _open_stream)
    monkeypatch.setattr(mod, "uuid4", lambda: SimpleNamespace(hex="abcd1234"))
    created = []

    class _FakeTask:
        def cancel(self):
            return None

    monkeypatch.setattr(asyncio, "create_task", lambda coro: (coro.close(), created.append(True), _FakeTask())[2])
    sent.clear()
    with _request_context():
        await mod.handle_media_stream_open(network, bus, "c1", {"request_id": "o5", "mediaStreamOpen": {}})
    assert bound and ensured and created
    assert sent[-1][1]["type"] == "media_stream_opened"
    stream_id = sent[-1][1]["mediaStreamOpened"]["stream_id"]
    assert stream_id in network._media_stream_tasks
    assert stream_id in network._client_media_streams[(id(bus), "c1")]

    # stream close paths
    with _request_context(user=None, organization_id=None, session_key=None):
        await mod.handle_media_stream_close(network, bus, "c1", {"request_id": "c1", "mediaStreamClose": {}})
    assert auth_errors

    invalid_errors.clear()
    with _request_context():
        await mod.handle_media_stream_close(network, bus, "c1", {"request_id": "c2", "mediaStreamClose": "x"})
        await mod.handle_media_stream_close(network, bus, "c1", {"request_id": "c3", "mediaStreamClose": {}})
    assert len(invalid_errors) == 2

    with _request_context():
        await mod.handle_media_stream_close(network, bus, "c1", {"request_id": "c4", "mediaStreamClose": {"stream_id": "nope"}})
    assert auth_errors[-1] == "unauthorized_stream"

    with _request_context():
        await mod.handle_media_stream_close(network, bus, "c1", {"request_id": "c5", "mediaStreamClose": {"stream_id": "ok-stream"}})
    assert closed and closed[-1] == "ok-stream"
    assert dbg
