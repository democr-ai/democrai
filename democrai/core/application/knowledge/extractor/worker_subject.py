from __future__ import annotations

import asyncio
import contextlib
import contextvars
import os
import site
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.ai.engine.orchestrator.config import (
    EngineOrchestratorConfig,
)
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload
from democrai.core.runtime.foundation.paths import get_base_dir
from democrai.core.runtime.foundation.paths import is_frozen
from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_cache_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_config_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_env_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_tmp_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_venv_python_path
from democrai.core.runtime.ipc.local_binary_payload import LocalBinaryPayloadChannel
from democrai.core.runtime.ipc.local_connection import (
    accept_connection,
    create_local_listener,
)
from democrai.core.infrastructure.process.child_failure import ChildProcessFailure
from democrai.core.infrastructure.sandbox.process_guard import (
    process_guard_bypass_context,
)
from democrai.core.infrastructure.sandbox.worker_launch import (
    build_worker_launch_state,
    payload_access_rules,
)


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
    "[sys.path.remove(p) for p in paths if p in sys.path];"
    "[sys.path.insert(i, p) for i, p in enumerate(paths)];"
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


def _with_extractor_temp_env(env: dict[str, str], extractor_id: str) -> dict[str, str]:
    tmp_path = str(get_extractor_local_tmp_path(extractor_id))
    env["TMPDIR"] = tmp_path
    env["TEMP"] = tmp_path
    env["TMP"] = tmp_path
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
    orchestrator_config = EngineOrchestratorConfig.load(config)
    if orchestrator_config.transport == "unix":
        values["ai.engine_orchestrator.socket_path"] = (
            orchestrator_config.socket_path
        )
    return values


