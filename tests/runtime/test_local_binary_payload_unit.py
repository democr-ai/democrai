from __future__ import annotations

import subprocess
import sys
from multiprocessing import Pipe

import pytest

from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.runtime.ipc import local_binary_payload as binary_mod
from democrai.core.runtime.ipc.local_binary_payload import LocalBinaryPayloadChannel


def test_local_binary_payload_keeps_small_bytes_inline():
    left, right = Pipe()
    sender = LocalBinaryPayloadChannel(left, threshold_bytes=1024)
    receiver = LocalBinaryPayloadChannel(right, threshold_bytes=1024)

    sender.send({"data": b"a"})

    assert receiver.recv() == {"data": b"a"}
    sender.close()
    receiver.close()
    left.close()
    right.close()


def test_local_binary_payload_send_json_keeps_small_bytes_serialized():
    left, right = Pipe()
    sender = LocalBinaryPayloadChannel(left, threshold_bytes=1024)
    receiver = LocalBinaryPayloadChannel(right, threshold_bytes=1024)

    sender.send_json({"data": b"a"}, json_value)

    assert receiver.recv() == {"data": {"__bytes__": "YQ=="}}
    sender.close()
    receiver.close()
    left.close()
    right.close()


def test_local_binary_payload_send_preserves_tuples():
    left, right = Pipe()
    sender = LocalBinaryPayloadChannel(left, threshold_bytes=1024)
    receiver = LocalBinaryPayloadChannel(right, threshold_bytes=1024)

    sender.send({"items": (b"a", b"b")})

    result = receiver.recv()
    assert result == {"items": (b"a", b"b")}
    assert isinstance(result["items"], tuple)
    sender.close()
    receiver.close()
    left.close()
    right.close()


def test_local_binary_payload_uses_shared_memory_for_large_bytes_and_releases_on_ack():
    left, right = Pipe()
    sender = LocalBinaryPayloadChannel(left, threshold_bytes=8)
    receiver = LocalBinaryPayloadChannel(right, threshold_bytes=8)
    raw = b"abcdef" * 8

    sender.send({"data": raw})

    assert receiver.recv() == {"data": raw}
    assert sender._pending
    receiver.send({"ok": True})
    assert sender.recv() == {"ok": True}
    assert not sender._pending

    sender.close()
    receiver.close()
    left.close()
    right.close()


def test_local_binary_payload_close_releases_pending_shared_memory():
    left, right = Pipe()
    sender = LocalBinaryPayloadChannel(left, threshold_bytes=8)

    sender.send({"data": b"abcdef" * 8})
    assert sender._pending
    assert binary_mod._LOCAL_OWNED_NAMES

    sender.close()

    assert not sender._pending
    assert not binary_mod._LOCAL_OWNED_NAMES
    left.close()
    right.close()


def test_local_binary_payload_send_failure_releases_pending_shared_memory():
    class _FailingConnection:
        def send(self, _value):
            raise OSError("broken")

    channel = LocalBinaryPayloadChannel(_FailingConnection(), threshold_bytes=8)
    with pytest.raises(OSError):
        channel.send({"data": b"abcdef" * 8})

    assert not channel._pending


def test_local_binary_payload_send_json_failure_releases_pending_shared_memory():
    class _BadValue:
        pass

    def _json_value(value, *, binary_packer=None):
        binary_packer(value["data"])
        raise RuntimeError("serialization_failed")

    left, right = Pipe()
    channel = LocalBinaryPayloadChannel(left, threshold_bytes=8)

    with pytest.raises(RuntimeError, match="serialization_failed"):
        channel.send_json({"data": b"abcdef" * 8, "bad": _BadValue()}, _json_value)

    assert not channel._pending
    channel.close()
    left.close()
    right.close()


def test_local_binary_payload_recv_skips_ack_frames():
    left, right = Pipe()
    sender = LocalBinaryPayloadChannel(left, threshold_bytes=8)
    receiver = LocalBinaryPayloadChannel(right, threshold_bytes=8)
    token = "unknown"

    right.send({"__democrai_shared_memory_ack__": True, "tokens": [token]})
    right.send({"value": 1})

    assert sender.recv() == {"value": 1}

    sender.close()
    receiver.close()
    left.close()
    right.close()


def test_runtime_json_value_uses_binary_packer_before_base64_for_large_bytes():
    calls = []

    def _packer(value):
        calls.append(bytes(value))
        return {"packed": len(value)}

    assert json_value({"data": b"abc"}, binary_packer=_packer) == {"data": {"packed": 3}}
    assert calls == [b"abc"]
    assert python_value({"data": {"__bytes__": "YQ=="}}) == {"data": b"a"}


def test_local_binary_payload_same_process_has_no_resource_tracker_warning():
    script = """
from multiprocessing import Pipe
from democrai.core.runtime.ipc.local_binary_payload import LocalBinaryPayloadChannel

left, right = Pipe()
sender = LocalBinaryPayloadChannel(left, threshold_bytes=8)
receiver = LocalBinaryPayloadChannel(right, threshold_bytes=8)
sender.send({"data": b"abcdef" * 8})
assert receiver.recv()["data"] == b"abcdef" * 8
receiver.send({"ok": True})
assert sender.recv() == {"ok": True}
sender.close()
receiver.close()
left.close()
right.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "resource_tracker" not in result.stderr
    assert "KeyError" not in result.stderr


def test_local_binary_payload_cross_process_has_no_resource_tracker_warning():
    script = """
from multiprocessing import Pipe, Process
from democrai.core.runtime.ipc.local_binary_payload import LocalBinaryPayloadChannel

def child(conn):
    channel = LocalBinaryPayloadChannel(conn, threshold_bytes=8)
    assert channel.recv()["data"] == b"abcdef" * 8
    channel.send({"ok": True})
    channel.close()
    conn.close()

left, right = Pipe()
process = Process(target=child, args=(right,))
process.start()
right.close()
sender = LocalBinaryPayloadChannel(left, threshold_bytes=8)
sender.send({"data": b"abcdef" * 8})
assert sender.recv() == {"ok": True}
sender.close()
left.close()
process.join()
raise SystemExit(process.exitcode or 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "resource_tracker" not in result.stderr
