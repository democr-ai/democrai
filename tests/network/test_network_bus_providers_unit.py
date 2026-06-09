from __future__ import annotations

import asyncio
import importlib
import json
import os
import socket
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest


class _DummyLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []
        self.debugs = []

    def info(self, msg, *a, **k):
        self.infos.append(str(msg))

    def warning(self, msg, *a, **k):
        self.warnings.append(str(msg))

    def error(self, msg, *a, **k):
        self.errors.append(str(msg))

    def debug(self, msg, *a, **k):
        self.debugs.append(str(msg))


def _install_fake_pyside(monkeypatch):
    class _QtMeta(__import__("abc").ABCMeta):
        pass

    class QObject(metaclass=_QtMeta):
        def __init__(self, *a, **k):
            return None

    class Signal:
        def __init__(self, *a, **k):
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, *a, **k):
            for cb in list(self._callbacks):
                cb(*a, **k)

    def Slot(*_a, **_k):
        def _dec(fn):
            return fn

        return _dec

    class QByteArray:
        def __init__(self, data):
            self.data = data

    class _State:
        ConnectedState = 1

    class QLocalSocket:
        LocalSocketState = _State

    class _ReadyData:
        def __init__(self, raw: bytes):
            self._raw = raw

        def data(self):
            return self._raw

    class _FakeSock:
        def __init__(self, payloads=None):
            self._sid = None
            self._buf = bytearray()
            self._payloads = list(payloads or [])
            self.readyRead = Signal()
            self.disconnected = Signal()
            self.parent = None
            self.closed = False
            self.deleted = False
            self.writes = []

        def setParent(self, p):
            self.parent = p

        def state(self):
            return 1

        def readAll(self):
            raw = self._payloads.pop(0) if self._payloads else b""
            return _ReadyData(raw)

        def write(self, b):
            self.writes.append(b)

        def flush(self):
            return None

        def close(self):
            self.closed = True

        def deleteLater(self):
            self.deleted = True

    class _SignalWrap(Signal):
        pass

    class QLocalServer:
        _removed = []

        @staticmethod
        def removeServer(name):
            QLocalServer._removed.append(name)

        def __init__(self, parent=None):
            self.parent = parent
            self.newConnection = _SignalWrap()
            self._pending = []
            self._listen_results = [True]
            self._error = "err"
            self.closed = False

        def close(self):
            self.closed = True

        def listen(self, _name):
            if self._listen_results:
                return self._listen_results.pop(0)
            return True

        def errorString(self):
            return self._error

        def hasPendingConnections(self):
            return bool(self._pending)

        def nextPendingConnection(self):
            return self._pending.pop(0)

    qtcore = SimpleNamespace(QObject=QObject, Slot=Slot, Signal=Signal, QByteArray=QByteArray)
    qtnetwork = SimpleNamespace(QLocalServer=QLocalServer, QLocalSocket=QLocalSocket, _FakeSock=_FakeSock)
    monkeypatch.setitem(sys.modules, "PySide6", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", qtcore)
    monkeypatch.setitem(sys.modules, "PySide6.QtNetwork", qtnetwork)
    return qtnetwork


def test_ipc_bus_provider_branches(monkeypatch, tmp_path):
    logger = _DummyLogger()
    monkeypatch.setattr("democrai.core.runtime.foundation.app.app_ctx", lambda: SimpleNamespace(logger=logger))
    ipc_mod = importlib.reload(importlib.import_module("democrai.core.infrastructure.network.providers.bus.ipc"))
    monkeypatch.setattr(ipc_mod, "_debug_ipc_trace", lambda *a, **k: None)

    recv = []
    disc = []
    endpoint = os.path.join(tempfile.gettempdir(), f"dc-ipc-{os.getpid()}.sock")
    bus = ipc_mod.IpcBusProvider(endpoint, on_message=lambda cid, msg: recv.append((cid, msg)), on_disconnect=lambda cid: disc.append(cid))
    bus.start()
    assert logger.infos
    assert bus.endpoint == f"unix:{endpoint}"

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(1.0)
    client.connect(endpoint)
    deadline = time.time() + 2
    while not bus._sockets and time.time() < deadline:
        time.sleep(0.01)
    assert bus._sockets
    sid = next(iter(bus._sockets.keys()))

    client.sendall(b'{"a":1}\nnot-json\n')
    deadline = time.time() + 2
    while not recv and time.time() < deadline:
        time.sleep(0.01)
    assert recv and recv[0][1]["a"] == 1
    deadline = time.time() + 2
    while not logger.errors and time.time() < deadline:
        time.sleep(0.01)
    assert logger.errors

    bus.send(sid, {"x": 1})
    bus.broadcast({"b": 2})
    chunks = bytearray()
    deadline = time.time() + 2
    while time.time() < deadline and (b'"x":1' not in chunks or b'"b":2' not in chunks):
        chunks.extend(client.recv(65536))
    payload = bytes(chunks)
    assert b'"x":1' in payload and b'"b":2' in payload
    bus.send(999, {"x": 2})

    bus.on_message = None
    client.sendall(b'{"cb":0}\n')
    time.sleep(0.05)
    client.close()
    deadline = time.time() + 2
    while not disc and time.time() < deadline:
        time.sleep(0.01)
    assert disc and sid not in bus._sockets

    bus.stop()
    assert bus._sockets == {}
    assert not os.path.exists(endpoint)

    rel_bus = ipc_mod.IpcBusProvider("relative.sock")
    assert rel_bus.endpoint.startswith("unix:")
    unix_bus = ipc_mod.IpcBusProvider("unix:/tmp/demo.sock")
    assert unix_bus.endpoint == "unix:/tmp/demo.sock"
    tcp_bus = ipc_mod.IpcBusProvider("tcp://127.0.0.1:0")
    tcp_bus.start()
    try:
        assert tcp_bus.endpoint.startswith("tcp://127.0.0.1:")
    finally:
        tcp_bus.stop()
    monkeypatch.setattr(ipc_mod.os, "name", "nt")
    win_bus = ipc_mod.IpcBusProvider("democr.ai.8000")
    assert win_bus.endpoint == "tcp://127.0.0.1:0"


@pytest.mark.asyncio
async def test_redis_bus_provider_branches(monkeypatch):
    logger = _DummyLogger()
    import democrai.core.infrastructure.network.providers.bus.redis as redis_mod

    monkeypatch.setattr(redis_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(redis_mod, "HAS_REDIS", False)
    with pytest.raises(Exception):
        redis_mod.RedisBusProvider("n1")

    monkeypatch.setattr(redis_mod, "HAS_REDIS", True)

    class _FakePubSub:
        def __init__(self):
            self._msgs = [
                {"type": "subscribe", "data": "ok"},
                {"type": "message", "data": json.dumps({"kind": "direct", "client_id": "c1", "message": {"x": 1}})},
                {"type": "message", "data": json.dumps({"kind": "broadcast", "message": {"b": 1}})},
                {"type": "message", "data": json.dumps({"kind": "unknown"})},
            ]
            self.unsubscribed = False
            self.closed = False

        async def subscribe(self, *args):
            return None

        async def listen(self):
            for m in self._msgs:
                yield m

        async def unsubscribe(self, *args):
            self.unsubscribed = True

        async def close(self):
            self.closed = True

    class _FakeRedis:
        def __init__(self):
            self.published = []
            self.closed = False
            self._pubsub = _FakePubSub()

        def pubsub(self):
            return self._pubsub

        async def publish(self, ch, payload):
            self.published.append((ch, payload))

        async def close(self):
            self.closed = True

    fake = _FakeRedis()
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda url: fake), raising=False
    )

    direct = []
    bcast = []
    bus = redis_mod.RedisBusProvider(
        "n1",
        local_send=lambda cid, msg: direct.append((cid, msg)),
        local_broadcast=lambda msg: bcast.append(msg),
        resolve_client_node=lambda cid: ("n2", cid) if cid == "remote" else None,
    )

    assert bus._resolve_target({"node_id": "n2", "client_id": "c"}) == ("n2", "c")
    assert bus._resolve_target(("n3", "c")) == ("n3", "c")
    assert bus._resolve_target(("n3",)) is None
    assert bus._resolve_target({"node_id": "n2"}) is None
    assert bus._resolve_target("local") is None

    bus.send("local", {"x": 1})
    assert direct
    bus.send({"node_id": "n1", "client_id": "c-local"}, {"z": 1})
    assert any(item[0] == "c-local" for item in direct)

    # without redis object: schedule publish_direct
    created = []

    def _create_task(coro):
        t = asyncio.get_running_loop().create_task(coro)
        created.append(t)
        return t

    monkeypatch.setattr(redis_mod.asyncio, "create_task", _create_task)
    bus.redis = None
    bus.send("remote", {"r": 1})
    await asyncio.gather(*created)

    bus.redis = fake
    bus.send("remote", {"r2": 2})
    await asyncio.sleep(0)
    assert fake.published

    bus.broadcast({"b": 1})
    await asyncio.sleep(0)
    bus.redis = None
    bus.broadcast({"b": 2})
    await asyncio.sleep(0)
    # _publish_broadcast no redis after ensure branch
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda _url: None), raising=False
    )
    await bus._publish_broadcast({"b": 3})
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda url: fake), raising=False
    )

    await bus._listen_for_node_messages()
    assert any(item[0] == "c1" for item in direct)
    assert bcast
    assert logger.debugs
    assert bus.redis is None  # closed in finally

    # _deliver_local on_message and warning branches
    bus_local = redis_mod.RedisBusProvider("n3")
    delivered = []
    bus_local.on_message = lambda cid, msg: delivered.append((cid, msg))
    bus_local._deliver_local("c", {"ok": 1})
    assert delivered
    bus_warn = redis_mod.RedisBusProvider("n4")
    bus_warn._deliver_local("c", {"ok": 1})
    assert logger.warnings

    # _publish_direct early return when redis stays None
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda _url: None), raising=False
    )
    bus_none = redis_mod.RedisBusProvider("n5")
    await bus_none._publish_direct("n6", "c", {"x": 1})
    await bus_none._publish_broadcast({"x": 9})

    # _listen_for_node_messages branch when ensure_connected keeps redis None
    await bus_none._listen_for_node_messages()

    # broadcast warning branch (local_send present without local_broadcast)
    class _PubSubWarn(_FakePubSub):
        def __init__(self):
            self._msgs = [
                {"type": "message", "data": json.dumps({"kind": "broadcast", "message": {"x": 1}})},
            ]
            self.unsubscribed = False
            self.closed = False

    fake_warn = _FakeRedis()
    fake_warn._pubsub = _PubSubWarn()
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda _url: fake_warn), raising=False
    )
    bus_warn_bcast = redis_mod.RedisBusProvider("n6", local_send=lambda *_a, **_k: None)
    await bus_warn_bcast._listen_for_node_messages()
    assert logger.warnings

    # listener error branch
    class _BadPubSub(_FakePubSub):
        async def listen(self):
            raise RuntimeError("boom")
            yield {}

    fake2 = _FakeRedis()
    fake2._pubsub = _BadPubSub()
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda url: fake2), raising=False
    )
    bus2 = redis_mod.RedisBusProvider("n2")
    await bus2._listen_for_node_messages()
    assert logger.errors

    # cancelled listener + unsubscribe failure in finally
    class _CancelPubSub(_FakePubSub):
        async def listen(self):
            raise asyncio.CancelledError()
            yield {}

        async def unsubscribe(self, *args):
            raise RuntimeError("no-unsub")

    fake3 = _FakeRedis()
    fake3._pubsub = _CancelPubSub()
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda _url: fake3), raising=False
    )
    bus3 = redis_mod.RedisBusProvider("n7")
    await bus3._listen_for_node_messages()
    # bytes payload decode branch
    class _PubSubBytes(_FakePubSub):
        def __init__(self):
            self._msgs = [
                {
                    "type": "message",
                    "data": json.dumps(
                        {"kind": "direct", "client_id": "c2", "message": {"x": 2}}
                    ).encode("utf-8"),
                }
            ]
            self.unsubscribed = False
            self.closed = False

    fake_bytes = _FakeRedis()
    fake_bytes._pubsub = _PubSubBytes()
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda _url: fake_bytes), raising=False
    )
    bus_bytes = redis_mod.RedisBusProvider("n10", local_send=lambda cid, msg: direct.append((cid, msg)))
    await bus_bytes._listen_for_node_messages()
    assert any(item[0] == "c2" for item in direct)

    # no resolver branch
    bus_no_resolver = redis_mod.RedisBusProvider("n11")
    assert bus_no_resolver._resolve_target("x") is None

    # broadcast branch without local_broadcast and without local_send
    class _PubSubBroadcast(_FakePubSub):
        def __init__(self):
            self._msgs = [
                {
                    "type": "message",
                    "data": json.dumps({"kind": "broadcast", "message": {"k": 1}}),
                }
            ]
            self.unsubscribed = False
            self.closed = False

    fake_broadcast = _FakeRedis()
    fake_broadcast._pubsub = _PubSubBroadcast()
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda _url: fake_broadcast), raising=False
    )
    await redis_mod.RedisBusProvider("n12")._listen_for_node_messages()

    # finally branches where _pubsub / redis become None before cleanup
    class _PubSubMutate(_FakePubSub):
        def __init__(self):
            self._msgs = [
                {
                    "type": "message",
                    "data": json.dumps(
                        {"kind": "direct", "client_id": "c-final", "message": {"x": 1}}
                    ),
                }
            ]
            self.unsubscribed = False
            self.closed = False

    fake_mutate = _FakeRedis()
    fake_mutate._pubsub = _PubSubMutate()
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda _url: fake_mutate), raising=False
    )
    bus_mutate = redis_mod.RedisBusProvider("n13")
    bus_mutate.local_send = lambda *_a, **_k: (setattr(bus_mutate, "_pubsub", None), setattr(bus_mutate, "redis", None))
    await bus_mutate._listen_for_node_messages()

    bus2.start()
    assert bus2._listener_task is not None
    bus2.stop()
    redis_mod.RedisBusProvider("n8").stop()  # no listener task branch


