import asyncio
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.network.contracts.bus import BusProvider
from democrai.core.infrastructure.network.contracts.stream import StreamProvider
from democrai.core.infrastructure.network.factory._registry import _RegistryFactory
from democrai.core.infrastructure.network.factory.stream import StreamProviderFactory
from democrai.core.infrastructure.network.flows.legacy_requests import handle_legacy_launch
from democrai.core.infrastructure.network.protocol.routing import (
    DEFAULT_PROTOCOL_HANDLER_METHOD,
    PROTOCOL_HANDLER_METHODS,
)
from democrai.core.runtime.foundation.app import RequestContext, app_ctx, reset_req_ctx, set_req_ctx


class _BusImpl(BusProvider):
    def __init__(self):
        self.sent = []

    def start(self) -> None:
        self.sent.append("start")

    def stop(self) -> None:
        self.sent.append("stop")

    def send(self, client_id, message) -> None:
        self.sent.append(("send", client_id, message))

    def broadcast(self, message) -> None:
        self.sent.append(("broadcast", message))


class _StreamImpl(StreamProvider):
    def __init__(self):
        self.queues = {}

    def subscribe(self, channel_id: str):
        q = asyncio.Queue()
        self.queues.setdefault(channel_id, []).append(q)
        return q

    def unsubscribe(self, channel_id: str, queue):
        if channel_id in self.queues and queue in self.queues[channel_id]:
            self.queues[channel_id].remove(queue)

    async def broadcast(self, channel_id: str, data):
        for queue in list(self.queues.get(channel_id, [])):
            queue.put_nowait(data)


def _set_request_context():
    return set_req_ctx(
        RequestContext(
            request_id="test",
            user=1,
            role="super",
            organization_id=None,
            access_level=1,
            channel="ws",
            app=app_ctx(),
            session_key="sess-test",
        )
    )


def test_abstract_contracts_have_expected_shape():
    bus = _BusImpl()
    bus.start()
    bus.send("c1", {"ok": True})
    bus.broadcast({"all": 1})
    bus.stop()
    assert bus.sent[0] == "start"
    assert bus.sent[-1] == "stop"

    stream = _StreamImpl()
    q = stream.subscribe("a")
    asyncio.run(stream.broadcast("a", {"x": 1}))
    assert q.get_nowait() == {"x": 1}
    stream.unsubscribe("a", q)


def test_registry_factory_supports_type_string_callable_and_fallback(monkeypatch):
    class _Default:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _Alt:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _ByPath:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    warnings = []
    monkeypatch.setattr(
        "democrai.core.infrastructure.network.factory._registry.app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(warning=lambda msg: warnings.append(msg))),
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.network.factory._registry.import_module",
        lambda _name: SimpleNamespace(ByPath=_ByPath),
    )

    factory = _RegistryFactory("default", _Default)
    factory.register("alt", _Alt)
    factory.register("by_path", "anything:ByPath")
    factory.register("from_callable", lambda: _Alt)

    assert isinstance(factory.create("alt", v=1), _Alt)
    assert isinstance(factory.create("by_path", v=2), _ByPath)
    assert isinstance(factory.create("from_callable", v=3), _Alt)
    fallback = factory.create("missing", v=4)
    assert isinstance(fallback, _Default)
    assert warnings and "Falling back" in warnings[0]


def test_registry_factory_rejects_non_class_resolver():
    factory = _RegistryFactory("default", lambda: dict)
    factory.register("bad", lambda: object())
    with pytest.raises(TypeError):
        factory.create("bad")


def test_stream_provider_factory_registration():
    class _CustomStream(StreamProvider):
        def subscribe(self, channel_id: str):
            return asyncio.Queue()

        def unsubscribe(self, channel_id: str, queue):
            return None

        async def broadcast(self, channel_id: str, data):
            return None

    StreamProviderFactory.register("custom", _CustomStream)

    stream = StreamProviderFactory.get_provider("custom")
    assert isinstance(stream, _CustomStream)


def test_protocol_routing_constants_are_wired():
    methods = dict(PROTOCOL_HANDLER_METHODS)
    assert methods["userAction"] == "_handle_action"
    assert methods["mediaResolve"] == "_handle_media_resolve"
    assert DEFAULT_PROTOCOL_HANDLER_METHOD == "_handle_legacy_launch"


@pytest.mark.asyncio
async def test_handle_legacy_launch_happy_path():
    launched = []
    auth_errors = []

    async def _launch_request(bus, client_id, msg, ctx):
        launched.append((client_id, msg, ctx))

    network = SimpleNamespace(
        _build_context=lambda bus, client_id, msg: {"cid": client_id, "msg": msg, "bus": bus},
        _is_legacy_message_allowed_for_context=lambda msg, ctx: True,
        _authorize_and_bind_stream=lambda *a, **k: object(),
        _launch_request=_launch_request,
        _send_auth_error=lambda *a, **k: auth_errors.append("err"),
    )

    token = _set_request_context()
    try:
        await handle_legacy_launch(network, object(), "c1", {"action": "x"})
    finally:
        reset_req_ctx(token)

    assert launched and not auth_errors


@pytest.mark.asyncio
async def test_handle_legacy_launch_auth_rejection():
    launched = []
    auth_errors = []
    network = SimpleNamespace(
        _build_context=lambda bus, client_id, msg: {"cid": client_id},
        _is_legacy_message_allowed_for_context=lambda msg, ctx: False,
        _authorize_and_bind_stream=lambda *a, **k: object(),
        _launch_request=lambda *a, **k: launched.append(True),
        _send_auth_error=lambda *a, **k: auth_errors.append(a),
    )

    token = _set_request_context()
    try:
        await handle_legacy_launch(network, object(), "c1", {"action": "x"})
    finally:
        reset_req_ctx(token)

    assert not launched
    assert auth_errors


@pytest.mark.asyncio
async def test_handle_legacy_launch_stream_binding_failure_short_circuits():
    launched = []
    network = SimpleNamespace(
        _build_context=lambda bus, client_id, msg: {},
        _is_legacy_message_allowed_for_context=lambda msg, ctx: True,
        _authorize_and_bind_stream=lambda *a, **k: None,
        _launch_request=lambda *a, **k: launched.append(True),
        _send_auth_error=lambda *a, **k: None,
    )

    token = _set_request_context()
    try:
        await handle_legacy_launch(network, object(), "c1", {"stream_id": "s1"})
    finally:
        reset_req_ctx(token)

    assert not launched
