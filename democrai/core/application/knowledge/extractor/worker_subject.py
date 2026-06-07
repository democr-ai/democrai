from __future__ import annotations

import contextlib
import contextvars
import json
import os
import site
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload
from democrai.core.runtime.foundation.paths import get_base_dir
from democrai.core.runtime.foundation.paths import is_frozen
from democrai.core.runtime.dependencies.extractor_env import get_extractor_venv_python_path


_AUTH_SECRET_PLACEHOLDER = "change-me-with-a-long-random-secret"

_WORKER_CONFIG_KEYS = (
    "auth.jwt_secret",
    "auth.jwt_algorithm",
    "auth.jwt_issuer",
    "auth.jwt_audience",
    "auth.jwt_tid",
    "auth.jwt_internal_service_ttl_seconds",
    "ai.engine_orchestrator.transport",
    "ai.engine_orchestrator.socket_path",
    "ai.engine_orchestrator.host",
    "ai.engine_orchestrator.port",
    "ai.engine_orchestrator.tls.enabled",
    "ai.engine_orchestrator.tls.ca_file",
    "ai.engine_orchestrator.max_message_mb",
    "ai.engine_orchestrator.invoke_timeout_seconds",
)

_EXTRACTOR_ENV_KEYS = {
    "DOCLING_ARTIFACTS_PATH",
    "HF_DATASETS_CACHE",
    "HF_HOME",
    "HF_HUB_CACHE",
    "HF_HUB_OFFLINE",
    "HUGGINGFACE_HUB_CACHE",
    "MODELSCOPE_CACHE",
    "MPLCONFIGDIR",
    "NETRC",
    "PATH",
    "PYTHONPATH",
    "TESSDATA_PREFIX",
    "TEMP",
    "TMP",
    "TMPDIR",
    "TORCH_HOME",
    "TRANSFORMERS_CACHE",
    "TRANSFORMERS_OFFLINE",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
}


def _application_root() -> str:
    if is_frozen():
        return str(Path(get_base_dir()).resolve())
    return str(Path(get_base_dir()).resolve().parent)


def _application_pythonpath() -> str:
    entries: list[str] = [_application_root()]
    for value in [*site.getsitepackages(), site.getusersitepackages()]:
        raw = str(value or "").strip()
        if raw and raw not in entries:
            entries.append(raw)
    for value in sys.path:
        raw = str(value or "").strip()
        if not raw or raw in entries:
            continue
        if "site-packages" in raw or "dist-packages" in raw:
            entries.append(raw)
    return os.pathsep.join(entries)


_WORKER_BOOTSTRAP_CODE = (
    "import os,runpy,sys;"
    "module=sys.argv[1];"
    "paths=[p for p in sys.argv[2].split(os.pathsep) if p];"
    "root=paths[0] if paths else '';"
    "deps=paths[1:];"
    "sys.path.insert(0, root) if root and root not in sys.path else None;"
    "[sys.path.append(p) for p in deps if p not in sys.path];"
    "runpy.run_module(module, run_name='__main__')"
)


def _clean_worker_env() -> dict[str, str]:
    env = {
        str(key): str(value)
        for key, value in os.environ.items()
        if str(key) not in _EXTRACTOR_ENV_KEYS
    }
    env["PATH"] = os.defpath
    env.pop("PYTHONPATH", None)
    return env


def _with_auth_secret_env(env: dict[str, str]) -> dict[str, str]:
    config = getattr(app_ctx(), "config", None)
    if config is None:
        return env
    secret = str(config.get("auth.jwt_secret") or "").strip()
    if secret and secret != _AUTH_SECRET_PLACEHOLDER:
        env["AUTH_SECRET_KEY"] = secret
    return env


def worker_runtime_config() -> dict[str, Any]:
    config = getattr(app_ctx(), "config", None)
    getter = getattr(config, "get", None)
    if not callable(getter):
        return {}
    marker = object()
    values: dict[str, Any] = {}
    for key in _WORKER_CONFIG_KEYS:
        value = getter(key, marker)
        if value is not marker:
            values[key] = value
    return values


