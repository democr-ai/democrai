from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()
_READER = None
_WRITER = None


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


def _streams():
    global _READER, _WRITER
    _require_engine_worker_runtime()
    if _READER is not None and _WRITER is not None:
        return _READER, _WRITER
    request_fd = int(os.environ["DEMOCRAI_ENGINE_WORKER_PARENT_REQUEST_FD"])
    response_fd = int(os.environ["DEMOCRAI_ENGINE_WORKER_PARENT_RESPONSE_FD"])
    _WRITER = os.fdopen(request_fd, "w", encoding="utf-8", buffering=1)
    _READER = os.fdopen(response_fd, "r", encoding="utf-8", buffering=1)
    return _READER, _WRITER


def _request(operation: str, payload: dict[str, Any]) -> Any:
    reader, writer = _streams()
    request_id = uuid.uuid4().hex
    with _LOCK:
        writer.write(
            json.dumps(
                {
                    "id": request_id,
                    "parent_request": True,
                    "operation": operation,
                    "payload": payload,
                },
                ensure_ascii=True,
            )
            + "\n"
        )
        writer.flush()
        while True:
            line = reader.readline()
            if not line:
                raise RuntimeError("engine_runtime_parent_media_channel_closed")
            response = json.loads(line)
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
