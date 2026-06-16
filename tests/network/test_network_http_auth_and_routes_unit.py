from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _Logger:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(str(msg))

    def error(self, msg, *args, **kwargs):
        self.errors.append(str(msg))


def test_http_auth_helpers(monkeypatch):
    from democrai.core.infrastructure.network.http import auth as mod

    logger = _Logger()
    config_values = {}
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=logger,
            config=SimpleNamespace(get=lambda key, default=None: config_values.get(key, default)),
        ),
    )
    monkeypatch.setattr(mod, "decode_access_token", lambda token, log_expired=False: {"tok": token, "ok": True})

    assert mod.decode_token_if_present(None) is None
    assert mod.decode_token_if_present("abc") == {"tok": "abc", "ok": True}

    monkeypatch.setitem(
        sys.modules,
        "jwt",
        SimpleNamespace(decode=lambda token, options=None, algorithms=None: {"user_id": "8", "token": token}),
    )
    assert mod.decode_token_claims_unverified("x") == {"user_id": "8", "token": "x"}
    monkeypatch.setitem(sys.modules, "jwt", SimpleNamespace(decode=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad"))))
    assert mod.decode_token_claims_unverified("x") is None
    assert mod.decode_token_claims_unverified(None) is None

    req = SimpleNamespace(headers={"Authorization": "Bearer htok"}, cookies={})
    assert mod.resolve_request_token(req) == "htok"
    from democrai.core.infrastructure.network.http.cookies import auth_cookie_name

    req2 = SimpleNamespace(headers={}, cookies={auth_cookie_name(): "ctok"})
    assert mod.resolve_request_token(req2) == "ctok"
    req3 = SimpleNamespace(headers={}, cookies={})
    assert mod.resolve_request_token(req3) is None

    ws = SimpleNamespace(headers={"Authorization": "Bearer wtok"}, query_params={}, cookies={})
    assert mod.resolve_websocket_token(ws) == "wtok"
    ws2 = SimpleNamespace(headers={}, query_params={"token": "q1"}, cookies={})
    assert mod.resolve_websocket_token(ws2) == "q1"
    ws3 = SimpleNamespace(headers={}, query_params={}, cookies={auth_cookie_name(): "c1"})
    assert mod.resolve_websocket_token(ws3) == "c1"
    ws4 = SimpleNamespace(headers={}, query_params={}, cookies={})
    assert mod.resolve_websocket_token(ws4) is None

    assert mod.resolve_client_ip({"x-forwarded-for": "1.2.3.4, 8.8.8.8"}, None) == "1.2.3.4"
    assert mod.resolve_client_ip({"x-forwarded-for": "   ", "x-real-ip": "   "}, None) is None
    assert mod.resolve_client_ip({"x-real-ip": "5.6.7.8"}, None) == "5.6.7.8"
    assert mod.resolve_client_ip({}, SimpleNamespace(host="9.9.9.9")) == "9.9.9.9"
    assert mod.resolve_client_ip(object(), None) is None
    assert logger.warnings

    config_values["http.client_ip.mode"] = "trusted_proxy"
    config_values["http.client_ip.trusted_proxies"] = ["10.0.0.0/8"]
    assert (
        mod.resolve_client_ip(
            {"x-forwarded-for": "4.4.4.4"},
            SimpleNamespace(host="10.1.2.3"),
        )
        == "4.4.4.4"
    )
    assert (
        mod.resolve_client_ip(
            {"x-forwarded-for": "6.6.6.6, 4.4.4.4, 10.2.3.4"},
            SimpleNamespace(host="10.1.2.3"),
        )
        == "4.4.4.4"
    )
    assert (
        mod.resolve_client_ip(
            {"x-forwarded-for": "4.4.4.4"},
            SimpleNamespace(host="9.9.9.9"),
        )
        == "9.9.9.9"
    )
    assert (
        mod.resolve_client_ip(
            {"x-forwarded-for": "not-an-ip"},
            SimpleNamespace(host="10.1.2.3"),
        )
        == "10.1.2.3"
    )
    config_values["http.client_ip.mode"] = "never"
    assert (
        mod.resolve_client_ip(
            {"x-forwarded-for": "4.4.4.4"},
            SimpleNamespace(host="9.9.9.9"),
        )
        == "9.9.9.9"
    )

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.auth.service",
        SimpleNamespace(get_user_permissions=lambda uid: ["p1", f"uid:{uid}"]),
    )
    out = mod.auth_payload_to_response(
        {"user_id": "4", "role": "Admin", "organization_id": "2", "access_level": 1}
    )
    assert out["authenticated"] is True and out["user_id"] == 4 and out["permissions"]
    assert mod.auth_payload_to_response(None)["authenticated"] is False
    assert mod.auth_payload_to_response({"user_id": "x"})["authenticated"] is False

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.auth.service",
        SimpleNamespace(get_user_permissions=lambda _uid: (_ for _ in ()).throw(RuntimeError("boom"))),
    )
    with pytest.raises(RuntimeError):
        mod.auth_payload_to_response({"user_id": "7"})
    assert logger.errors


