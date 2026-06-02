from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import sysconfig
import threading
import uuid
from pathlib import Path
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.ai.engine.runtime.access import (
    get_engine_access,
    get_engine_allowed_imports,
)
from democrai.core.application.ai.engine.runtime.environment import (
    application_root,
    get_engine_allowed_subprocess_commands,
    get_engine_runtime_env,
)
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.infrastructure.sandbox.access_constants import system_read_paths
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload
from democrai.core.runtime.foundation.paths import get_base_dir
from democrai.core.runtime.foundation.paths import get_runtime_engine_dirs
from democrai.core.runtime.foundation.paths import get_runtime_module_dirs
from democrai.core.runtime.foundation.paths import logs_dir


_WORKER_LOGGING_CONFIG_KEYS = (
    "logging.provider",
    "logging.url",
    "logging.method",
)


def worker_logging_config() -> dict[str, Any]:
    config = getattr(app_ctx(), "config", None)
    getter = getattr(config, "get", None)
    if not callable(getter):
        return {}
    marker = object()
    values: dict[str, Any] = {}
    for key in _WORKER_LOGGING_CONFIG_KEYS:
        value = getter(key, marker)
        if value is not marker:
            values[key] = value
    return values


def worker_landlock_enabled() -> bool:
    config = getattr(app_ctx(), "config", None)
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.landlock.enabled", False))


def _logging_access(
    *,
    engine_id: str,
    logging_config: dict[str, Any],
) -> tuple[AccessManifestRule, ...]:
    subject = AccessSubject.create("engine", engine_id)
    log_root = str(logs_dir().resolve())
    rules: list[AccessManifestRule] = [
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="filesystem",
                operation=operation,
                target=log_root,
            ),
        )
        for operation in ("read", "create", "modify", "delete")
    ]
    provider = (
        str(logging_config.get("logging.provider", "local") or "local")
        .strip()
        .lower()
    )
    target = str(logging_config.get("logging.url", "") or "").strip()
    if provider == "http" and target:
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="network",
                    operation=operation,
                    target=target,
                ),
            )
            for operation in ("connect", "send", "receive")
        )
    return tuple(rules)


def _worker_platform_read_paths() -> tuple[str, ...]:
    candidates: list[str] = list(system_read_paths())
    candidates.extend(path for path in sys.path if path)
    for key in ("stdlib", "platstdlib", "purelib", "platlib", "data", "include", "scripts"):
        path = sysconfig.get_paths().get(key)
        if path:
            candidates.append(path)
    for item in (sys.prefix, sys.exec_prefix):
        raw = str(item or "").strip()
        if raw:
            candidates.append(raw)
    try:
        candidates.append(str(get_base_dir()))
    except Exception:
        pass
    candidates.extend(get_runtime_module_dirs())
    candidates.extend(get_runtime_engine_dirs())

    seen: set[str] = set()
    resolved: list[str] = []
    for item in candidates:
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            path = os.path.realpath(os.path.abspath(os.path.expanduser(raw)))
        except Exception:
            continue
        if path in seen or not os.path.exists(path):
            continue
        seen.add(path)
        resolved.append(path)
    return tuple(resolved)


def _worker_platform_access(engine_id: str) -> tuple[AccessManifestRule, ...]:
    subject = AccessSubject.create("engine", engine_id)
    return tuple(
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="read",
                target=path,
            ),
        )
        for path in _worker_platform_read_paths()
    )


def worker_runtime_access(
    *,
    engine_id: str,
    config: dict[str, Any],
    logging_config: dict[str, Any],
) -> tuple[AccessManifestRule, ...]:
    return (
        *_worker_platform_access(engine_id),
        *get_engine_access(
            engine_id,
            "runtime",
            config=config,
        ),
        *_logging_access(
            engine_id=engine_id,
            logging_config=logging_config,
        ),
    )


