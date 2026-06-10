from __future__ import annotations

import asyncio
import os
import signal
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
    application_pythonpath,
    get_engine_allowed_subprocess_commands,
    get_engine_runtime_env,
)
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.infrastructure.process.child_failure import ChildProcessFailure
from democrai.core.infrastructure.sandbox.access_constants import system_read_paths
from democrai.core.infrastructure.sandbox.process_guard import process_guard_bypass_context
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload
from democrai.core.runtime.foundation.paths import get_base_dir
from democrai.core.runtime.foundation.paths import get_runtime_engine_dirs
from democrai.core.runtime.foundation.paths import get_runtime_module_dirs
from democrai.core.runtime.foundation.paths import logs_dir
from democrai.core.runtime.dependencies.engine_env import get_engine_local_cache_path
from democrai.core.runtime.dependencies.engine_env import get_engine_local_config_path
from democrai.core.runtime.dependencies.engine_env import get_engine_local_env_path
from democrai.core.runtime.dependencies.engine_env import get_engine_local_tmp_path
from democrai.core.runtime.dependencies.engine_env import get_engine_venv_python_path
from democrai.core.runtime.ipc.local_binary_payload import LocalBinaryPayloadChannel
from democrai.core.runtime.ipc.local_connection import (
    accept_connection,
    create_local_listener,
)
from democrai.core.infrastructure.sandbox.worker_launch import (
    build_worker_launch_state,
    payload_access_rules,
)


_WORKER_LOGGING_CONFIG_KEYS = (
    "logging.provider",
    "logging.url",
    "logging.method",
)

_WORKER_BOOTSTRAP_CODE = (
    "import os,runpy,sys;"
    "module=sys.argv[1];"
    "paths=[p for p in sys.argv[2].split(os.pathsep) if p];"
    "[sys.path.remove(p) for p in paths if p in sys.path];"
    "[sys.path.insert(i, p) for i, p in enumerate(paths)];"
    "runpy.run_module(module, run_name='__main__')"
)


def engine_worker_init_timeout_seconds(config: Any | None = None) -> float:
    resolved = getattr(app_ctx(), "config", None) if config is None else config
    getter = getattr(resolved, "get", None)
    raw = getter("ai.engine_worker.init_timeout_seconds", 120.0) if callable(getter) else 120.0
    try:
        value = float(raw)
    except Exception:
        value = 120.0
    return max(15.0, value)


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


def worker_os_sandbox_enabled() -> bool:
    config = getattr(app_ctx(), "config", None)
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.enabled", False))


def _engine_worker_launch_state(
    *,
    engine_id: str,
    access: tuple[AccessManifestRule, ...],
) -> dict[str, Any]:
    return build_worker_launch_state(
        subject_kind="engine",
        subject_name=engine_id,
        access=access,
        inherit_os_sandbox_helper_env=True,
    )


def _with_engine_temp_env(env: dict[str, str], engine_id: str) -> dict[str, str]:
    tmp_path = str(get_engine_local_tmp_path(engine_id))
    env["TMPDIR"] = tmp_path
    env["TEMP"] = tmp_path
    env["TMP"] = tmp_path
    return env


def _spawn_engine_worker_process(
    command: list[str],
    *,
    env: dict[str, str],
    launch_state: dict[str, Any],
) -> subprocess.Popen[str]:
    if not worker_os_sandbox_enabled():
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
    from democrai.core.infrastructure.sandbox import launcher as sandbox_launcher

    return sandbox_launcher.popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        state=launch_state,
    )


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
    resolved: list[str] = list(system_read_paths())
    seen: set[str] = set(resolved)
    candidates: list[str] = []
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


def worker_path_overrides(engine_id: str) -> dict[str, str]:
    return {
        "env": str(get_engine_local_env_path(engine_id)),
        "cache": str(get_engine_local_cache_path(engine_id)),
        "config": str(get_engine_local_config_path(engine_id)),
        "tmp": str(get_engine_local_tmp_path(engine_id)),
    }


