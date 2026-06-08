"""Install-event handling for pluggable knowledge extractors.

Extractor installation is modeled as a distributed runtime workflow. This
module creates install request events, publishes them on the shared stream, and
keeps node-level and registry-level status synchronized while installation and
readiness checks progress.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from democrai.core.application.ai.engine.install_events import get_runtime_node_id
from democrai.core.application.knowledge.extractor.manifests import (
    get_extractor_manifest,
    load_extractor_class,
)
from democrai.core.application.knowledge.extractor.runtime import (
    check_extractor_ready_runtime,
)
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    ExtractorNodeInstallRegistry,
    ExtractorRegistry,
)
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import (
    app_ctx,
    current_request_context_payload,
    request_context_scope,
)

INSTALL_NETWORK_READY_FILE_ENV = "DEMOCRAI_INSTALL_NETWORK_READY_FILE"
from democrai.core.runtime.foundation.paths import (
    ENGINES_PATH_ENV,
    EXTRACTORS_PATH_ENV,
    MODULES_PATH_ENV,
)
from democrai.core.runtime.lifecycle.process_supervisor import process_supervisor
from democrai.core.application.ai.engine.runtime.environment import application_root


EXTRACTOR_INSTALL_STREAM_ID = "system.extractor.install.events"
EXTRACTOR_INSTALL_OUTPUT_EVENT_NAME = "extractor.install.output"
EXTRACTOR_INSTALL_PROCESS_RESULT_PREFIX = "__DEMOCRAI_EXTRACTOR_INSTALL_RESULT__="
EXTRACTOR_INSTALL_PROCESS_ERROR_PREFIX = "__DEMOCRAI_EXTRACTOR_INSTALL_ERROR__="
EXTRACTOR_INSTALL_PROXY_CONNECT_TARGET_ENV = (
    "DEMOCRAI_EXTRACTOR_INSTALL_PROXY_CONNECT_TARGET"
)
_EXTRACTOR_INSTALL_LOCKS: dict[str, asyncio.Lock] = {}
_INSTALL_OUTPUT_CONTEXT: contextvars.ContextVar[
    dict[str, str] | None
] = contextvars.ContextVar("extractor_install_output_context", default=None)


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@contextlib.contextmanager
def extractor_install_output_context(
    *,
    event_id: str,
    extractor_id: str,
    node_id: str,
    task_id: str | None = None,
):
    token = _INSTALL_OUTPUT_CONTEXT.set(
        {
            "event_id": event_id,
            "extractor_id": extractor_id,
            "node_id": node_id,
            "task_id": task_id or "",
        }
    )
    try:
        yield
    finally:
        _INSTALL_OUTPUT_CONTEXT.reset(token)


def emit_extractor_install_output(
    line: str,
    *,
    phase: str = "install",
    stream: str = "stdout",
    level: str = "info",
) -> None:
    context = _INSTALL_OUTPUT_CONTEXT.get()
    text = line.strip()
    if not context or not text:
        return
    network = getattr(app_ctx(), "network", None)
    loop = getattr(network, "_loop", None) if network is not None else None
    stream_manager = (
        getattr(network, "stream_manager", None) if network is not None else None
    )
    if loop is None or stream_manager is None:
        return
    task_id = context.get("task_id") or ""
    payload = {
        "event_name": EXTRACTOR_INSTALL_OUTPUT_EVENT_NAME,
        "event_id": context["event_id"],
        "extractor_id": context["extractor_id"],
        "node_id": context["node_id"],
        "task_id": task_id,
        "phase": phase,
        "stream": stream,
        "level": level,
        "line": text,
        "timestamp": _utc_now_iso(),
    }
    try:
        asyncio.run_coroutine_threadsafe(
            stream_manager.broadcast(EXTRACTOR_INSTALL_STREAM_ID, payload),
            loop,
        )
        if task_id:
            task_manager = getattr(app_ctx(), "task_manager", None)
            if task_manager is not None:
                label = f"{payload['phase']}: {text}" if payload["phase"] else text
                asyncio.run_coroutine_threadsafe(
                    task_manager.emit_progress(task_id, 0.6, label=label),
                    loop,
                )
    except Exception:
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.debug("[ExtractorInstall] output broadcast skipped", exc_info=True)


def build_install_requested_event(
    *,
    extractor_id: str,
    force: bool = False,
    install_config: dict[str, Any] | None = None,
    requested_by: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Build the event payload that requests extractor installation."""
    manifest = get_extractor_manifest(extractor_id) or {}
    return {
        "event_id": str(uuid.uuid4()),
        "event_name": "extractor.install.requested",
        "extractor_id": extractor_id,
        "manifest_version": str(manifest.get("manifest_version") or "1"),
        "extractor_version": str(manifest.get("version") or ""),
        "force": force,
        "install_config": dict(install_config or {}),
        "source_node_id": get_runtime_node_id(),
        "task_id": task_id or "",
        "request_context": current_request_context_payload(
            "extractor_install_event.build_requested"
        ),
        "requested_by": dict(requested_by or {}),
        "requested_at": _utc_now_iso(),
    }