def worker_runtime_env(phase: str) -> dict[str, str]:
    if str(phase or "").strip().lower() != "runtime":
        return {}
    return {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


def worker_os_sandbox_enabled() -> bool:
    config = getattr(app_ctx(), "config", None)
    getter = getattr(config, "get", None)
    if not callable(getter):
        return False
    return bool(getter("sandbox.os.enabled", False))


def worker_path_overrides(extractor_id: str) -> dict[str, str]:
    return {
        "env": str(get_extractor_local_env_path(extractor_id)),
        "cache": str(get_extractor_local_cache_path(extractor_id)),
        "config": str(get_extractor_local_config_path(extractor_id)),
        "tmp": str(get_extractor_local_tmp_path(extractor_id)),
    }


def build_extractor_worker_init_payload(
    *,
    extractor_id: str,
    phase: str,
    config: dict[str, Any],
    access: tuple[AccessManifestRule, ...],
    allowed_imports: list[str],
) -> dict[str, Any]:
    return {
        "extractor_id": extractor_id,
        "phase": phase,
        "config": config,
        "runtime_config": worker_runtime_config(),
        "env": worker_runtime_env(phase),
        "path_overrides": worker_path_overrides(extractor_id),
        "access": [
            rule.to_dict()
            for rule in access
        ],
        "allowed_imports": allowed_imports,
    }


def _run_async_blocking(coro):
    return asyncio.run(coro)


def _parent_ai_provider_result(
    result: Any,
    provider_ref: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in dict(result or {}).items()
        if key != "provider"
    }
    if payload.get("status") == "ok":
        payload["provider_ref"] = provider_ref
    return payload


async def _parent_ai_resolve_provider(provider_ref: dict[str, Any]) -> Any:
    from democrai.core.application.ai.orchestrator import model_orchestrator

    selector_type = str(provider_ref.get("selector_type") or "").strip()
    if selector_type == "model_registry_id":
        result = await model_orchestrator.get_provider_by_model_registry_id(
            int(provider_ref.get("model_registry_id") or 0),
            confirm_swap=bool(provider_ref.get("confirm_swap")),
        )
    elif selector_type == "objective":
        result = await model_orchestrator.get_provider_for_objective(
            str(provider_ref.get("objective") or ""),
            required_capabilities=[
                str(item)
                for item in list(provider_ref.get("required_capabilities") or [])
                if str(item).strip()
            ],
            prefer_local=provider_ref.get("prefer_local"),
        )
    else:
        raise RuntimeError(f"extractor_worker_parent_ai_selector_unknown:{selector_type}")
    provider = dict(result or {}).get("provider")
    if dict(result or {}).get("status") != "ok" or provider is None:
        raise RuntimeError(
            str(dict(result or {}).get("error") or "extractor_worker_parent_ai_unavailable")
        )
    return provider


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


def _extractor_worker_launch_state(
    *,
    extractor_id: str,
    access: tuple[AccessManifestRule, ...],
) -> dict[str, Any]:
    return build_worker_launch_state(
        subject_kind="extractor",
        subject_name=extractor_id,
        access=access,
        inherit_os_sandbox_helper_env=True,
    )


def _spawn_extractor_worker_process(
    command: list[str],
    *,
    env: dict[str, str],
    launch_state: dict[str, Any],
) -> subprocess.Popen[str]:
    if not worker_os_sandbox_enabled():
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )
    from democrai.core.infrastructure.sandbox import launcher as sandbox_launcher

    return sandbox_launcher.popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        state=launch_state,
    )


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
        self._stdout_tail: list[str] = []
        self._stdout_lock = threading.Lock()
        self._stderr_reader = None
        self._stderr_tail: list[str] = []
        self._stderr_lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None
        self._control_conn = None
        self._control_channel: LocalBinaryPayloadChannel | None = None
        self._parent_conn = None
        self._parent_channel: LocalBinaryPayloadChannel | None = None
        self._start(dict(config or {}))

    def _start(self, config: dict[str, Any]) -> None:
        from democrai.core.application.knowledge.extractor.runtime import (
            get_extractor_access,
            get_extractor_allowed_imports,
        )

        control_endpoint = create_local_listener("extractor-worker-control")
        parent_endpoint = create_local_listener("extractor-worker-parent")
        stdout_context = contextvars.copy_context()
        with process_guard_bypass_context():
            env = _with_extractor_temp_env(
                _with_auth_secret_env(_clean_worker_env()),
                self._extractor_id,
            )
            env.update(control_endpoint.env("DEMOCRAI_EXTRACTOR_WORKER_CONTROL"))
            env.update(parent_endpoint.env("DEMOCRAI_EXTRACTOR_WORKER_PARENT"))
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
            init_payload = build_extractor_worker_init_payload(
                extractor_id=self._extractor_id,
                phase=self._phase,
                config=config,
                access=phase_access,
                allowed_imports=get_extractor_allowed_imports(
                    self._extractor_id,
                    self._phase,
                ),
            )
            try:
                self._process = _spawn_extractor_worker_process(
                    command,
                    env=env,
                    launch_state=_extractor_worker_launch_state(
                        extractor_id=self._extractor_id,
                        access=payload_access_rules(
                            list(init_payload.get("access") or [])
                        ),
                    ),
                )
                if self._process is not None and self._process.stdout is not None:
                    self._stdout_reader = self._process.stdout
                if self._process is not None and self._process.stderr is not None:
                    self._stderr_reader = self._process.stderr
            except Exception:
                control_endpoint.close()
                parent_endpoint.close()
                raise
        with process_guard_bypass_context():
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
                self._parent_conn = accept_connection(
                    parent_endpoint,
                    process=self._process,
                    timeout_seconds=10.0,
                )
                self._parent_channel = LocalBinaryPayloadChannel(
                    self._parent_conn,
                    shared_memory_package_sid=getattr(
                        self._process,
                        "democrai_os_sandbox_appcontainer_sid",
                        "",
                    ),
                )
            except Exception as exc:
                message = self._worker_start_failure_message(
                    stage="control_connect",
                    error=exc,
                )
                _stop_process_after_start_failure(self._process)
                control_endpoint.close()
                parent_endpoint.close()
                raise RuntimeError(message) from exc
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
            if self._stdout_reader is not None:
                threading.Thread(
                    target=lambda: stdout_context.run(self._read_stdout),
                    name=f"extractor-worker-stdout-{self._extractor_id}",
                    daemon=True,
                ).start()
            if self._stderr_reader is not None:
                self._stderr_thread = threading.Thread(
                    target=self._read_stderr,
                    name=f"extractor-worker-stderr-{self._extractor_id}",
                    daemon=True,
                )
                self._stderr_thread.start()
            self._request("init", init_payload)

    def _read_responses(self) -> None:
        try:
            while self._control_channel is not None:
                response = python_value(self._control_channel.recv())
                response_id = str(response.get("id") or "")
                with self._response_condition:
                    self._responses[response_id] = response
                    self._response_condition.notify_all()
        except (EOFError, OSError, BrokenPipeError):
            pass
        finally:
            with self._response_condition:
                self._closed = True
                self._response_condition.notify_all()

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
            from democrai.core.runtime.foundation.app import request_context_scope

            with request_context_scope(dict(request.get("request_context") or {})):
                result = self._parent_request(
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
            if self._parent_channel is None:
                return
            self._parent_channel.send_json(response, json_value)

    def _parent_request(self, operation: str, payload: dict[str, Any]) -> Any:
        if operation.startswith("media."):
            return self._parent_media_request(operation, payload)
        if operation.startswith("ai."):
            return self._parent_ai_request(operation, payload)
        raise RuntimeError(f"extractor_worker_parent_operation_unknown:{operation}")

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

    def _parent_ai_request(self, operation: str, payload: dict[str, Any]) -> Any:
        if operation == "ai.get_provider_by_model_registry_id":
            return _run_async_blocking(
                self._parent_ai_get_provider_by_model_registry_id(payload)
            )
        if operation == "ai.get_provider_for_objective":
            return _run_async_blocking(self._parent_ai_get_provider_for_objective(payload))
        if operation == "ai.invoke_provider":
            return _run_async_blocking(self._parent_ai_invoke_provider(payload))
        if operation == "ai.cancel_request":
            from democrai.core.application.ai.engine.runtime.requests import (
                cancel_runtime_request,
            )

            return cancel_runtime_request(str(payload.get("request_id") or ""))
        raise RuntimeError(f"extractor_worker_parent_operation_unknown:{operation}")

    async def _parent_ai_get_provider_by_model_registry_id(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        from democrai.core.application.ai.orchestrator import model_orchestrator

        model_registry_id = int(payload.get("model_registry_id") or 0)
        result = await model_orchestrator.get_provider_by_model_registry_id(
            model_registry_id,
            confirm_swap=bool(payload.get("confirm_swap")),
        )
        return _parent_ai_provider_result(
            result,
            {
                "selector_type": "model_registry_id",
                "model_registry_id": model_registry_id,
                "confirm_swap": bool(payload.get("confirm_swap")),
            },
        )

    async def _parent_ai_get_provider_for_objective(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        from democrai.core.application.ai.orchestrator import model_orchestrator

        objective = str(payload.get("objective") or "")
        required_capabilities = [
            str(item)
            for item in list(payload.get("required_capabilities") or [])
            if str(item).strip()
        ]
        result = await model_orchestrator.get_provider_for_objective(
            objective,
            required_capabilities=required_capabilities,
            prefer_local=payload.get("prefer_local"),
        )
        return _parent_ai_provider_result(
            result,
            {
                "selector_type": "objective",
                "objective": objective,
                "required_capabilities": required_capabilities,
                "prefer_local": payload.get("prefer_local"),
            },
        )

    async def _parent_ai_invoke_provider(self, payload: dict[str, Any]) -> Any:
        provider_ref = dict(payload.get("provider_ref") or {})
        provider = await _parent_ai_resolve_provider(provider_ref)
        method = str(payload.get("method") or "").strip()
        if not method:
            raise RuntimeError("extractor_worker_parent_ai_method_required")
        target = getattr(provider, method, None)
        if not callable(target):
            raise RuntimeError(f"extractor_worker_parent_ai_method_unknown:{method}")
        kwargs = dict(payload.get("kwargs") or {})
        result = target(**kwargs)
        if hasattr(result, "__aiter__"):
            items = []
            async for item in result:
                items.append(item)
            return items
        if asyncio.iscoroutine(result):
            return await result
        return result

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
                    with self._stdout_lock:
                        self._stdout_tail.append(text)
                        if len(self._stdout_tail) > 200:
                            self._stdout_tail = self._stdout_tail[-200:]
                    emit_extractor_install_output(text, phase="install")
        finally:
            try:
                reader.close()
            except Exception:
                pass

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

    def _worker_stdout_tail(self) -> str:
        with self._stdout_lock:
            return "\n".join(self._stdout_tail[-80:])

    def _worker_output_tail(self) -> tuple[str, str]:
        stderr_tail = self._worker_stderr_tail()
        if stderr_tail:
            return stderr_tail, "stderr tail"
        return self._worker_stdout_tail(), "stdout tail"

    def _worker_start_failure_message(self, *, stage: str, error: BaseException) -> str:
        process = self._process
        return_code = process.poll() if process is not None else None
        status = "still_running" if process is not None and return_code is None else "exited"
        output_tail, output_label = self._worker_output_tail()
        reader = self._stderr_reader
        if not output_tail and return_code is not None and reader is not None:
            try:
                output_tail = str(reader.read() or "").strip()
                output_label = "stderr tail"
            except Exception:
                output_tail = ""
        return ChildProcessFailure.format(
            subject=f"extractor:{self._extractor_id}",
            stage=stage,
            error="extractor_worker_start_failed",
            returncode=return_code,
            details={
                "extractor_id": self._extractor_id,
                "phase": self._phase,
                "return_code": return_code,
                "status": status,
                "error": error,
            },
            output_tail=output_tail,
            output_label=output_label,
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
        output_tail, output_label = self._worker_output_tail()
        still_running = process is not None and process.poll() is None
        status = "still_running_after_pipe_close" if still_running else "closed"
        message = ChildProcessFailure.format(
            subject=f"extractor:{self._extractor_id}",
            stage=operation,
            error=f"extractor_worker_no_response:{return_code}",
            details={
                "extractor_id": self._extractor_id,
                "phase": self._phase,
                "operation": operation,
                "status": status,
            },
            output_tail=output_tail,
            output_label=output_label,
        )
        try:
            app_ctx().logger.error(
                f"[ExtractorWorkerSubject] Worker closed without response\n{message}"
            )
        except Exception:
            pass
        return message

    def _request(self, operation: str, payload: dict[str, Any]) -> Any:
        if self._process is None or self._control_channel is None:
            raise RuntimeError("extractor_worker_not_started")
        if self._process.poll() is not None:
            raise RuntimeError(f"extractor_worker_exited:{self._process.returncode}")
        request_id = uuid.uuid4().hex
        with self._write_lock:
            self._control_channel.send_json(
                {
                    "id": request_id,
                    "operation": operation,
                    "payload": payload,
                    "request_context": current_request_context_payload(
                        f"extractor_worker_subject.{operation}"
                    ),
                },
                json_value,
            )
        with self._response_condition:
            self._response_condition.wait_for(
                lambda: request_id in self._responses or self._closed
            )
            if request_id not in self._responses and self._closed:
                return_code = self._process.poll()
                message = self._log_worker_no_response(
                    operation=operation,
                    return_code=return_code,
                )
                raise RuntimeError(message)
            response = self._responses.pop(request_id)
        if not bool(response.get("ok")):
            error = str(response.get("error") or "extractor_worker_error")
            details = str(response.get("traceback") or "").strip()
            output_tail, output_label = self._worker_output_tail()
            message = ChildProcessFailure.format(
                subject=f"extractor:{self._extractor_id}",
                stage=operation,
                error=error,
                details={
                    "extractor_id": self._extractor_id,
                    "phase": self._phase,
                    "operation": operation,
                    "payload_keys": sorted(payload.keys()),
                },
                traceback=details,
                output_tail=output_tail,
                output_label=output_label,
            )
            try:
                app_ctx().logger.error(
                    f"[ExtractorWorkerSubject] Worker request failed\n{message}"
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
            cleanup = getattr(process, "cleanup", None)
            if callable(cleanup):
                with contextlib.suppress(Exception):
                    cleanup()
        finally:
            for channel in (self._control_channel, self._parent_channel):
                try:
                    if channel is not None:
                        channel.close()
                except Exception:
                    pass
            for handle in (
                self._stdout_reader,
                self._stderr_reader,
                self._control_conn,
                self._parent_conn,
            ):
                try:
                    if handle is not None:
                        handle.close()
                except Exception:
                    pass
            self._control_conn = None
            self._parent_conn = None
            self._control_channel = None
            self._parent_channel = None