def worker_landlock_paths() -> dict[str, list[str]]:
    return {
        "read_only": list(_worker_platform_read_paths()),
        "read_write": [str(logs_dir().resolve())],
    }


def build_engine_worker_init_payload(
    *,
    engine_id: str,
    config: dict[str, Any],
    class_only: bool,
) -> dict[str, Any]:
    logging_config = worker_logging_config()
    landlock_paths = worker_landlock_paths()
    return {
        "engine_id": engine_id,
        "config": config,
        "class_only": bool(class_only),
        "logging_config": logging_config,
        "log_dir": str(logs_dir().resolve()),
        "landlock_enabled": False,
        "path_overrides": worker_path_overrides(engine_id),
        "landlock_read_only_paths": landlock_paths["read_only"],
        "landlock_read_write_paths": landlock_paths["read_write"],
        "env": get_engine_runtime_env(engine_id),
        "access": [
            rule.to_dict()
            for rule in worker_runtime_access(
                engine_id=engine_id,
                config=config,
                logging_config=logging_config,
            )
        ],
        "allowed_imports": get_engine_allowed_imports(
            engine_id,
            "runtime",
        ),
        "allowed_subprocess_commands": get_engine_allowed_subprocess_commands(
            engine_id,
            "runtime",
        ),
    }