class EngineWorkerSubject:
    def __init__(self, *, engine_id: str, config: dict[str, Any]) -> None:
        self._engine_id = engine_id.strip().lower() if isinstance(engine_id, str) else ""
        self._concurrency_enabled = bool(
            config.get("concurrency_enabled", False)
        )
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._response_condition = threading.Condition()
        self._responses: dict[str, dict[str, Any]] = {}
        self._stream_responses: dict[str, list[dict[str, Any]]] = {}
        self._closed = False
        self._process: subprocess.Popen[str] | None = None
        self._reader = None
        self._writer = None
        self._parent_request_reader = None
        self._parent_request_writer = None
        self._start(dict(config))

    def _start(self, config: dict[str, Any]) -> None:
        parent_read, child_write = os.pipe()
        child_read, parent_write = os.pipe()
        parent_request_read, child_request_write = os.pipe()
        child_response_read, parent_response_write = os.pipe()
        env = dict(os.environ)
        env["DEMOCRAI_ENGINE_WORKER_READ_FD"] = str(child_read)
        env["DEMOCRAI_ENGINE_WORKER_WRITE_FD"] = str(child_write)
        env["DEMOCRAI_ENGINE_WORKER_PARENT_REQUEST_FD"] = str(child_request_write)
        env["DEMOCRAI_ENGINE_WORKER_PARENT_RESPONSE_FD"] = str(child_response_read)
        current_pythonpath = str(env.get("PYTHONPATH") or "").strip()
        env["PYTHONPATH"] = (
            application_root()
            if not current_pythonpath
            else os.pathsep.join((application_root(), current_pythonpath))
        )
        command = [
            sys.executable,
            "-m",
            "democrai.core.application.ai.engine.worker",
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                pass_fds=(
                    child_read,
                    child_write,
                    child_request_write,
                    child_response_read,
                ),
                env=env,
                text=True,
            )
        finally:
            os.close(child_read)
            os.close(child_write)
            os.close(child_request_write)
            os.close(child_response_read)
        self._reader = os.fdopen(parent_read, "r", encoding="utf-8", buffering=1)
        self._writer = os.fdopen(parent_write, "w", encoding="utf-8", buffering=1)
        self._parent_request_reader = os.fdopen(
            parent_request_read,
            "r",
            encoding="utf-8",
            buffering=1,
        )
        self._parent_request_writer = os.fdopen(
            parent_response_write,
            "w",
            encoding="utf-8",
            buffering=1,
        )
        threading.Thread(
            target=self._read_responses,
            name=f"engine-worker-reader-{self._engine_id}",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_parent_requests,
            name=f"engine-worker-parent-request-{self._engine_id}",
            daemon=True,
        ).start()
        logging_config = worker_logging_config()
        self._request(
            "init",
            {
                "engine_id": self._engine_id,
                "config": config,
                "logging_config": logging_config,
                "landlock_enabled": worker_landlock_enabled(),
                "env": get_engine_runtime_env(self._engine_id),
                "access": [
                    rule.to_dict()
                    for rule in worker_runtime_access(
                        engine_id=self._engine_id,
                        config=config,
                        logging_config=logging_config,
                    )
                ],
                "allowed_imports": get_engine_allowed_imports(
                    self._engine_id,
                    "runtime",
                ),
                "allowed_subprocess_commands": get_engine_allowed_subprocess_commands(
                    self._engine_id,
                    "runtime",
                ),
            },
        )

    def _read_responses(self) -> None:
        try:
            while self._reader is not None:
                line = self._reader.readline()
                if not line:
                    break
                response = python_value(json.loads(line))
                response_id = str(response.get("id") or "")
                with self._response_condition:
                    if response.get("stream"):
                        self._stream_responses.setdefault(response_id, []).append(response)
                    else:
                        self._responses[response_id] = response
                    self._response_condition.notify_all()
        finally:
            with self._response_condition:
                self._closed = True
                self._response_condition.notify_all()

    def _read_parent_requests(self) -> None:
        try:
            while self._parent_request_reader is not None:
                line = self._parent_request_reader.readline()
                if not line:
                    break
                request = python_value(json.loads(line))
                self._handle_parent_request(dict(request or {}))
        except Exception:
            return

    def _handle_parent_request(self, request: dict[str, Any]) -> None:
        response_id = str(request.get("id") or "")
        try:
            result = self._parent_media_request(
                str(request.get("operation") or "").strip(),
                dict(request.get("payload") or {}),
            )
            response = {"id": response_id, "parent_response": True, "ok": True, "result": result}
        except Exception as exc:
            response = {
                "id": response_id,
                "parent_response": True,
                "ok": False,
                "error": str(exc),
            }
        with self._write_lock:
            if self._parent_request_writer is None:
                return
            self._parent_request_writer.write(
                json.dumps(json_value(response), ensure_ascii=True) + "\n"
            )
            self._parent_request_writer.flush()

    def _parent_media_request(self, operation: str, payload: dict[str, Any]) -> Any:
        from democrai.core.runtime.foundation.app import app_ctx
        from democrai.core.runtime.dependencies.engine_env import get_engine_local_tmp_path

        media = getattr(app_ctx(), "media", None)
        if media is None:
            raise RuntimeError("media_provider_unavailable")
        if operation == "media.exists":
            storage_path = str(payload.get("storage_path") or "").strip()
            if not storage_path:
                raise ValueError("storage_path_required")
            try:
                materialized = media.get_path(storage_path)
            except FileNotFoundError:
                return False
            except Exception:
                return False
            materialized.cleanup()
            return True
        if operation == "media.materialize":
            storage_path = str(payload.get("storage_path") or "").strip()
            if not storage_path:
                raise ValueError("storage_path_required")
            destination_dir = str(payload.get("destination_dir") or "").strip()
            if not destination_dir:
                destination_dir = str(get_engine_local_tmp_path(self._engine_id))
            materialized = media.get_path(storage_path, destination_dir=destination_dir)
            return {
                "path": str(materialized.path),
                "temporary": bool(materialized.temporary),
            }
        if operation == "media.save_model_artifact":
            storage_path = str(payload.get("storage_path") or "").strip()
            source_path = str(payload.get("source_path") or "").strip()
            if not storage_path:
                raise ValueError("storage_path_required")
            if not source_path:
                raise ValueError("source_path_required")
            if not Path(source_path).is_file():
                raise FileNotFoundError(source_path)
            if not storage_path.startswith("models/"):
                raise ValueError("model_artifact_storage_path_required")
            relative = storage_path[len("models/") :]
            parts = Path(relative).parts
            if len(parts) < 2 or not parts[-1]:
                raise ValueError("invalid_model_artifact_storage_path")
            return str(media.save_file(storage_path, source_path))
        raise RuntimeError(f"engine_worker_parent_operation_unknown:{operation}")

    def _request(self, operation: str, payload: dict[str, Any]) -> Any:
        if self._process is None or self._reader is None or self._writer is None:
            raise RuntimeError("engine_worker_not_started")
        if self._process.poll() is not None:
            raise RuntimeError(f"engine_worker_exited:{self._process.returncode}")
        request_id = uuid.uuid4().hex
        with self._write_lock:
            self._writer.write(
                json.dumps(
                    json_value(
                        {
                            "id": request_id,
                            "operation": operation,
                            "payload": payload,
                            "request_context": current_request_context_payload(
                                f"engine_worker_subject.{operation}"
                            ),
                            **(
                                {"request_id": str(payload.get("request_id") or "")}
                                if operation == "invoke" and payload.get("request_id")
                                else {}
                            ),
                        }
                    ),
                    ensure_ascii=True,
                )
                + "\n"
            )
            self._writer.flush()
        with self._response_condition:
            self._response_condition.wait_for(
                lambda: request_id in self._responses or self._closed
            )
            if request_id not in self._responses and self._closed:
                return_code = self._process.poll()
                raise RuntimeError(f"engine_worker_no_response:{return_code}")
            response = self._responses.pop(request_id)
        if not bool(response.get("ok")):
            error = str(response.get("error") or "engine_worker_error")
            details = str(response.get("traceback") or "").strip()
            try:
                app_ctx().logger.error(
                    "[EngineWorkerSubject] Worker request failed "
                    f"engine_id={self._engine_id} operation={operation} "
                    f"payload_keys={sorted(payload.keys())} error={error}"
                    + (f"\n{details}" if details else "")
                )
            except Exception:
                pass
            raise RuntimeError(error + (f"\n{details}" if details else ""))
        return response.get("result")

    def _send_request(self, operation: str, payload: dict[str, Any]) -> str:
        if self._process is None or self._reader is None or self._writer is None:
            raise RuntimeError("engine_worker_not_started")
        if self._process.poll() is not None:
            raise RuntimeError(f"engine_worker_exited:{self._process.returncode}")
        request_id = uuid.uuid4().hex
        with self._write_lock:
            self._writer.write(
                json.dumps(
                    json_value(
                        {
                            "id": request_id,
                            "operation": operation,
                            "payload": payload,
                            "request_context": current_request_context_payload(
                                f"engine_worker_subject.{operation}"
                            ),
                            **(
                                {"request_id": str(payload.get("request_id") or "")}
                                if operation == "invoke" and payload.get("request_id")
                                else {}
                            ),
                        }
                    ),
                    ensure_ascii=True,
                )
                + "\n"
            )
            self._writer.flush()
        return request_id

    def _wait_stream_response(self, request_id: str) -> dict[str, Any]:
        with self._response_condition:
            self._response_condition.wait_for(
                lambda: bool(self._stream_responses.get(request_id)) or self._closed
            )
            messages = self._stream_responses.get(request_id)
            if not messages and self._closed:
                return_code = self._process.poll() if self._process is not None else None
                raise RuntimeError(f"engine_worker_no_response:{return_code}")
            response = messages.pop(0)
            if not messages:
                self._stream_responses.pop(request_id, None)
            return response

    def cancel(self, request_id: str) -> bool:
        return bool(self._request("cancel", {"request_id": request_id}))

    def invoke(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        def _invoke() -> Any:
            request_id = ""
            raw_payload = payload or {}
            ai_context = raw_payload.get("__ai_call_context")
            if isinstance(ai_context, dict):
                request_id = str(ai_context.get("request_id") or "")
            return self._request(
                "invoke",
                {
                    "method": method,
                    "payload": raw_payload,
                    **({"request_id": request_id} if request_id else {}),
                },
            )

        if self._concurrency_enabled:
            return _invoke()

        with self._lock:
            return _invoke()

    async def invoke_stream(self, method: str, payload: dict[str, Any] | None = None):
        async def _stream():
            request_id = ""
            raw_payload = payload or {}
            ai_context = raw_payload.get("__ai_call_context")
            if isinstance(ai_context, dict):
                request_id = str(ai_context.get("request_id") or "")
            response_id = self._send_request(
                "invoke",
                {
                    "method": method,
                    "payload": raw_payload,
                    **({"request_id": request_id} if request_id else {}),
                },
            )
            while True:
                response = await asyncio.to_thread(
                    self._wait_stream_response,
                    response_id,
                )
                stream_kind = str(response.get("stream") or "")
                if stream_kind == "chunk":
                    yield response.get("chunk")
                    continue
                if stream_kind == "end":
                    if not bool(response.get("ok")):
                        error = str(response.get("error") or "engine_worker_error")
                        details = str(response.get("traceback") or "").strip()
                        raise RuntimeError(error + (f"\n{details}" if details else ""))
                    return
                raise RuntimeError(f"engine_worker_stream_response_unknown:{stream_kind}")

        if self._concurrency_enabled:
            async for item in _stream():
                yield item
            return

        await asyncio.to_thread(self._lock.acquire)
        try:
            async for item in _stream():
                yield item
        finally:
            self._lock.release()

    def close(self) -> None:
        process = self._process
        try:
            if process is not None and process.poll() is None:
                try:
                    self._request("close", {})
                except Exception:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
        finally:
            for handle in (self._reader, self._writer):
                try:
                    if handle is not None:
                        handle.close()
                except Exception:
                    pass
            for handle in (self._parent_request_reader, self._parent_request_writer):
                try:
                    if handle is not None:
                        handle.close()
                except Exception:
                    pass
