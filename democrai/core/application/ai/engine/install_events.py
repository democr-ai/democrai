from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import os
import subprocess
import sys
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    EngineNodeInstallRegistry,
    EngineRegistry,
    RuntimeNodeRegistry,
)
from democrai.core.application.ai.engine.registry_config import (
    apply_engine_registry_config_updates,
)
from democrai.core.application.ai.engine.runtime import (
    check_engine_ready_runtime,
)
from democrai.core.application.ai.engine.runtime.environment import application_root
from democrai.core.application.ai.engine.manifests import get_engine_manifest, load_engine_class
from democrai.core.application.ai.engine.runtime.methods import _engine_guard
from democrai.core.platform.utils.debug import debug_engine_install_flow
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.paths import (
    ENGINES_PATH_ENV,
    EXTRACTORS_PATH_ENV,
    MODULES_PATH_ENV,
)
from democrai.core.runtime.lifecycle.process_supervisor import process_supervisor
from democrai.core.runtime.foundation.app import (
    app_ctx,
    current_request_context_payload,
    request_context_scope,
)


ENGINE_INSTALL_STREAM_ID = "system.engine.install.events"
ENGINE_INSTALL_OUTPUT_EVENT_NAME = "engine.install.output"
ENGINE_INSTALL_STATUS_EVENT_NAME = "engine.install.status"
ENGINE_INSTALL_PROCESS_RESULT_PREFIX = "__DEMOCRAI_ENGINE_INSTALL_RESULT__="
ENGINE_INSTALL_PROCESS_ERROR_PREFIX = "__DEMOCRAI_ENGINE_INSTALL_ERROR__="
_INSTALL_OUTPUT_CONTEXT: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar("engine_install_output_context", default=None)
)
_ENGINE_INSTALL_LOCKS: dict[str, asyncio.Lock] = {}


def get_runtime_node_id() -> str:
    ctx = app_ctx()
    configured = ctx.node_id
    if configured:
        return configured
    cfg = ctx.config
    if cfg is not None:
        configured = cfg.get("network.node_id", "")
        if configured:
            ctx.node_id = configured
            return configured
    ctx.node_id = SERVER_NAME
    return SERVER_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _active_runtime_node_ids(session) -> list[str]:
    rows = (
        session.query(RuntimeNodeRegistry)
        .filter(RuntimeNodeRegistry.status == "active")
        .all()
    )
    node_ids = [row.node_id for row in rows if row.node_id]
    if node_ids:
        return sorted(set(node_ids))
    current = get_runtime_node_id()
    return [current] if current else []


def _engine_not_ready_message(
    engine_cls: Any,
    ready_result: dict[str, Any],
    *,
    install_context: bool = False,
) -> str:
    formatter = getattr(engine_cls, "_not_ready_message", None)
    if callable(formatter):
        return str(
            formatter(
                missing_shared=ready_result.get("missing_shared", []),
                missing_local=ready_result.get("missing_local", []),
                message=ready_result.get("message"),
                install_context=install_context,
            )
        )
    message = str(ready_result.get("message") or "").strip()
    if message:
        return message
    return "engine_not_ready"