def _network_endpoint_payloads_from_access(
    access: tuple[AccessManifestRule, ...],
) -> list[dict[str, Any]]:
    from democrai.core.application.access_policy import ResourceType
    from democrai.core.infrastructure.sandbox.os.normalize import (
        dedupe_endpoints,
        endpoint_from_target,
    )

    endpoints = []
    for rule in access:
        resource = rule.resource
        if resource.resource_type != ResourceType.NETWORK:
            continue
        endpoint = endpoint_from_target(
            resource.normalized_target,
            source=f"extractor:{rule.subject.subject_name}",
            purpose=f"extractor_{resource.operation.value}",
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return [
        {
            "host": endpoint.host,
            "port": endpoint.port,
            "protocol": endpoint.protocol,
            "source": endpoint.source,
            "purpose": endpoint.purpose,
        }
        for endpoint in dedupe_endpoints(endpoints)
    ]


def _apply_os_network_allowlist_to_worker_process(
    pid: int | None,
    *,
    access: tuple[AccessManifestRule, ...],
) -> None:
    if pid is None:
        return
    from democrai.core.infrastructure.sandbox.os.helper import (
        apply_application_network_endpoints_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.state import (
        is_application_network_allowlist_active,
        is_application_network_allowlist_enabled,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    ctx = app_ctx()
    config = ctx.config
    if not is_application_network_allowlist_enabled(config):
        return
    if not is_application_network_allowlist_active():
        return
    endpoints = _network_endpoint_payloads_from_access(access)
    if not endpoints:
        return
    with process_guard_bypass_context():
        apply_application_network_endpoints_with_helper(
            endpoints,
            pid=pid,
            config=config,
        )


def _stop_process_after_start_failure(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    with contextlib.suppress(Exception):
        process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(Exception):
            process.kill()
        with contextlib.suppress(Exception):
            process.wait(timeout=2.0)


def _close_fd_after_start_failure(fd: int) -> None:
    with contextlib.suppress(OSError):
        os.close(fd)


class ExtractorWorkerSubject:
    def __init__(
        self,
        *,
        extractor_id: str,
        phase: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._extractor_id = str(extractor_id or "").strip().lower()
        self._phase = str(phase or "runtime").strip().lower()
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._response_condition = threading.Condition()
        self._responses: dict[str, dict[str, Any]] = {}
        self._closed = False
        self._process: subprocess.Popen[str] | None = None
        self._stdout_reader = None
        self._reader = None
        self._writer = None
        self._parent_request_reader = None
        self._parent_request_writer = None
        self._start(dict(config or {}))

    def _start(self, config: dict[str, Any]) -> None:
        from democrai.core.application.knowledge.extractor.runtime import (
            get_extractor_access,
            get_extractor_allowed_imports,
        )

        parent_read, child_write = os.pipe()
        child_read, parent_write = os.pipe()
        parent_request_read, child_request_write = os.pipe()
        child_response_read, parent_response_write = os.pipe()
        env = _with_auth_secret_env(_clean_worker_env())
        env["DEMOCRAI_EXTRACTOR_WORKER_READ_FD"] = str(child_read)
        env["DEMOCRAI_EXTRACTOR_WORKER_WRITE_FD"] = str(child_write)
        env["DEMOCRAI_EXTRACTOR_WORKER_PARENT_REQUEST_FD"] = str(child_request_write)
        env["DEMOCRAI_EXTRACTOR_WORKER_PARENT_RESPONSE_FD"] = str(child_response_read)
        command = [
            str(get_extractor_venv_python_path(self._extractor_id)),
            "-c",
            _WORKER_BOOTSTRAP_CODE,
            "democrai.core.application.knowledge.extractor.worker",
            _application_pythonpath(),
        ]
        phase_access = get_extractor_access(
            self._extractor_id,
            self._phase,
        )
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                pass_fds=(
                    child_read,
                    child_write,
                    child_request_write,
                    child_response_read,
                ),
                env=env,
                text=True,
                bufsize=1,
            )
        finally:
            os.close(child_read)
            os.close(child_write)
            os.close(child_request_write)
            os.close(child_response_read)
        try:
            _apply_os_network_allowlist_to_worker_process(
                self._process.pid,
                access=phase_access,
            )
        except Exception:
            _stop_process_after_start_failure(self._process)
            _close_fd_after_start_failure(parent_read)
            _close_fd_after_start_failure(parent_write)
            _close_fd_after_start_failure(parent_request_read)
            _close_fd_after_start_failure(parent_response_write)
            raise
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
            name=f"extractor-worker-reader-{self._extractor_id}",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_parent_requests,
            name=f"extractor-worker-parent-request-{self._extractor_id}",
            daemon=True,
        ).start()
        if self._process.stdout is not None:
            self._stdout_reader = self._process.stdout
            stdout_context = contextvars.copy_context()
            threading.Thread(
                target=lambda: stdout_context.run(self._read_stdout),
                name=f"extractor-worker-stdout-{self._extractor_id}",
                daemon=True,
            ).start()
        self._request(
            "init",
            {
                "extractor_id": self._extractor_id,
                "phase": self._phase,
                "config": config,
                "runtime_config": worker_runtime_config(),
                "access": [
                    rule.to_dict()
                    for rule in phase_access
                ],
                "allowed_imports": get_extractor_allowed_imports(
                    self._extractor_id,
                    self._phase,
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
            response = {
                "id": response_id,
                "parent_response": True,
                "ok": True,
                "result": result,
            }
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
        from democrai.core.runtime.dependencies.extractor_env import (
            get_extractor_local_tmp_path,
        )
        from democrai.core.runtime.foundation.app import app_ctx

        media = getattr(app_ctx(), "media", None)
        if media is None:
            raise RuntimeError("media_provider_unavailable")
        if operation == "media.load":
            storage_path = str(payload.get("storage_path") or "").strip()
            if not storage_path:
                raise ValueError("storage_path_required")
            return bytes(media.load(storage_path))
        if operation == "media.materialize":
            storage_path = str(payload.get("storage_path") or "").strip()
            if not storage_path:
                raise ValueError("storage_path_required")
            destination_dir = str(payload.get("destination_dir") or "").strip()
            if not destination_dir:
                destination_dir = str(get_extractor_local_tmp_path(self._extractor_id))
            materialized = media.get_path(storage_path, destination_dir=destination_dir)
            return {
                "path": str(materialized.path),
                "temporary": bool(materialized.temporary),
            }
        raise RuntimeError(f"extractor_worker_parent_operation_unknown:{operation}")

    def _read_stdout(self) -> None:
        from democrai.core.application.knowledge.extractor.install_events import (
            emit_extractor_install_output,
        )

        reader = self._stdout_reader
        if reader is None:
            return
        try:
            while True:
                line = reader.readline()
                if not line:
                    break
                text = str(line or "").rstrip()
                if text:
                    emit_extractor_install_output(text, phase="install")
        finally:
            try:
                reader.close()
            except Exception:
                pass

    def _request(self, operation: str, payload: dict[str, Any]) -> Any:
        if self._process is None or self._reader is None or self._writer is None:
            raise RuntimeError("extractor_worker_not_started")
        if self._process.poll() is not None:
            raise RuntimeError(f"extractor_worker_exited:{self._process.returncode}")
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
                                f"extractor_worker_subject.{operation}"
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
                raise RuntimeError(f"extractor_worker_no_response:{return_code}")
            response = self._responses.pop(request_id)
        if not bool(response.get("ok")):
            error = str(response.get("error") or "extractor_worker_error")
            details = str(response.get("traceback") or "").strip()
            try:
                app_ctx().logger.error(
                    "[ExtractorWorkerSubject] Worker request failed "
                    f"extractor_id={self._extractor_id} phase={self._phase} "
                    f"operation={operation} payload_keys={sorted(payload.keys())} "
                    f"error={error}"
                    + (f"\n{details}" if details else "")
                )
            except Exception:
                pass
            raise RuntimeError(error + (f"\n{details}" if details else ""))
        return response.get("result")

    def invoke_class(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        with self._lock:
            return self._request(
                "invoke_class",
                {
                    "method": method,
                    "payload": payload or {},
                },
            )

    def extract(
        self,
        *,
        config: dict[str, Any],
        files: list[Any],
    ) -> dict[str, Any]:
        with self._lock:
            result = self._request(
                "extract",
                {
                    "config": config,
                    "files": files,
                },
            )
        return dict(result or {})

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
            for handle in (self._stdout_reader, self._reader, self._writer):
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