async def publish_extractor_install_requested(
    *,
    extractor_id: str,
    force: bool = False,
    install_config: dict[str, Any] | None = None,
    requested_by: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Publish an extractor-install request and mark the registry as installing."""
    event = build_install_requested_event(
        extractor_id=extractor_id,
        force=force,
        install_config=install_config,
        requested_by=requested_by,
        task_id=task_id,
    )
    network = getattr(app_ctx(), "network", None)
    if network is None:
        raise RuntimeError("network_unavailable")

    with SessionLocal() as session:
        rows = (
            session.query(ExtractorRegistry)
            .filter(ExtractorRegistry.extractor_id == event["extractor_id"])
            .all()
        )
        if not rows:
            session.add(
                ExtractorRegistry(
                    name=event["extractor_id"],
                    extractor_id=event["extractor_id"],
                    config={},
                    install_config=dict(event.get("install_config") or {}),
                    status="installing",
                    supported=True,
                    file_extensions=[],
                    mime_types=[],
                )
            )
        else:
            for row in rows:
                row.status = "installing"
                row.supported = True
                if install_config is not None:
                    row.install_config = dict(event.get("install_config") or {})
        session.commit()

    _upsert_node_status(
        extractor_id=event["extractor_id"],
        node_id=event["source_node_id"] or get_runtime_node_id(),
        status="installing",
        event_id=event["event_id"],
        manifest_version=str(event.get("manifest_version") or "1"),
    )
    await network.stream_manager.broadcast(EXTRACTOR_INSTALL_STREAM_ID, event)
    return event


def _upsert_node_status(
    *,
    extractor_id: str,
    node_id: str,
    status: str,
    event_id: str | None = None,
    manifest_version: str | None = None,
    last_error: str | None = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    now = utc_now_naive()
    with SessionLocal() as session:
        row = (
            session.query(ExtractorNodeInstallRegistry)
            .filter(
                ExtractorNodeInstallRegistry.extractor_id == extractor_id,
                ExtractorNodeInstallRegistry.node_id == node_id,
            )
            .first()
        )
        if row is None:
            row = ExtractorNodeInstallRegistry(
                extractor_id=extractor_id,
                node_id=node_id,
                status=status,
                last_event_id=event_id,
                manifest_version=manifest_version,
                created_at=now,
            )
            session.add(row)
        else:
            row.status = status
            if event_id is not None:
                row.last_event_id = event_id
            if manifest_version is not None:
                row.manifest_version = manifest_version
        row.last_error = last_error
        row.last_heartbeat_at = now
        if started:
            row.install_started_at = now
        if completed:
            row.install_completed_at = now
        row.updated_at = now
        session.commit()


def _update_extractor_registry_status(
    *,
    extractor_id: str,
    status: str,
    supported: bool | None = None,
) -> None:
    with SessionLocal() as session:
        rows = (
            session.query(ExtractorRegistry)
            .filter(ExtractorRegistry.extractor_id == extractor_id)
            .all()
        )
        if not rows:
            return
        for row in rows:
            row.status = status
            if supported is not None:
                row.supported = supported
        session.commit()


def _already_processed(*, extractor_id: str, node_id: str, event_id: str) -> bool:
    with SessionLocal() as session:
        row = (
            session.query(ExtractorNodeInstallRegistry)
            .filter(
                ExtractorNodeInstallRegistry.extractor_id == extractor_id,
                ExtractorNodeInstallRegistry.node_id == node_id,
            )
            .first()
        )
        if not row or row.last_event_id != event_id:
            return False
        return row.status in {"installed", "error"}


def _set_path_env(env: dict[str, str], name: str, paths: Any) -> None:
    values = [str(path) for path in (paths or ()) if path]
    if values:
        env[name] = os.pathsep.join(values)


def _proxy_connect_target(proxy_url: str) -> str:
    parsed = urlparse(str(proxy_url or "").strip())
    if parsed.hostname != "127.0.0.1" or parsed.port is None:
        return ""
    return f"{parsed.hostname}:{int(parsed.port)}"


async def _apply_os_network_allowlist_to_install_process(
    pid: int | None,
    *,
    env: dict[str, str],
    extractor_id: str,
) -> None:
    if pid is None:
        return
    from democrai.core.infrastructure.sandbox.os.helper import (
        apply_application_network_allowlist_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.base import proxy_endpoint_payload
    from democrai.core.infrastructure.sandbox.os.models import (
        ApplicationNetworkAllowlist,
        NetworkEndpoint,
    )
    from democrai.core.infrastructure.sandbox.os.state import (
        is_application_network_allowlist_enabled,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    ctx = app_ctx()
    config = ctx.config
    if not is_application_network_allowlist_enabled(config):
        return
    endpoints = []
    proxy_url = str(env.get("ALL_PROXY") or env.get("all_proxy") or "").strip()
    if proxy_url:
        proxy_endpoint = proxy_endpoint_payload(proxy_url)
        endpoints.append(
            NetworkEndpoint(
                host=str(proxy_endpoint["host"]),
                port=int(proxy_endpoint["port"]),
                protocol=str(proxy_endpoint["protocol"]),
                source=str(proxy_endpoint["source"]),
                purpose=str(proxy_endpoint["purpose"]),
            )
        )
    allowlist = ApplicationNetworkAllowlist(endpoints=endpoints)

    def _apply() -> None:
        with process_guard_bypass_context():
            apply_application_network_allowlist_with_helper(
                allowlist,
                pid=pid,
                config=config,
            )

    await asyncio.to_thread(_apply)


async def _start_os_network_proxy_for_install(
    env: dict[str, str],
    *,
    extractor_id: str,
) -> str:
    from democrai.core.infrastructure.sandbox.os.helper import (
        start_application_network_proxy_session_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.state import (
        is_application_network_allowlist_enabled,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    ctx = app_ctx()
    config = ctx.config
    if not is_application_network_allowlist_enabled(config):
        return ""
    allowlist = _extractor_install_network_allowlist(extractor_id)
    if not allowlist.endpoints:
        return ""

    def _start() -> dict[str, str]:
        with process_guard_bypass_context():
            return start_application_network_proxy_session_with_helper(
                allowlist,
                config=config,
            )

    session = await asyncio.to_thread(_start)
    proxy_url = session["proxy_url"]
    env["HTTP_PROXY"] = proxy_url
    env["HTTPS_PROXY"] = proxy_url
    env["ALL_PROXY"] = proxy_url
    env["http_proxy"] = proxy_url
    env["https_proxy"] = proxy_url
    env["all_proxy"] = proxy_url
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    env["no_proxy"] = "127.0.0.1,localhost,::1"
    proxy_connect_target = _proxy_connect_target(proxy_url)
    if proxy_connect_target:
        env[EXTRACTOR_INSTALL_PROXY_CONNECT_TARGET_ENV] = proxy_connect_target
    return session["session_id"]


def _extractor_install_network_allowlist(extractor_id: str):
    from democrai.core.application.access_policy.operations import ResourceType
    from democrai.core.application.knowledge.extractor.runtime import get_extractor_access
    from democrai.core.infrastructure.sandbox.os.models import ApplicationNetworkAllowlist
    from democrai.core.infrastructure.sandbox.os.normalize import (
        dedupe_endpoints,
        endpoint_from_target,
    )

    endpoints = []
    for rule in get_extractor_access(extractor_id, "install"):
        resource = getattr(rule, "resource", None)
        if resource is None:
            continue
        resource_type = getattr(resource.resource_type, "value", resource.resource_type)
        if resource_type != ResourceType.NETWORK.value:
            continue
        target = str(
            getattr(resource, "normalized_target", None)
            or getattr(resource, "target", "")
            or ""
        ).strip()
        endpoint = endpoint_from_target(
            target,
            source=f"extractor:{extractor_id}",
            purpose="extractor_install_access",
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return ApplicationNetworkAllowlist(endpoints=dedupe_endpoints(endpoints))


async def _stop_os_network_proxy_for_install(session_id: str) -> None:
    if not session_id:
        return
    from democrai.core.infrastructure.sandbox.os.helper import (
        stop_application_network_proxy_session_with_helper,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    config = app_ctx().config

    def _stop() -> None:
        with process_guard_bypass_context():
            stop_application_network_proxy_session_with_helper(
                session_id,
                config=config,
            )

    await asyncio.to_thread(_stop)


async def _terminate_install_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        process.terminate()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(process.wait(), timeout=2.0)
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        process.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(process.wait(), timeout=2.0)


def _new_install_ready_file() -> str:
    fd, raw_path = tempfile.mkstemp(prefix="democrai_extractor_install_ready_", suffix=".flag")
    os.close(fd)
    with contextlib.suppress(OSError):
        os.unlink(raw_path)
    return raw_path


def _release_install_ready_file(path: str) -> None:
    if not path:
        return
    with open(path, "w", encoding="ascii") as handle:
        handle.write("ready\n")


def _cleanup_install_ready_file(path: str) -> None:
    if not path:
        return
    with contextlib.suppress(OSError):
        os.unlink(path)


async def _run_extractor_install_runtime_process(
    *,
    extractor_id: str,
    force: bool,
    node_id: str,
    event_id: str,
    source_node_id: str | None,
    install_config: dict[str, Any],
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ctx = app_ctx()
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        application_root()
        if not current_pythonpath
        else os.pathsep.join((application_root(), current_pythonpath))
    )
    _set_path_env(env, MODULES_PATH_ENV, ctx.runtime_module_paths)
    _set_path_env(env, ENGINES_PATH_ENV, ctx.runtime_engine_paths)
    _set_path_env(env, EXTRACTORS_PATH_ENV, ctx.runtime_extractor_paths)
    if request_context:
        env["DEMOCRAI_REQUEST_CONTEXT"] = json.dumps(request_context, sort_keys=True)
    ready_file = _new_install_ready_file()
    ready_released = False
    env[INSTALL_NETWORK_READY_FILE_ENV] = ready_file

    command = [
        sys.executable,
        "-m",
        "democrai.core.application.knowledge.extractor.install_runtime_process",
        "--extractor-id",
        extractor_id,
        "--node-id",
        node_id,
        "--event-id",
        event_id,
        "--install-config-json",
        json.dumps(install_config, sort_keys=True),
    ]
    if source_node_id:
        command.extend(["--source-node-id", source_node_id])
    if force:
        command.append("--force")

    proxy_session_id = await _start_os_network_proxy_for_install(
        env,
        extractor_id=extractor_id,
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
    except BaseException:
        with contextlib.suppress(Exception):
            await _stop_os_network_proxy_for_install(proxy_session_id)
        _cleanup_install_ready_file(ready_file)
        raise
    process_supervisor.register(process, name=f"extractor-install:{extractor_id}")
    try:
        await _apply_os_network_allowlist_to_install_process(
            process.pid,
            env=env,
            extractor_id=extractor_id,
        )
        _release_install_ready_file(ready_file)
        ready_released = True
        assert process.stdout is not None
        result: dict[str, Any] = {}
        error_message = ""
        last_line = ""
        output_tail: deque[str] = deque(maxlen=80)
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            if line.startswith(EXTRACTOR_INSTALL_PROCESS_RESULT_PREFIX):
                result_payload = line[len(EXTRACTOR_INSTALL_PROCESS_RESULT_PREFIX) :]
                result = json.loads(result_payload)
                if not isinstance(result, dict):
                    raise RuntimeError("extractor_install_process_result_dict_required")
                continue
            if line.startswith(EXTRACTOR_INSTALL_PROCESS_ERROR_PREFIX):
                error_payload = line[len(EXTRACTOR_INSTALL_PROCESS_ERROR_PREFIX) :]
                error_payload_data = json.loads(error_payload)
                if not isinstance(error_payload_data, dict):
                    raise RuntimeError("extractor_install_process_error_dict_required")
                error_message = str(error_payload_data.get("error") or "")
                continue
            output_tail.append(line)
            last_line = line
            emit_extractor_install_output(line, phase="install")
        return_code = await process.wait()
        if return_code != 0:
            raise RuntimeError(
                error_message
                or last_line
                or f"extractor install process failed:{return_code}"
            )
        return result
    finally:
        if ready_released:
            _release_install_ready_file(ready_file)
        _cleanup_install_ready_file(ready_file)
        await _terminate_install_process(process)
        process_supervisor.unregister(process)
        with contextlib.suppress(Exception):
            await _stop_os_network_proxy_for_install(proxy_session_id)


async def process_install_event(payload: dict[str, Any]) -> None:
    """Consume and execute one extractor-install request event."""
    with request_context_scope(dict(payload.get("request_context") or {})):
        extractor_id = str(payload.get("extractor_id") or "").strip().lower()
        if not extractor_id:
            return
        lock = _EXTRACTOR_INSTALL_LOCKS.get(extractor_id)
        if lock is None:
            lock = asyncio.Lock()
            _EXTRACTOR_INSTALL_LOCKS[extractor_id] = lock
        async with lock:
            await _process_install_event_locked(payload)


async def _process_install_event_locked(payload: dict[str, Any]) -> None:
    extractor_id = str(payload.get("extractor_id") or "").strip().lower()
    event_id = str(payload.get("event_id") or "").strip()
    manifest_version = str(payload.get("manifest_version") or "1")
    if not extractor_id or not event_id:
        return

    node_id = get_runtime_node_id()
    if _already_processed(
        extractor_id=extractor_id, node_id=node_id, event_id=event_id
    ):
        return

    extractor_cls = load_extractor_class(extractor_id)
    if extractor_cls is None:
        _update_extractor_registry_status(
            extractor_id=extractor_id,
            status="error",
            supported=False,
        )
        _upsert_node_status(
            extractor_id=extractor_id,
            node_id=node_id,
            status="error",
            event_id=event_id,
            manifest_version=manifest_version,
            last_error="extractor_class_not_found",
            completed=True,
        )
        return

    force_install = bool(payload.get("force"))
    if not force_install:
        ready_result = await asyncio.to_thread(
            check_extractor_ready_runtime,
            extractor_id=extractor_id,
            node_id=node_id,
        )
        if bool((ready_result or {}).get("ready")):
            _update_extractor_registry_status(
                extractor_id=extractor_id,
                status="installed",
                supported=True,
            )
            _upsert_node_status(
                extractor_id=extractor_id,
                node_id=node_id,
                status="installed",
                event_id=event_id,
                manifest_version=manifest_version,
                completed=True,
            )
            return

    _update_extractor_registry_status(
        extractor_id=extractor_id,
        status="installing",
        supported=True,
    )
    _upsert_node_status(
        extractor_id=extractor_id,
        node_id=node_id,
        status="installing",
        event_id=event_id,
        manifest_version=manifest_version,
        started=True,
    )

    try:
        with extractor_install_output_context(
            event_id=event_id,
            extractor_id=extractor_id,
            node_id=node_id,
            task_id=str(payload.get("task_id") or "").strip() or None,
        ):
            emit_extractor_install_output(
                "Starting extractor installation",
                phase="prepare",
            )
            await _run_extractor_install_runtime_process(
                extractor_id=extractor_id,
                force=force_install,
                node_id=node_id,
                event_id=event_id,
                source_node_id=str(payload.get("source_node_id") or "").strip() or None,
                install_config=dict(payload.get("install_config") or {}),
                request_context=dict(payload.get("request_context") or {}),
            )
            emit_extractor_install_output(
                "Extractor installation completed",
                phase="completed",
            )
        ready_result = await asyncio.to_thread(
            check_extractor_ready_runtime,
            extractor_id=extractor_id,
            node_id=node_id,
        )
        if not bool((ready_result or {}).get("ready")):
            raise RuntimeError(
                str((ready_result or {}).get("message") or "extractor_not_ready")
            )
        _update_extractor_registry_status(
            extractor_id=extractor_id,
            status="installed",
            supported=True,
        )
        _upsert_node_status(
            extractor_id=extractor_id,
            node_id=node_id,
            status="installed",
            event_id=event_id,
            manifest_version=manifest_version,
            completed=True,
        )
    except asyncio.CancelledError:
        _update_extractor_registry_status(
            extractor_id=extractor_id,
            status="error",
            supported=False,
        )
        _upsert_node_status(
            extractor_id=extractor_id,
            node_id=node_id,
            status="error",
            event_id=event_id,
            manifest_version=manifest_version,
            last_error="extractor_install_cancelled",
            completed=True,
        )
        raise
    except Exception as exc:
        _update_extractor_registry_status(
            extractor_id=extractor_id,
            status="error",
            supported=False,
        )
        _upsert_node_status(
            extractor_id=extractor_id,
            node_id=node_id,
            status="error",
            event_id=event_id,
            manifest_version=manifest_version,
            last_error=str(exc),
            completed=True,
        )


async def _consume_install_stream() -> None:
    ctx = app_ctx()
    logger = getattr(ctx, "logger", None)
    network = getattr(ctx, "network", None)
    if network is None:
        if logger is not None:
            logger.warning("[ExtractorInstall] consumer aborted: network unavailable")
        return
    queue = network.stream_manager.subscribe(EXTRACTOR_INSTALL_STREAM_ID)
    if logger is not None:
        logger.info(
            f"[ExtractorInstall] consumer listening stream={EXTRACTOR_INSTALL_STREAM_ID} "
            f"node={get_runtime_node_id()}"
        )
    try:
        while True:
            payload = await queue.get()
            if not isinstance(payload, dict):
                continue
            if (
                str(payload.get("event_name") or "").strip()
                != "extractor.install.requested"
            ):
                continue
            try:
                await process_install_event(payload)
            except Exception as exc:
                if logger is not None:
                    logger.error(
                        "[ExtractorInstall] install event failed "
                        f"extractor={payload.get('extractor_id')!r}: {exc!r}",
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
    except asyncio.CancelledError:
        pass
    finally:
        network.stream_manager.unsubscribe(EXTRACTOR_INSTALL_STREAM_ID, queue)


def start_extractor_install_consumer() -> None:
    """Start the long-lived consumer for extractor installation events."""
    ctx = app_ctx()
    logger = getattr(ctx, "logger", None)
    network = getattr(ctx, "network", None)
    if network is None or getattr(network, "_loop", None) is None:
        if logger is not None:
            logger.warning(
                "[ExtractorInstall] consumer NOT started: network/loop not ready "
                f"network={network is not None} loop={getattr(network, '_loop', None) is not None}"
            )
        return
    if getattr(ctx, "extractor_install_consumer", None) is not None:
        return
    future = asyncio.run_coroutine_threadsafe(_consume_install_stream(), network._loop)

    def _on_consumer_done(fut: Any) -> None:
        try:
            exc = fut.exception()
        except Exception:
            return
        if exc is not None and logger is not None:
            logger.error(
                f"[ExtractorInstall] consumer stopped with exception: {exc!r}",
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    future.add_done_callback(_on_consumer_done)
    ctx.extractor_install_consumer = future
    if logger is not None:
        logger.info("[ExtractorInstall] consumer started")


async def reconcile_installed_extractors() -> None:
    """Re-run installation processing for extractors already marked installed."""
    with SessionLocal() as session:
        rows = (
            session.query(ExtractorRegistry)
            .filter(ExtractorRegistry.status.in_(["installed", "active", "installing"]))
            .all()
        )
    node_id = get_runtime_node_id()
    for row in rows:
        extractor_id = row.extractor_id
        if not extractor_id:
            continue

        try:
            ready_result = await asyncio.to_thread(
                check_extractor_ready_runtime,
                extractor_id=extractor_id,
                node_id=node_id,
            )
        except Exception as exc:
            app_ctx().logger.error("{exc}", "extractor")
            continue
        if bool((ready_result or {}).get("ready")):
            previous_status = row.status
            next_status = (
                "installed" if previous_status == "installing" else previous_status
            )
            _update_extractor_registry_status(
                extractor_id=extractor_id,
                status=next_status,
                supported=True,
            )
            _upsert_node_status(
                extractor_id=extractor_id,
                node_id=node_id,
                status="installed",
                manifest_version=str(
                    get_extractor_manifest(extractor_id).get("manifest_version") or "1"
                ),
                completed=True,
            )
            continue
        payload = build_install_requested_event(
            extractor_id=extractor_id,
            install_config=dict(getattr(row, "install_config", None) or {}),
        )
        payload["source_node_id"] = get_runtime_node_id()
        await process_install_event(payload)


def start_extractor_install_reconcile() -> None:
    """Schedule one reconciliation pass for installed extractors."""
    ctx = app_ctx()
    network = getattr(ctx, "network", None)
    if network is None or getattr(network, "_loop", None) is None:
        return
    asyncio.run_coroutine_threadsafe(reconcile_installed_extractors(), network._loop)