def recompute_engine_install_status(
    engine_id: str,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    if not engine_id:
        return {
            "engine_id": "",
            "status": "",
            "supported": False,
            "nodes": [],
            "summary": {},
        }

    with SessionLocal() as session:
        target_nodes = _active_runtime_node_ids(session)
        install_rows = (
            session.query(EngineNodeInstallRegistry)
            .filter(EngineNodeInstallRegistry.engine_id == engine_id)
            .all()
        )
        rows_by_node = {
            row.node_id: row
            for row in install_rows
            if row.node_id
        }
        has_install_rows = rows_by_node
        nodes: list[dict[str, str]] = []
        summary = {"pending": 0, "installing": 0, "installed": 0, "error": 0}
        for node_id in target_nodes:
            row = rows_by_node.get(node_id)
            status = row.status if row is not None else "pending"
            if status not in summary:
                status = "pending"
            summary[status] += 1
            nodes.append(
                {
                    "node_id": node_id,
                    "status": status,
                    "last_event_id": row.last_event_id if row is not None else "",
                    "last_error": row.last_error if row is not None else "",
                }
            )

        if summary["error"] > 0:
            next_status = "error"
            supported = False
        elif not target_nodes or summary["installed"] == len(target_nodes):
            next_status = "installed"
            supported = True
        elif not has_install_rows and summary["pending"] == len(target_nodes):
            next_status = "uninstalled"
            supported = True
        else:
            next_status = "installing"
            supported = True

        if persist:
            rows = (
                session.query(EngineRegistry)
                .filter(EngineRegistry.provider == engine_id)
                .all()
            )
            for row in rows:
                current_status = row.status
                row.status = (
                    "active"
                    if next_status == "installed" and current_status == "active"
                    else next_status
                )
                row.supported = supported
            session.commit()

    return {
        "engine_id": engine_id,
        "status": next_status,
        "supported": supported,
        "nodes": nodes,
        "summary": summary,
    }


def _broadcast_install_status(payload: dict[str, Any]) -> None:
    ctx = app_ctx()
    network = ctx.network
    if network is None or network._loop is None or network.stream_manager is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(
            network.stream_manager.broadcast(ENGINE_INSTALL_STREAM_ID, payload),
            network._loop,
        )
    except Exception:
        if ctx.logger is not None:
            ctx.logger.debug("[EngineInstall] status broadcast skipped", exc_info=True)


@contextlib.contextmanager
def engine_install_output_context(
    *,
    event_id: str,
    engine_id: str,
    node_id: str,
    task_id: str | None = None,
):
    token = _INSTALL_OUTPUT_CONTEXT.set(
        {
            "event_id": event_id,
            "engine_id": engine_id,
            "node_id": node_id,
            "task_id": task_id or "",
        }
    )
    try:
        yield
    finally:
        _INSTALL_OUTPUT_CONTEXT.reset(token)


def emit_engine_install_output(
    line: str,
    *,
    phase: str = "install",
    stream: str = "stdout",
    level: str = "info",
) -> None:
    context = _INSTALL_OUTPUT_CONTEXT.get()
    if not context or not line:
        return
    ctx = app_ctx()
    network = ctx.network
    if network is None or network._loop is None or network.stream_manager is None:
        return
    task_id = context.get("task_id", "")
    payload = {
        "event_name": ENGINE_INSTALL_OUTPUT_EVENT_NAME,
        "event_id": context["event_id"],
        "engine_id": context["engine_id"],
        "node_id": context["node_id"],
        "task_id": task_id,
        "phase": phase or "install",
        "stream": stream or "stdout",
        "level": level or "info",
        "line": line,
        "timestamp": _utc_now_iso(),
    }
    try:
        asyncio.run_coroutine_threadsafe(
            network.stream_manager.broadcast(ENGINE_INSTALL_STREAM_ID, payload),
            network._loop,
        )
        if task_id:
            if ctx.task_manager is not None:
                label = f"{payload['phase']}: {line}" if payload["phase"] else line
                asyncio.run_coroutine_threadsafe(
                    ctx.task_manager.emit_progress(task_id, 0.6, label=label),
                    network._loop,
                )
    except Exception:
        if ctx.logger is not None:
            ctx.logger.debug("[EngineInstall] output broadcast skipped", exc_info=True)


def build_install_requested_event(
    *,
    engine_id: str,
    force: bool = False,
    requested_by: dict[str, Any] | None = None,
    task_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    manifest = get_engine_manifest(engine_id) or {}
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_name": "engine.install.requested",
        "engine_id": engine_id,
        "manifest_version": manifest.get("manifest_version") or "1",
        "engine_version": manifest.get("version", ""),
        "force": force,
        "task_id": task_id or "",
        "source_node_id": get_runtime_node_id(),
        "request_context": current_request_context_payload(
            "engine_install_event.build_requested"
        ),
        "requested_by": requested_by or {},
        "requested_at": _utc_now_iso(),
    }


def _active_node_install_event_id(*, engine_id: str, node_id: str) -> str:
    with SessionLocal() as session:
        row = (
            session.query(EngineNodeInstallRegistry)
            .filter(
                EngineNodeInstallRegistry.engine_id == engine_id,
                EngineNodeInstallRegistry.node_id == node_id,
            )
            .first()
        )
        if row is None:
            return ""
        event_id = str(row.last_event_id or "").strip()
        if str(row.status or "").strip().lower() == "installing" and event_id:
            return event_id
        return ""


async def publish_engine_install_requested(
    *,
    engine_id: str,
    force: bool = False,
    requested_by: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    source_node_id = get_runtime_node_id()
    active_event_id = ""
    if not force:
        active_event_id = _active_node_install_event_id(
            engine_id=engine_id,
            node_id=source_node_id,
        )
    event = build_install_requested_event(
        engine_id=engine_id,
        force=force,
        requested_by=requested_by,
        task_id=task_id,
        event_id=active_event_id or None,
    )
    provider_definition = get_engine_manifest(event["engine_id"]) or {}
    provider_payload = (
        dict(provider_definition.get("provider"))
        if isinstance(provider_definition.get("provider"), dict)
        else {}
    )
    provider_configurable = provider_payload.get("configurable", False)
    ctx = app_ctx()
    network = ctx.network
    if network is None:
        raise RuntimeError("network_unavailable")
    logger = ctx.logger

    with SessionLocal() as session:
        rows = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.provider == event["engine_id"])
            .all()
        )
        if not rows:
            if not provider_configurable:
                row = EngineRegistry(
                    name=event["engine_id"],
                    provider=event["engine_id"],
                    config={},
                    status="installing",
                    supported=True,
                )
                session.add(row)
        else:
            for row in rows:
                row.status = "installing"
                row.supported = True
        session.commit()
    _upsert_node_status(
        engine_id=event["engine_id"],
        node_id=event["source_node_id"] or get_runtime_node_id(),
        status="installing",
        event_id=event["event_id"],
        manifest_version=event.get("manifest_version") or "1",
    )

    if logger is not None:
        logger.info(
            "[EngineInstall] published install request "
            f"engine={event['engine_id']} event_id={event['event_id']} source_node={event['source_node_id']}"
        )
    await network.stream_manager.broadcast(ENGINE_INSTALL_STREAM_ID, event)
    return event


