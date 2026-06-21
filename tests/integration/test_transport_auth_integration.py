import asyncio
import sys
import types

import pytest

from democrai.core.infrastructure.network.http import build_fastapi_app
from democrai.core.infrastructure.network.providers.bus.ipc import IpcBusProvider
from democrai.core.infrastructure.network.providers.bus.ws import WsBusProvider
from democrai.core.runtime.foundation.app import req_ctx, app_ctx, set_req_ctx, reset_req_ctx, RequestContext


class _CoreStub:
    async def handle(self, payload):
        ctx = req_ctx()
        return {
            "type": payload.get("type"),
            "user": ctx.user,
            "role": ctx.role,
            "channel": ctx.channel,
        }


class _BusWrapper:
    def __init__(self, buses):
        self.buses = buses


class _Logger:
    def __init__(self):
        self.errors = []
        self.debugs = []
        self.infos = []

    def info(self, msg, *args, **kwargs):
        self.infos.append(msg)

    def error(self, msg, *args, **kwargs):
        self.errors.append(msg)

    def debug(self, msg, *args, **kwargs):
        self.debugs.append(msg)

    def warning(self, msg, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        self.debugs.append(msg)


class _Cfg:
    def get(self, key, default=None):
        defaults = {
            "network.ws.codec": "json",
            "network.ws.allow_client_codec_override": True,
        }
        return defaults.get(key, default)


class _FakeWebSocket:
    def __init__(self, packets):
        self._packets = list(packets)
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive(self):
        return self._packets.pop(0)

    async def send_text(self, payload):
        return None

    async def send_bytes(self, payload):
        return None


class _ByteArray:
    def __init__(self, b: bytes):
        self._b = b

    def data(self):
        return self._b


class _FakeSocket:
    def __init__(self, sid: int, chunks: bytes):
        self._sid = sid
        self._buf = bytearray()
        self._chunks = chunks
        self.deleted = False

    def readAll(self):
        c = self._chunks
        self._chunks = b""
        return _ByteArray(c)

    def deleteLater(self):
        self.deleted = True

    def close(self):
        self.deleted = True


@pytest.mark.integration
def test_http_ping_is_available_and_rpc_is_not_registered():
    app_ctx().logger = _Logger()
    app_ctx().network = _BusWrapper(buses=[])
    app_ctx().config = types.SimpleNamespace(get=lambda _k, _d=None: "secure-secret-key-123456789012345678" if _k == "auth.jwt_secret" else _d)

    app = build_fastapi_app(_CoreStub())
    ping_ep = next(r.endpoint for r in app.routes if getattr(r, "path", None) == "/ping")
    assert all(getattr(r, "path", None) != "/rpc" for r in app.routes)

    # no-auth context
    tk1 = set_req_ctx(
        RequestContext(
            app=app_ctx(),
            request_id="r-noauth",
            user=None,
            role=None,
            organization_id=None,
            access_level=None,
            channel="http",
        )
    )
    try:
        ping = asyncio.run(ping_ep())
    finally:
        reset_req_ctx(tk1)

    assert ping["type"] == "ping"
    assert ping["user"] is None


@pytest.mark.integration
def test_ws_provider_integration_flow():
    app_ctx().logger = _Logger()
    app_ctx().config = _Cfg()

    received = []
    disconnected = []
    bus = WsBusProvider()
    bus.on_message = lambda client_id, msg: received.append((client_id, msg))
    bus.on_disconnect = lambda client_id: disconnected.append(client_id)

    ws = _FakeWebSocket(
        [
            {"text": '{"type":"ping"}', "bytes": None},
            {"type": "websocket.disconnect", "text": None, "bytes": None},
        ]
    )

    asyncio.run(bus.handle_connection(ws, "ws1", preferred_codec="json"))
    assert ws.accepted is True
    assert received[0] == ("ws1", {"type": "init"})
    assert received[1][0] == "ws1"
    assert received[1][1]["type"] == "ping"
    assert "_ws_decode_ms" in received[1][1]
    assert "_ws_handoff_started_at" in received[1][1]
    assert disconnected == ["ws1"]


@pytest.mark.integration
def test_ipc_provider_json_framing_flow():
    app_ctx().logger = _Logger()
    received = []
    disconnected = []
    provider = IpcBusProvider(
        "integration_bus",
        on_message=lambda sid, msg: received.append((sid, msg)),
        on_disconnect=lambda sid: disconnected.append(sid),
    )

    sock = _FakeSocket(17, b'{"x":1}\n{"y":2}\n')
    provider._sockets[17] = sock  # type: ignore[assignment]
    provider._buffers[17] = bytearray()
    provider._handle_chunk(17, sock._chunks)  # type: ignore[arg-type]
    provider._drop_client(17, notify=True)  # type: ignore[arg-type]

    assert received == [(17, {"x": 1}), (17, {"y": 2})]
    assert disconnected == [17]
    assert sock.deleted is True


@pytest.mark.integration
def test_login_and_permission_flow():
    # module auth action imports "sdk" module; provide test shim
    def _identity_action(_name=None):
        def deco(fn):
            return fn

        return deco

    class _SdkModule:
        def event_slot(self, *_args, **_kwargs):
            return _identity_action()

    sys.modules.setdefault(
        "sdk",
        types.SimpleNamespace(action=_identity_action, sdk=_SdkModule()),
    )
    from modules.auth.actions import login

    class _Users:
        def verify(self, username, password):
            return username == "fabio" and password == "pw"

        def get_info(self, username):
            return {"id": 1, "username": username, "roles": ["Admin"]}

    class _Auth:
        def __init__(self, users):
            self.users = users

        def create_token(self, payload, expires_delta=None):
            from democrai.core.application.auth.jwt import create_access_token
            return create_access_token(payload, expires_delta)

        def login(self, username, password):
            if not self.users.verify(username, password):
                return {"ok": False, "error": "invalid_credentials", "details": "Invalid credentials."}
            user_info = self.users.get_info(username)
            token_payload = {
                "user_id": user_info.get("id"),
                "username": user_info.get("username") or username,
                "role": "super",
                "access_level": 3,
                "organization_id": None,
            }
            return {
                "ok": True,
                "user_id": user_info.get("id"),
                "user_info": user_info,
                "token_payload": token_payload,
                "token": self.create_token(token_payload),
            }

    class _SDK:
        def __init__(self):
            users = _Users()
            self.models = types.SimpleNamespace(users=users)
            self.auth = _Auth(users)
            self.system = types.SimpleNamespace(log=lambda *_a, **_k: None)
            self.effects = types.SimpleNamespace(
                render=lambda: {"type": "render"},
                refresh_modules=lambda: {"type": "refresh_modules"},
                set_jwt=lambda token: {"type": "set_jwt", "token": token},
                respond=lambda *effects: {"effects": list(effects)},
                ui_messages=lambda messages: {"type": "ui_messages", "messages": messages},
            )
            self.events = types.SimpleNamespace(emit=self._emit)
            self.pages = types.SimpleNamespace(get_post_login_redirect_path=lambda: "/dashboard/index")
            self.i18n = types.SimpleNamespace(get_user_language=lambda _user_id: "en")

        async def _emit(self, *_args, **_kwargs):
            return None

    app_ctx().config = types.SimpleNamespace(get=lambda _k, _d=None: "secure-secret-key-123456789012345678" if _k == "auth.jwt_secret" else _d)
    session = {}
    sdk = _SDK()
    out = asyncio.run(
        login(
            ctx={"login_form": {"username": "fabio", "password": "pw"}},
            session=session,
            module_sdk=sdk,
        )
    )

    assert "effects" in out
    assert session["user"]["username"] == "fabio"
    assert session["user"]["role"] == "super"
    assert session["user"]["access_level"] == 3
