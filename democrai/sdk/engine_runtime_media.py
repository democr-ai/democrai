from __future__ import annotations

import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from democrai.core.runtime.ipc.local_connection import connect_from_env


_LOCK = threading.Lock()
_CONN = None


@dataclass(frozen=True)
class RuntimeMaterializedMedia:
    """Filesystem view returned by the engine runtime parent process."""

    path: str
    temporary: bool = False

    def cleanup(self) -> None:
        if not self.temporary:
            return
        target = Path(self.path)
        try:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
        except OSError:
            pass


def _require_engine_worker_runtime() -> None:
    if os.environ.get("DEMOCRAI_ENGINE_WORKER") != "1":
        raise RuntimeError("engine_runtime_media_only_available_in_engine_worker")


def _connection():
    global _CONN
    _require_engine_worker_runtime()
    if _CONN is not None:
        return _CONN
    _CONN = connect_from_env("DEMOCRAI_ENGINE_WORKER_PARENT")
    return _CONN


def _request(operation: str, payload: dict[str, Any]) -> Any:
    conn = _connection()
    request_id = uuid.uuid4().hex
    with _LOCK:
        conn.send(
            {
                "id": request_id,
                "parent_request": True,
                "operation": operation,
                "payload": payload,
            }
        )
        while True:
            response = conn.recv()
            if str(response.get("id") or "") != request_id:
                continue
            if not bool(response.get("ok")):
                raise RuntimeError(str(response.get("error") or "engine_runtime_parent_media_error"))
            return response.get("result")


def media_exists(storage_path: str) -> bool:
    """Return whether a media storage path exists via the parent runtime."""

    return bool(_request("media.exists", {"storage_path": str(storage_path or "")}))


def materialize_media(
    storage_path: str,
    *,
    destination_dir: str | None = None,
) -> RuntimeMaterializedMedia:
    """Materialize a media storage path through the parent runtime."""

    result = _request(
        "media.materialize",
        {
            "storage_path": str(storage_path or ""),
            **(
                {"destination_dir": str(destination_dir or "")}
                if destination_dir
                else {}
            ),
        },
    )
    if not isinstance(result, dict):
        raise RuntimeError("engine_runtime_materialize_response_invalid")
    return RuntimeMaterializedMedia(
        path=str(result.get("path") or ""),
        temporary=bool(result.get("temporary")),
    )


def save_model_artifact(storage_path: str, source_path: str) -> str:
    """Save a local file under model storage through the parent runtime."""

    return str(
        _request(
            "media.save_model_artifact",
            {
                "storage_path": str(storage_path or ""),
                "source_path": str(source_path or ""),
            },
        )
        or ""
    )
