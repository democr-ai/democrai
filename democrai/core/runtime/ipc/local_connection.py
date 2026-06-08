from __future__ import annotations

import base64
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from multiprocessing.connection import Client, Connection, Listener
from pathlib import Path
from typing import Any

from democrai.core.runtime.foundation.paths import runtime_unix_socket_path


@dataclass(frozen=True)
class LocalConnectionEndpoint:
    address: str
    authkey_b64: str
    listener: Listener
    socket_path: Path | None = None

    def env(self, prefix: str) -> dict[str, str]:
        normalized = str(prefix or "").strip().upper()
        return {
            f"{normalized}_ADDRESS": self.address,
            f"{normalized}_AUTHKEY": self.authkey_b64,
        }

    def close(self) -> None:
        try:
            self.listener.close()
        except Exception:
            pass
        if self.socket_path is not None:
            try:
                self.socket_path.unlink(missing_ok=True)
            except Exception:
                pass


def create_local_listener(kind: str) -> LocalConnectionEndpoint:
    normalized = _normalize_kind(kind)
    authkey = os.urandom(32)
    authkey_b64 = base64.b64encode(authkey).decode("ascii")
    address, socket_path = _local_address(normalized)
    listener = Listener(address=address, family=_address_family(address), authkey=authkey)
    return LocalConnectionEndpoint(
        address=address,
        authkey_b64=authkey_b64,
        listener=listener,
        socket_path=socket_path,
    )


def connect_from_env(prefix: str) -> Connection:
    normalized = str(prefix or "").strip().upper()
    address = str(os.environ[f"{normalized}_ADDRESS"])
    authkey = base64.b64decode(str(os.environ[f"{normalized}_AUTHKEY"]))
    return Client(address=address, family=_address_family(address), authkey=authkey)


def accept_connection(
    endpoint: LocalConnectionEndpoint,
    *,
    process: Any | None = None,
    timeout_seconds: float = 10.0,
) -> Connection:
    deadline = time.monotonic() + max(0.1, float(timeout_seconds or 10.0))
    accepted: queue.Queue[Connection | BaseException] = queue.Queue(maxsize=1)

    def _accept() -> None:
        try:
            accepted.put(endpoint.listener.accept())
        except BaseException as exc:
            accepted.put(exc)

    thread = threading.Thread(
        target=_accept,
        name="local-connection-accept",
        daemon=True,
    )
    thread.start()
    try:
        while True:
            try:
                item = accepted.get(timeout=0.05)
            except queue.Empty:
                item = None
            if item is not None:
                if isinstance(item, BaseException):
                    raise item
                return item
            if process is not None and process.poll() is not None:
                raise RuntimeError(
                    f"local_connection_process_exited_before_connect:{process.returncode}"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(f"local_connection_accept_timeout:{endpoint.address}")
    finally:
        endpoint.close()


def _normalize_kind(kind: str) -> str:
    raw = str(kind or "").strip().lower()
    resolved = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw)
    return resolved.strip("-_") or "worker"


def _local_address(kind: str) -> tuple[str, Path | None]:
    unique = f"{kind}-{os.getpid()}-{uuid.uuid4().hex}"
    if os.name == "nt":
        return rf"\\.\pipe\democrai-{unique}", None
    path = runtime_unix_socket_path(f"{unique}.sock")
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
    return str(path), path


def _address_family(address: str) -> str:
    if os.name == "nt" or str(address).startswith("\\\\.\\pipe\\"):
        return "AF_PIPE"
    return "AF_UNIX"