async def begin_engine_install(
    *,
    engine_registry_id: int,
    force: bool = False,
    requested_by: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    with SessionLocal() as session:
        row = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.id == engine_registry_id)
            .first()
        )
        if row is None:
            raise RuntimeError(f"engine_registry_row_not_found:{engine_registry_id}")
        provider = row.provider
    if not provider:
        raise RuntimeError(f"engine_registry_provider_missing:{engine_registry_id}")
    event = await publish_engine_install_requested(
        engine_id=provider,
        force=force,
        requested_by=requested_by,
        task_id=task_id,
    )
    status = recompute_engine_install_status(provider)
    return {
        "engine_registry_id": engine_registry_id,
        "provider": provider,
        "event": event,
        "status": status,
    }


def engine_install_status(*, engine_registry_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        row = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.id == engine_registry_id)
            .first()
        )
        if row is None:
            raise RuntimeError(f"engine_registry_row_not_found:{engine_registry_id}")
        provider = row.provider
    if not provider:
        raise RuntimeError(f"engine_registry_provider_missing:{engine_registry_id}")
    status = recompute_engine_install_status(provider, persist=False)
    status["engine_registry_id"] = engine_registry_id
    return status


def _upsert_node_status(
    *,
    engine_id: str,
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
            session.query(EngineNodeInstallRegistry)
            .filter(
                EngineNodeInstallRegistry.engine_id == engine_id,
                EngineNodeInstallRegistry.node_id == node_id,
            )
            .first()
        )
        if row is None:
            row = EngineNodeInstallRegistry(
                engine_id=engine_id,
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
    aggregate = recompute_engine_install_status(engine_id)
    _broadcast_install_status(
        {
            "event_name": ENGINE_INSTALL_STATUS_EVENT_NAME,
            "engine_id": engine_id,
            "node_id": node_id,
            "event_id": event_id or "",
            "status": status,
            "last_error": last_error or "",
            "manifest_version": manifest_version or "",
            "timestamp": _utc_now_iso(),
            "aggregate": aggregate,
        }
    )


def _already_processed(*, engine_id: str, node_id: str, event_id: str) -> bool:
    with SessionLocal() as session:
        row = (
            session.query(EngineNodeInstallRegistry)
            .filter(
                EngineNodeInstallRegistry.engine_id == engine_id,
                EngineNodeInstallRegistry.node_id == node_id,
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


async def _apply_os_network_allowlist_to_install_process(pid: int | None) -> None:
    if pid is None:
        return
    from democrai.core.infrastructure.sandbox.os.helper import (
        apply_application_network_allowlist_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.state import (
        is_application_network_allowlist_enabled,
        refresh_application_network_allowlist,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    ctx = app_ctx()
    config = ctx.config
    if not is_application_network_allowlist_enabled(config):
        return
    allowlist = refresh_application_network_allowlist()

    def _apply() -> None:
        with process_guard_bypass_context():
            apply_application_network_allowlist_with_helper(
                allowlist,
                pid=pid,
                config=config,
            )

    await asyncio.to_thread(_apply)


async def _start_os_network_proxy_for_install(env: dict[str, str]) -> str:
    from democrai.core.infrastructure.sandbox.os.helper import (
        start_application_network_proxy_session_with_helper,
    )
    from democrai.core.infrastructure.sandbox.os.state import (
        is_application_network_allowlist_enabled,
        refresh_application_network_allowlist,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    ctx = app_ctx()
    config = ctx.config
    if not is_application_network_allowlist_enabled(config):
        return ""
    allowlist = refresh_application_network_allowlist()

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
    return session["session_id"]


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


async def _run_engine_install_runtime_process(
    *,
    engine_id: str,
    force: bool,
    node_id: str,
    event_id: str,
    source_node_id: str | None,
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

    command = [
        sys.executable,
        "-m",
        "democrai.core.application.ai.engine.install_runtime_process",
        "--engine-id",
        engine_id,
        "--node-id",
        node_id,
        "--event-id",
        event_id,
    ]
    if source_node_id:
        command.extend(["--source-node-id", source_node_id])
    if force:
        command.append("--force")

    proxy_session_id = await _start_os_network_proxy_for_install(env)
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
        raise
    process_supervisor.register(process, name=f"engine-install:{engine_id}")
    try:
        await _apply_os_network_allowlist_to_install_process(process.pid)
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
            if line.startswith(ENGINE_INSTALL_PROCESS_RESULT_PREFIX):
                result_payload = line[len(ENGINE_INSTALL_PROCESS_RESULT_PREFIX) :]
                result = json.loads(result_payload)
                if not isinstance(result, dict):
                    raise RuntimeError("engine_install_process_result_dict_required")
                continue
            if line.startswith(ENGINE_INSTALL_PROCESS_ERROR_PREFIX):
                error_payload = line[len(ENGINE_INSTALL_PROCESS_ERROR_PREFIX) :]
                error_payload_data = json.loads(error_payload)
                if not isinstance(error_payload_data, dict):
                    raise RuntimeError("engine_install_process_error_dict_required")
                error_message = error_payload_data.get("error", "")
                continue
            last_line = line
            output_tail.append(line)
            emit_engine_install_output(line, phase="install")
        return_code = await process.wait()
        if return_code != 0:
            logger = app_ctx().logger
            if logger is not None:
                logger.error(
                    "[EngineInstall] install process failed "
                    f"engine={engine_id} node={node_id} event_id={event_id} "
                    f"return_code={return_code} error={error_message or last_line} "
                    f"output_tail={list(output_tail)}"
                )
            raise RuntimeError(
                error_message or last_line or f"engine install process failed:{return_code}"
            )
        return result
    finally:
        await _terminate_install_process(process)
        process_supervisor.unregister(process)
        with contextlib.suppress(Exception):
            await _stop_os_network_proxy_for_install(proxy_session_id)


async def process_install_event(payload: dict[str, Any]) -> None:
    with request_context_scope(payload.get("request_context") or {}):
        engine_id = payload.get("engine_id", "")
        if not engine_id:
            return
        lock = _ENGINE_INSTALL_LOCKS.get(engine_id)
        if lock is None:
            lock = asyncio.Lock()
            _ENGINE_INSTALL_LOCKS[engine_id] = lock
        async with lock:
            await _process_install_event_locked(payload)


async def _process_install_event_locked(payload: dict[str, Any]) -> None:
    engine_id = payload.get("engine_id", "")
    event_id = payload.get("event_id", "")
    manifest_version = payload.get("manifest_version") or "1"
    if not engine_id or not event_id:
        return

    node_id = get_runtime_node_id()
    force_install = payload.get("force", False)
    logger = app_ctx().logger
    if logger is not None:
        logger.info(
            f"[EngineInstall] process event start engine={engine_id} node={node_id} event_id={event_id}"
        )
    debug_engine_install_flow(
        "process_event.start",
        engine_id=engine_id,
        node_id=node_id,
        event_id=event_id,
        force_install=force_install,
        manifest_version=manifest_version,
    )
    already_processed = _already_processed(
        engine_id=engine_id,
        node_id=node_id,
        event_id=event_id,
    )
    debug_engine_install_flow(
        "process_event.already_processed_result",
        engine_id=engine_id,
        node_id=node_id,
        event_id=event_id,
        already_processed=already_processed,
    )
    if already_processed:
        if logger is not None:
            logger.info(
                f"[EngineInstall] skipping already processed event engine={engine_id} node={node_id} event_id={event_id}"
            )
        return

    debug_engine_install_flow(
        "process_event.load_engine_class.begin",
        engine_id=engine_id,
        node_id=node_id,
        event_id=event_id,
    )
    with _engine_guard(engine_id=engine_id, phase="install", config={}):
        engine_cls = load_engine_class(engine_id)
    debug_engine_install_flow(
        "process_event.load_engine_class.end",
        engine_id=engine_id,
        node_id=node_id,
        event_id=event_id,
        engine_class_found=engine_cls is not None,
        engine_class_name=engine_cls.__name__ if engine_cls is not None else "",
    )
    if engine_cls is None:
        _upsert_node_status(
            engine_id=engine_id,
            node_id=node_id,
            status="error",
            event_id=event_id,
            manifest_version=manifest_version,
            last_error="engine_class_not_found",
            completed=True,
        )
        return

    if not force_install:
        if logger is not None:
            logger.debug(
                "[EngineInstall] check ready before install begin "
                f"engine={engine_id} node={node_id} event_id={event_id}"
            )
        debug_engine_install_flow(
            "process_event.check_ready.before_install.begin",
            engine_id=engine_id,
            node_id=node_id,
            event_id=event_id,
        )
        try:
            ready_result = await asyncio.to_thread(
                check_engine_ready_runtime,
                engine_id=engine_id,
                node_id=node_id,
            )
        except Exception as exc:
            if logger is not None:
                logger.error(
                    "[EngineInstall] check ready before install failed "
                    f"engine={engine_id} node={node_id} event_id={event_id} error={exc}"
                )
            raise
        if logger is not None:
            logger.debug(
                "[EngineInstall] check ready before install end "
                f"engine={engine_id} node={node_id} event_id={event_id} "
                f"ready={ready_result.get('ready')} "
                f"missing_local={ready_result.get('missing_local', [])} "
                f"message={ready_result.get('message', '')}"
            )
        debug_engine_install_flow(
            "process_event.check_ready.before_install.end",
            engine_id=engine_id,
            node_id=node_id,
            event_id=event_id,
            ready=ready_result.get("ready"),
            message=ready_result.get("message", ""),
            missing_shared=ready_result.get("missing_shared", []),
            missing_local=ready_result.get("missing_local", []),
        )
        if ready_result.get("ready"):
            _upsert_node_status(
                engine_id=engine_id,
                node_id=node_id,
                status="installed",
                event_id=event_id,
                manifest_version=manifest_version,
                completed=True,
            )
            if logger is not None:
                logger.info(
                    "[EngineInstall] skip install: already ready "
                    f"engine={engine_id} node={node_id} event_id={event_id}"
                )
            return

    _upsert_node_status(
        engine_id=engine_id,
        node_id=node_id,
        status="installing",
        event_id=event_id,
        manifest_version=manifest_version,
        started=True,
    )
    if logger is not None:
        logger.info(
            f"[EngineInstall] node install begin engine={engine_id} node={node_id} event_id={event_id}"
        )

    try:
        debug_engine_install_flow(
            "process_event.install_runtime.begin",
            engine_id=engine_id,
            node_id=node_id,
            event_id=event_id,
            source_node_id=payload.get("source_node_id") or None,
            force_install=force_install,
        )
        with engine_install_output_context(
            event_id=event_id,
            engine_id=engine_id,
            node_id=node_id,
            task_id=payload.get("task_id") or None,
        ):
            emit_engine_install_output("Starting engine installation", phase="prepare")
            install_result = await _run_engine_install_runtime_process(
                engine_id=engine_id,
                force=force_install,
                node_id=node_id,
                event_id=event_id,
                source_node_id=payload.get("source_node_id") or None,
                request_context=payload.get("request_context") or {},
            )
            apply_engine_registry_config_updates(
                engine_id=engine_id,
                updates=install_result.get("config_updates") or {},
            )
            emit_engine_install_output("Engine installation completed", phase="completed")
        debug_engine_install_flow(
            "process_event.install_runtime.end",
            engine_id=engine_id,
            node_id=node_id,
            event_id=event_id,
        )
        debug_engine_install_flow(
            "process_event.check_ready.after_install.begin",
            engine_id=engine_id,
            node_id=node_id,
            event_id=event_id,
        )
        ready_result = await asyncio.to_thread(
            check_engine_ready_runtime,
            engine_id=engine_id,
            node_id=node_id,
        )
        debug_engine_install_flow(
            "process_event.check_ready.after_install.end",
            engine_id=engine_id,
            node_id=node_id,
            event_id=event_id,
            ready=ready_result.get("ready"),
            message=ready_result.get("message", ""),
            missing_shared=ready_result.get("missing_shared", []),
            missing_local=ready_result.get("missing_local", []),
        )
        if not ready_result.get("ready"):
            raise RuntimeError(
                _engine_not_ready_message(
                    engine_cls,
                    ready_result,
                    install_context=True,
                )
            )
        _upsert_node_status(
            engine_id=engine_id,
            node_id=node_id,
            status="installed",
            event_id=event_id,
            manifest_version=manifest_version,
            completed=True,
        )
        if logger is not None:
            logger.info(
                f"[EngineInstall] node install completed engine={engine_id} node={node_id} event_id={event_id}"
            )
    except asyncio.CancelledError:
        if logger is not None:
            logger.info(
                "[EngineInstall] node install cancelled "
                f"engine={engine_id} node={node_id} event_id={event_id}"
            )
        _upsert_node_status(
            engine_id=engine_id,
            node_id=node_id,
            status="error",
            event_id=event_id,
            manifest_version=manifest_version,
            last_error="engine_install_cancelled",
            completed=True,
        )
        raise
    except Exception as exc:
        if logger is not None:
            logger.error(
                f"[EngineInstall] node install failed engine={engine_id} node={node_id} error={exc}"
            )
        _upsert_node_status(
            engine_id=engine_id,
            node_id=node_id,
            status="error",
            event_id=event_id,
            manifest_version=manifest_version,
            last_error=str(exc),
            completed=True,
        )


async def _consume_install_stream() -> None:
    ctx = app_ctx()
    network = ctx.network
    if network is None:
        return
    logger = ctx.logger
    if logger is not None:
        logger.info(
            f"[EngineInstall] consumer subscribed stream={ENGINE_INSTALL_STREAM_ID} node={get_runtime_node_id()}"
        )
    queue = network.stream_manager.subscribe(ENGINE_INSTALL_STREAM_ID)
    try:
        while True:
            payload = await queue.get()
            if not isinstance(payload, dict):
                continue
            if payload.get("event_name") != "engine.install.requested":
                continue
            if logger is not None:
                logger.debug(
                    "[EngineInstall] consumer received install event "
                    f"engine={payload.get('engine_id', '')} "
                    f"node={get_runtime_node_id()} "
                    f"event_id={payload.get('event_id', '')}"
                )
            await process_install_event(payload)
    except asyncio.CancelledError:
        pass
    finally:
        network.stream_manager.unsubscribe(ENGINE_INSTALL_STREAM_ID, queue)


def start_engine_install_consumer() -> None:
    ctx = app_ctx()
    logger = ctx.logger
    network = ctx.network
    if network is None or network._loop is None:
        if logger is not None:
            logger.warning("[EngineInstall] consumer not started: network loop unavailable")
        return
    if ctx.engine_install_consumer is not None:
        if logger is not None:
            logger.info("[EngineInstall] consumer already running")
        return
    future = asyncio.run_coroutine_threadsafe(_consume_install_stream(), network._loop)
    ctx.engine_install_consumer = future
    if logger is not None:
        logger.info("[EngineInstall] consumer start scheduled")


async def reconcile_installed_engines() -> None:
    logger = app_ctx().logger
    with SessionLocal() as session:
        rows = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.status.in_(["installed", "active", "installing"]))
            .all()
        )
    if logger is not None:
        logger.debug(f"[EngineInstall] reconcile candidates count={len(rows)}")
    for row in rows:
        engine_id = row.provider
        if not engine_id:
            continue
        node_id = get_runtime_node_id()
        if logger is not None:
            logger.debug(
                "[EngineInstall] reconcile check ready begin "
                f"engine={engine_id} node={node_id} registry_status={row.status}"
            )
        try:
            ready_result = await asyncio.to_thread(
                check_engine_ready_runtime,
                engine_id=engine_id,
                node_id=node_id,
            )
        except Exception as exc:
            if logger is not None:
                logger.error(
                    "[EngineInstall] reconcile check ready failed "
                    f"engine={engine_id} node={node_id} error={exc}"
                )
            continue
        if logger is not None:
            logger.debug(
                "[EngineInstall] reconcile check ready end "
                f"engine={engine_id} node={node_id} ready={ready_result.get('ready')} "
                f"missing_local={ready_result.get('missing_local', [])} "
                f"message={ready_result.get('message', '')}"
            )
        if ready_result.get("ready"):
            manifest = get_engine_manifest(engine_id) or {}
            _upsert_node_status(
                engine_id=engine_id,
                node_id=node_id,
                status="installed",
                manifest_version=manifest.get("manifest_version") or "1",
                completed=True,
            )
            continue
        payload = build_install_requested_event(engine_id=engine_id)
        payload["source_node_id"] = node_id
        if logger is not None:
            logger.debug(
                "[EngineInstall] reconcile dispatch install event "
                f"engine={engine_id} node={node_id} event_id={payload.get('event_id')}"
            )
        await process_install_event(payload)


def start_engine_install_reconcile() -> None:
    ctx = app_ctx()
    logger = ctx.logger
    network = ctx.network
    if network is None or network._loop is None:
        if logger is not None:
            logger.warning("[EngineInstall] reconcile not started: network loop unavailable")
        return
    asyncio.run_coroutine_threadsafe(reconcile_installed_engines(), network._loop)
    if logger is not None:
        logger.info("[EngineInstall] reconcile scheduled")
