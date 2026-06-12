from __future__ import annotations

import base64
import threading
import time
from types import SimpleNamespace

import pytest

from democrai.core.runtime.ipc import local_connection as mod


def test_local_connection_roundtrip_and_unix_socket_cleanup(monkeypatch):
    endpoint = mod.create_local_listener("unit test")
    for key, value in endpoint.env("DEMOCRAI_TEST").items():
        monkeypatch.setenv(key, value)
    seen = {}

    def _client():
        conn = mod.connect_from_env("DEMOCRAI_TEST")
        try:
            conn.send({"ping": True})
            seen["reply"] = conn.recv()
        finally:
            conn.close()

    thread = threading.Thread(target=_client)
    thread.start()
    conn = mod.accept_connection(endpoint, timeout_seconds=2.0)
    try:
        assert conn.recv() == {"ping": True}
        conn.send({"pong": True})
    finally:
        conn.close()
    thread.join(timeout=2.0)

    assert seen["reply"] == {"pong": True}
    if endpoint.socket_path is not None:
        assert not endpoint.socket_path.exists()


@pytest.mark.posix_only
def test_connect_from_env_requires_authkey(monkeypatch):
    calls = []
    monkeypatch.setenv("DEMOCRAI_TEST_ADDRESS", "/tmp/democrai.sock")
    monkeypatch.setenv(
        "DEMOCRAI_TEST_AUTHKEY",
        base64.b64encode(b"secret").decode("ascii"),
    )
    monkeypatch.setattr(
        mod,
        "Client",
        lambda *, address, family, authkey: calls.append((address, family, authkey))
        or SimpleNamespace(close=lambda: None),
    )

    conn = mod.connect_from_env("DEMOCRAI_TEST")

    assert conn is not None
    assert calls == [("/tmp/democrai.sock", "AF_UNIX", b"secret")]


def test_accept_connection_times_out_and_closes_endpoint():
    closed = []

    class _Listener:
        def accept(self):
            time.sleep(1.0)

    endpoint = SimpleNamespace(
        address="local-test",
        listener=_Listener(),
        close=lambda: closed.append(True),
    )

    with pytest.raises(TimeoutError, match="local_connection_accept_timeout"):
        mod.accept_connection(endpoint, timeout_seconds=0.1)

    assert closed == [True]


def test_address_family_supports_windows_named_pipe_address():
    assert mod._address_family(r"\\.\pipe\democrai-test") == "AF_PIPE"