def test_redis_bus_import_has_redis_branch(monkeypatch):
    import democrai.core.infrastructure.network.providers.bus.redis as redis_mod

    fake_asyncio = SimpleNamespace(from_url=lambda _url: None, Redis=object)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(asyncio=fake_asyncio))
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio)
    reloaded = importlib.reload(redis_mod)
    assert reloaded.HAS_REDIS is True


@pytest.mark.asyncio
async def test_redis_bus_publish_broadcast_without_redis(monkeypatch):
    import democrai.core.infrastructure.network.providers.bus.redis as redis_mod

    monkeypatch.setattr(redis_mod, "HAS_REDIS", True)
    monkeypatch.setattr(
        redis_mod, "redis", SimpleNamespace(from_url=lambda _url: None), raising=False
    )
    bus = redis_mod.RedisBusProvider("n-bcast-none")
    await bus._publish_broadcast({"k": "v"})
    assert bus.redis is None


@pytest.mark.asyncio
async def test_ws_bus_provider_branches(monkeypatch):
    import democrai.core.infrastructure.network.providers.bus.ws as ws_mod

    logger = _DummyLogger()
    monkeypatch.setattr(ws_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, config=SimpleNamespace(get=lambda k, d=None: d)))
    monkeypatch.setenv("DEMOCRAI_DEBUG_WS_RUNTIME", "1")
    monkeypatch.setattr(ws_mod, "runtime_diagnostics", lambda: {"json_encoder_module": "a", "json_decoder_module": "b", "_json_loaded": True, "json_module_file": "j", "zlib_module_file": "z"})
    monkeypatch.setattr(ws_mod, "normalize_codec", lambda codec, fallback="json": codec if codec in {"json", "deflate-json"} else fallback)
    monkeypatch.setattr(ws_mod, "encode_message", lambda message, codec: ("bytes", b"x") if codec == "deflate-json" else ("text", json.dumps(message)))
    monkeypatch.setattr(ws_mod, "decode_message", lambda text=None, data=None, codec="json": {"decoded": True})
    monkeypatch.setattr(ws_mod, "current_request_profiler", lambda: None)
    monkeypatch.setattr(
        ws_mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, _loop: asyncio.get_running_loop().create_task(coro),
    )

    sent = []

    class _WS:
        def __init__(self, packets):
            self._packets = list(packets)
            self.accepted = False

        async def accept(self):
            self.accepted = True

        async def receive(self):
            if not self._packets:
                return {"type": "websocket.disconnect"}
            return self._packets.pop(0)

        async def send_text(self, payload):
            sent.append(("text", payload))

        async def send_bytes(self, payload):
            sent.append(("bytes", payload))

    bus = ws_mod.WsBusProvider()
    bus.start()
    assert logger.infos
    monkeypatch.delenv("DEMOCRAI_DEBUG_WS_RUNTIME", raising=False)
    ws_mod.WsBusProvider().start()  # start branch without runtime debug

    loop = asyncio.get_running_loop()
    ws = _WS([{"text": "a"}, {"type": "websocket.disconnect"}])
    got = []
    bus.on_message = lambda cid, msg: got.append((cid, msg))
    bus.on_disconnect = lambda cid: got.append(("disc", cid))
    await bus.handle_connection(ws, "c1", preferred_codec="deflate-json")
    assert ws.accepted and got and got[0][1]["type"] == "init"

    bus._sockets["c2"] = _WS([])
    bus._loops["c2"] = loop
    bus._codecs["c2"] = "json"
    bus.send("c2", {"x": 1})
    bus.broadcast({"b": 1})
    await asyncio.sleep(0)
    assert sent
    bus.send("missing", {"x": 2})  # ws/loop missing branch

    # send error branch
    class _BadWS(_WS):
        async def send_text(self, payload):
            raise RuntimeError("boom")

    bus._sockets["bad"] = _BadWS([])
    bus._loops["bad"] = loop
    bus._codecs["bad"] = "json"
    def _raise_send(coro, _loop):
        coro.close()
        raise RuntimeError("boom")

    monkeypatch.setattr(ws_mod.asyncio, "run_coroutine_threadsafe", _raise_send)
    bus.send("bad", {"x": 1})
    await asyncio.sleep(0)
    assert logger.errors

    # profiler + bytes encode/send branches
    profile_events = []
    monkeypatch.setattr(
        ws_mod,
        "current_request_profiler",
        lambda: SimpleNamespace(add_ms=lambda n, v: profile_events.append((n, v))),
    )
    monkeypatch.setattr(
        ws_mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, _loop: asyncio.get_running_loop().create_task(coro),
    )
    bus._codecs["c2"] = "deflate-json"
    bus.send("c2", {"bytes": True})
    await asyncio.sleep(0)
    assert any(name == "transport.ws.encode" for name, _ in profile_events)
    assert any(kind == "bytes" for kind, _payload in sent)

    # broadcast exception swallowed branch and loop-missing branch
    class _BadSendWS(_WS):
        async def send_text(self, payload):
            raise RuntimeError("boom")

    bus._sockets["nol"] = _WS([])
    bus._sockets["boom"] = _BadSendWS([])
    bus._loops["boom"] = loop
    bus._codecs["boom"] = "json"
    bus.broadcast({"x": 1})
    monkeypatch.setattr(
        ws_mod, "encode_message", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("enc"))
    )
    bus.broadcast({"x": 2})

    # handle_connection with WebSocketDisconnect and generic error
    class _DisconnectWS(_WS):
        async def receive(self):
            raise ws_mod.WebSocketDisconnect()

    class _ErrorWS(_WS):
        async def receive(self):
            raise RuntimeError("err")

    await bus.handle_connection(_DisconnectWS([]), "c3")
    await bus.handle_connection(_ErrorWS([]), "c4")
    # on_message/on_disconnect missing branches + allow_override false branch
    bus_no_cb = ws_mod.WsBusProvider()
    monkeypatch.setattr(
        ws_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=logger,
            config=SimpleNamespace(
                get=lambda k, d=None: False
                if k == "network.ws.allow_client_codec_override"
                else d
            ),
        ),
    )
    await bus_no_cb.handle_connection(
        _WS([{"text": "x"}, {"type": "websocket.disconnect"}]),
        "c5",
        preferred_codec="deflate-json",
    )
    bus.stop()
    assert bus._sockets == {} and bus._loops == {} and bus._codecs == {}