def test_http_routes_auth_session_and_ws(monkeypatch):
    from democrai.core.infrastructure.network.http import routes as mod

    monkeypatch.setattr(mod, "generate_session_key", lambda: "generated-session")

    app = FastAPI()
    events = []
    deleted = []
    auth_cookies = []
    session_cookies = []
    cleared = []
    cleanup_called = []
    registered_ips = []

    def _decode_token_if_present(token):
        if token == "valid":
            return {"user_id": "10", "role": "Admin", "organization_id": "2", "access_level": 1}
        return None

    mod.register_auth_session_routes(
        app,
        decode_token_if_present=_decode_token_if_present,
        decode_token_claims_unverified=lambda token: {"user_id": "99"} if token else None,
        resolve_request_token=lambda req: req.headers.get("x-token"),
        auth_payload_to_response=lambda payload: {"authenticated": bool(payload), "user": payload.get("user_id") if payload else None},
        set_session_cookie=lambda resp, key: session_cookies.append(key),
        clear_auth_cookie=lambda resp: cleared.append(True),
        set_auth_cookie=lambda resp, tok: auth_cookies.append(tok),
        resolve_client_ip=lambda headers, client: "127.0.0.1",
        observability_service=SimpleNamespace(record_auth_event=lambda **kw: events.append(kw)),
        session_cookie_name=lambda: "sess",
        delete_session_by_key=lambda key: deleted.append(key),
    )

    class _FakeWsBus:
        async def handle_connection(
            self, ws, client_id, preferred_codec, initial_messages=None
        ):
            await ws.accept()
            for message in list(initial_messages or []):
                await ws.send_json(message)
            await ws.send_json({"ok": True, "client_id": client_id, "codec": preferred_codec})
            await ws.close()

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.network.providers.bus.ws",
        SimpleNamespace(WsBusProvider=_FakeWsBus),
    )

    async def _cleanup_client(*_a, **_k):
        cleanup_called.append(True)

    network = SimpleNamespace(
        buses=[_FakeWsBus()],
        register_client_session_key=lambda *a, **k: None,
        register_client_ip=lambda *a, **k: registered_ips.append(a),
        register_authenticated_client=lambda *a, **k: None,
        _cleanup_client=_cleanup_client,
    )
    mod.register_ws_route(
        app,
        app_ctx=lambda: SimpleNamespace(network=network, dev=False),
        is_local_websocket=lambda ws: True,
        is_secure_websocket=lambda ws: False,
        decode_token_if_present=_decode_token_if_present,
        resolve_websocket_token=lambda ws: ws.query_params.get("token"),
        session_cookie_name=lambda: "sess",
        resolve_client_ip=lambda headers, client: "203.0.113.10",
    )

    client = TestClient(app)

    # GET invalid token -> expired path
    client.cookies.set("sess", "s1")
    r = client.get("/auth/session", headers={"x-token": "invalid"})
    assert r.status_code == 401 and r.json()["authenticated"] is False
    assert deleted == ["s1"] and events

    # GET valid token path
    r2 = client.get("/auth/session", headers={"x-token": "valid"})
    assert r2.status_code == 200 and r2.json()["authenticated"] is True
    assert r2.json()["jwt"] == "valid"
    before_session_cookie_calls = len(session_cookies)
    client.cookies.set("sess", "existing")
    r2b = client.get("/auth/session", headers={"x-token": "valid"})
    assert r2b.status_code == 200 and r2b.json()["authenticated"] is True
    assert r2b.json()["jwt"] == "valid"
    assert len(session_cookies) == before_session_cookie_calls

    # POST invalid token: body.session_key must be ignored
    r3 = client.post("/auth/session", json={"jwt": "invalid", "session_key": "s2"})
    assert r3.status_code == 401 and r3.json()["authenticated"] is False
    assert session_cookies[-1] == "existing"
    assert "s2" not in session_cookies

    # POST valid token: body.session_key must be ignored
    r4 = client.post("/auth/session", json={"jwt": "valid"})
    assert r4.status_code == 200 and r4.json()["authenticated"] is True
    assert r4.json()["jwt"] == "valid"
    assert session_cookies[-1] == "existing"
    assert "s2" not in session_cookies
    assert auth_cookies and session_cookies and cleared

    # DELETE session
    r5 = client.delete("/auth/session", headers={"x-token": "valid"})
    assert r5.status_code == 200 and r5.json()["authenticated"] is False

    # WS route + cleanup client
    with client.websocket_connect("/ws?token=valid&codec=json") as ws:
        msg = ws.receive_json()
        assert msg["jwt"] == "valid"
        msg = ws.receive_json()
        assert msg["ok"] is True
    assert cleanup_called
    assert registered_ips and registered_ips[0][-1] == "203.0.113.10"

    # WS fallback when no bus provider
    app2 = FastAPI()
    mod.register_ws_route(
        app2,
        app_ctx=lambda: SimpleNamespace(network=SimpleNamespace(buses=[]), dev=True),
        is_local_websocket=lambda ws: True,
        is_secure_websocket=lambda ws: True,
        decode_token_if_present=_decode_token_if_present,
        resolve_websocket_token=lambda ws: None,
        session_cookie_name=lambda: "sess",
        resolve_client_ip=lambda *_a, **_k: None,
    )
    client2 = TestClient(app2)
    with client2.websocket_connect("/ws") as ws:
        error_msg = ws.receive_json()
        assert error_msg["type"] == "error"

    # WS fallback when network is None (branch where `if network:` is false)
    app2b = FastAPI()
    mod.register_ws_route(
        app2b,
        app_ctx=lambda: SimpleNamespace(network=None, dev=True),
        is_local_websocket=lambda ws: True,
        is_secure_websocket=lambda ws: True,
        decode_token_if_present=_decode_token_if_present,
        resolve_websocket_token=lambda ws: None,
        session_cookie_name=lambda: "sess",
        resolve_client_ip=lambda *_a, **_k: None,
    )
    client2b = TestClient(app2b)
    with client2b.websocket_connect("/ws") as ws:
        error_msg2 = ws.receive_json()
        assert error_msg2["type"] == "error"

    # ws branch: network exists but no register_client_session_key attr, payload none, bus mismatch then match
    app6 = FastAPI()
    class _OtherBus:
        pass
    class _RealWsBus:
        async def handle_connection(
            self, ws, client_id, preferred_codec, initial_messages=None
        ):
            await ws.accept()
            for message in list(initial_messages or []):
                await ws.send_json(message)
            await ws.send_json({"ok": True, "client_id": client_id})
            await ws.close()
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.network.providers.bus.ws",
        SimpleNamespace(WsBusProvider=_RealWsBus),
    )
    cleanup2 = []
    network6 = SimpleNamespace(
        buses=[_OtherBus(), _RealWsBus()],
        register_authenticated_client=lambda *a, **k: cleanup2.append("auth"),
        _cleanup_client=lambda *_a, **_k: asyncio.sleep(0),
    )
    mod.register_ws_route(
        app6,
        app_ctx=lambda: SimpleNamespace(network=network6, dev=True),
        is_local_websocket=lambda ws: True,
        is_secure_websocket=lambda ws: True,
        decode_token_if_present=lambda _t: None,
        resolve_websocket_token=lambda ws: None,
        session_cookie_name=lambda: "sess",
        resolve_client_ip=lambda *_a, **_k: None,
    )
    client6 = TestClient(app6)
    with client6.websocket_connect("/ws") as ws:
        assert ws.receive_json()["ok"] is True
    assert not cleanup2

    # cleanup error branch in _delete_session_for_request
    app3 = FastAPI()
    events3 = []
    mod.register_auth_session_routes(
        app3,
        decode_token_if_present=lambda _t: None,
        decode_token_claims_unverified=lambda _t: {"user_id": "1"},
        resolve_request_token=lambda req: req.headers.get("x-token"),
        auth_payload_to_response=lambda payload: {"authenticated": bool(payload)},
        set_session_cookie=lambda *_a, **_k: None,
        clear_auth_cookie=lambda *_a, **_k: None,
        set_auth_cookie=lambda *_a, **_k: None,
        resolve_client_ip=lambda *_a, **_k: "127.0.0.1",
        observability_service=SimpleNamespace(record_auth_event=lambda **kw: events3.append(kw)),
        session_cookie_name=lambda: "sess",
        delete_session_by_key=lambda _k: (_ for _ in ()).throw(RuntimeError("del-boom")),
    )
    client3 = TestClient(app3)
    client3.cookies.set("sess", "x")
    _ = client3.get("/auth/session", headers={"x-token": "invalid"})
    assert any(item.get("event_type") == "auth.session.cleanup_error" for item in events3)

    # delete_session_by_key not callable branch
    app4 = FastAPI()
    mod.register_auth_session_routes(
        app4,
        decode_token_if_present=lambda _t: None,
        decode_token_claims_unverified=lambda _t: None,
        resolve_request_token=lambda req: req.headers.get("x-token"),
        auth_payload_to_response=lambda payload: {"authenticated": bool(payload)},
        set_session_cookie=lambda *_a, **_k: None,
        clear_auth_cookie=lambda *_a, **_k: None,
        set_auth_cookie=lambda *_a, **_k: None,
        resolve_client_ip=lambda *_a, **_k: None,
        observability_service=SimpleNamespace(record_auth_event=lambda **kw: None),
        session_cookie_name=lambda: "sess",
        delete_session_by_key=None,
    )
    client4 = TestClient(app4)
    assert client4.delete("/auth/session").status_code == 200

    # websocket secure-required branch
    app5 = FastAPI()
    mod.register_ws_route(
        app5,
        app_ctx=lambda: SimpleNamespace(network=SimpleNamespace(buses=[]), dev=False),
        is_local_websocket=lambda ws: False,
        is_secure_websocket=lambda ws: False,
        decode_token_if_present=lambda _t: None,
        resolve_websocket_token=lambda ws: None,
        session_cookie_name=lambda: "sess",
        resolve_client_ip=lambda *_a, **_k: None,
    )
    client5 = TestClient(app5)
    with pytest.raises(Exception):
        with client5.websocket_connect("/ws"):
            pass