class EngineWorkerSubject:
    def __init__(
        self,
        *,
        engine_id: str,
        config: dict[str, Any],
        class_only: bool = False,
    ) -> None:
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
        self._control_conn = None
        self._control_channel: LocalBinaryPayloadChannel | None = None
        self._stderr_reader = None
        self._stderr_tail: list[str] = []
        self._stderr_lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None
        self._parent_conn = None
        self._parent_channel: LocalBinaryPayloadChannel | None = None
        self._parent_request_thread: threading.Thread | None = None
        self._start(dict(config), class_only=class_only)

    def _start(self, config: dict[str, Any], *, class_only: bool = False) -> None:
        control_endpoint = create_local_listener("engine-worker-control")
        parent_endpoint = create_local_listener("engine-worker-parent")
        with process_guard_bypass_context():
            env = dict(os.environ)
            env = _with_engine_temp_env(env, self._engine_id)
            env.update(control_endpoint.env("DEMOCRAI_ENGINE_WORKER_CONTROL"))
            env.update(parent_endpoint.env("DEMOCRAI_ENGINE_WORKER_PARENT"))
            env["PYTHONFAULTHANDLER"] = "1"
            env["PYTHONUNBUFFERED"] = "1"
            app_pythonpath = application_pythonpath()
            env.pop("PYTHONPATH", None)
            command = [
                str(get_engine_venv_python_path(self._engine_id)),
                "-c",
                _WORKER_BOOTSTRAP_CODE,
                "democrai.core.application.ai.engine.worker",
                app_pythonpath,
            ]
            init_payload = build_engine_worker_init_payload(
                engine_id=self._engine_id,
                config=config,
                class_only=class_only,
            )
            self._process = _spawn_engine_worker_process(
                command,
                env=env,
                launch_state=_engine_worker_launch_state(
                    engine_id=self._engine_id,
                    access=payload_access_rules(list(init_payload.get("access") or [])),
                ),
            )
            if self._process is not None and self._process.stderr is not None:
                self._stderr_reader = self._process.stderr
            try:
                self._control_conn = accept_connection(
                    control_endpoint,
                    process=self._process,
                    timeout_seconds=10.0,
                )
                self._control_channel = LocalBinaryPayloadChannel(
                    self._control_conn,
                    shared_memory_package_sid=getattr(
                        self._process,
                        "democrai_os_sandbox_appcontainer_sid",
                        "",
                    ),
                )
                threading.Thread(
                    target=self._accept_parent_connection,
                    args=(parent_endpoint,),
                    name=f"engine-worker-parent-accept-{self._engine_id}",
                    daemon=True,
                ).start()
            except Exception as exc:
                message = self._worker_start_failure_message(
                    stage="control_connect",
                    error=exc,
                )
                parent_endpoint.close()
                self.close()
                raise RuntimeError(message) from exc
            threading.Thread(
                target=self._read_responses,
                name=f"engine-worker-reader-{self._engine_id}",
                daemon=True,
            ).start()
            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                name=f"engine-worker-stderr-{self._engine_id}",
                daemon=True,
            )
            self._stderr_thread.start()
            self._request("init", init_payload)

    def _accept_parent_connection(self, parent_endpoint) -> None:
        try:
            self._parent_conn = accept_connection(
                parent_endpoint,
                process=self._process,
                timeout_seconds=86400.0,
            )
            self._parent_channel = LocalBinaryPayloadChannel(
                self._parent_conn,
                shared_memory_package_sid=getattr(
                    self._process,
                    "democrai_os_sandbox_appcontainer_sid",
                    "",
                ),
            )
        except Exception:
            return
        self._parent_request_thread = threading.Thread(
            target=self._read_parent_requests,
            name=f"engine-worker-parent-request-{self._engine_id}",
            daemon=True,
        )
        self._parent_request_thread.start()

    def _read_responses(self) -> None:
        try:
            while self._control_channel is not None:
                response = python_value(self._control_channel.recv())
                response_id = str(response.get("id") or "")
                with self._response_condition:
                    if response.get("stream"):
                        self._stream_responses.setdefault(response_id, []).append(response)
                    else:
                        self._responses[response_id] = response
                    self._response_condition.notify_all()
        except (EOFError, OSError, BrokenPipeError):
            pass
        finally:
            with self._response_condition:
                self._closed = True
                self._response_condition.notify_all()

    def _read_stderr(self) -> None:
        reader = self._stderr_reader
        if reader is None:
            return
        try:
            while True:
                line = reader.readline()
                if not line:
                    break
                text = str(line).rstrip()
                if not text:
                    continue
                with self._stderr_lock:
                    self._stderr_tail.append(text)
                    if len(self._stderr_tail) > 500:
                        self._stderr_tail = self._stderr_tail[-500:]
        except Exception:
            return

    def _worker_stderr_tail(self) -> str:
        with self._stderr_lock:
            return "\n".join(self._stderr_tail[-300:])

    def _worker_start_failure_message(self, *, stage: str, error: BaseException) -> str:
        process = self._process
        return_code = process.poll() if process is not None else None
        status = "still_running" if process is not None and return_code is None else "exited"
        stderr_tail = self._worker_stderr_tail()
        reader = self._stderr_reader
        if not stderr_tail and return_code is not None and reader is not None:
            try:
                stderr_tail = str(reader.read() or "").strip()
            except Exception:
                stderr_tail = ""
        return ChildProcessFailure.format(
            subject=f"engine:{self._engine_id}",
            stage=stage,
            error="engine_worker_start_failed",
            returncode=return_code,
            details={
                "engine_id": self._engine_id,
                "return_code": return_code,
                "status": status,
                "error": error,
            },
            output_tail=stderr_tail,
        )

    def _log_worker_no_response(self, *, operation: str, return_code: int | None) -> str:
        process = self._process
        if return_code is None and process is not None:
            try:
                process.wait(timeout=2.0)
                return_code = process.poll()
            except subprocess.TimeoutExpired:
                return_code = process.poll()
        thread = self._stderr_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)
        stderr_tail = self._worker_stderr_tail()
        still_running = process is not None and process.poll() is None
        signal_text = ""
        if isinstance(return_code, int) and return_code < 0:
            try:
                signal_text = f" signal={signal.Signals(-return_code).name}"
            except Exception:
                signal_text = f" signal={-return_code}"
        status = "still_running_after_pipe_close" if still_running else "closed"
        message = ChildProcessFailure.format(
            subject=f"engine:{self._engine_id}",
            stage=operation,
            error=f"engine_worker_no_response:{return_code}",
            details={
                "engine_id": self._engine_id,
                "operation": operation,
                "status": status,
                **({"signal": signal_text.split("=", 1)[1]} if signal_text else {}),
            },
            output_tail=stderr_tail,
        )
        try:
            app_ctx().logger.error(
                f"[EngineWorkerSubject] Worker closed without response\n{message}"
            )
        except Exception:
            pass
        return message

    def _read_parent_requests(self) -> None:
        try:
            while self._parent_channel is not None:
                request = python_value(self._parent_channel.recv())
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
            if self._parent_channel is None:
                return
            self._parent_channel.send_json(response, json_value)

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
        if self._process is None or self._control_channel is None:
            raise RuntimeError("engine_worker_not_started")
        if self._process.poll() is not None:
            raise RuntimeError(f"engine_worker_exited:{self._process.returncode}")
        request_id = uuid.uuid4().hex
        with self._write_lock:
            self._control_channel.send_json(
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
                },
                json_value,
            )
        with self._response_condition:
            ready = self._response_condition.wait_for(
                lambda: request_id in self._responses or self._closed,
                timeout=engine_worker_init_timeout_seconds()
                if operation == "init"
                else None,
            )
            if not ready and operation == "init":
                return_code = self._process.poll()
                message = self._log_worker_no_response(
                    operation=operation,
                    return_code=return_code,
                )
                raise RuntimeError(message)
            if request_id not in self._responses and self._closed:
                return_code = self._process.poll()
                message = self._log_worker_no_response(
                    operation=operation,
                    return_code=return_code,
                )
                raise RuntimeError(message)
            response = self._responses.pop(request_id)
        if not bool(response.get("ok")):
            error = str(response.get("error") or "engine_worker_error")
            details = str(response.get("traceback") or "").strip()
            stderr_tail = self._worker_stderr_tail()
            message = ChildProcessFailure.format(
                subject=f"engine:{self._engine_id}",
                stage=operation,
                error=error,
                details={
                    "engine_id": self._engine_id,
                    "operation": operation,
                    "payload_keys": sorted(payload.keys()),
                },
                traceback=details,
                output_tail=stderr_tail,
            )
            try:
                app_ctx().logger.error(
                    f"[EngineWorkerSubject] Worker request failed\n{message}"
                )
            except Exception:
                pass
            raise RuntimeError(error + (f"\n{details}" if details else ""))
        return response.get("result")

    def _send_request(self, operation: str, payload: dict[str, Any]) -> str:
        if self._process is None or self._control_channel is None:
            raise RuntimeError("engine_worker_not_started")
        if self._process.poll() is not None:
            raise RuntimeError(f"engine_worker_exited:{self._process.returncode}")
        request_id = uuid.uuid4().hex
        with self._write_lock:
            self._control_channel.send_json(
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
                },
                json_value,
            )
        return request_id

    def _wait_stream_response(self, request_id: str) -> dict[str, Any]:
        with self._response_condition:
            self._response_condition.wait_for(
                lambda: bool(self._stream_responses.get(request_id)) or self._closed
            )
            messages = self._stream_responses.get(request_id)
            if not messages and self._closed:
                return_code = self._process.poll() if self._process is not None else None
                message = self._log_worker_no_response(
                    operation="invoke_stream",
                    return_code=return_code,
                )
                raise RuntimeError(message)
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
                        try:
                            app_ctx().logger.error(
                                "[EngineWorkerSubject] Worker stream failed\n"
                                + ChildProcessFailure.format(
                                    subject=f"engine:{self._engine_id}",
                                    stage=f"invoke_stream:{method}",
                                    error=error,
                                    details={"engine_id": self._engine_id},
                                    traceback=details,
                                    output_tail=self._worker_stderr_tail(),
                                )
                            )
                        except Exception:
                            pass
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
            cleanup = getattr(process, "cleanup", None)
            if callable(cleanup):
                cleanup()
        finally:
            for channel in (self._control_channel, self._parent_channel):
                try:
                    if channel is not None:
                        channel.close()
                except Exception:
                    pass
            for handle in (self._control_conn, self._parent_conn):
                try:
                    if handle is not None:
                        handle.close()
                except Exception:
                    pass
            self._control_conn = None
            self._parent_conn = None
            self._control_channel = None
            self._parent_channel = None
