from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.application.ai.engine.manifests import load_engine_class
from democrai.core.application.ai.engine.runtime.access import (
    get_engine_access,
    get_engine_allowed_imports,
)
from democrai.core.application.ai.engine.runtime.environment import (
    get_engine_allowed_subprocess_commands,
    get_engine_install_env,
    get_engine_runtime_env,
)
from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.runtime.dependencies.engine_env import (
    engine_env_context,
    get_engine_venv_python_path,
)


def invoke_engine_method(
    subject: Any,
    method: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    if not method:
        raise RuntimeError("engine_runtime_method_required")
    if isinstance(subject, EngineWorkerSubject):
        return subject.invoke(method, payload)
    target = getattr(subject, method, None)
    if target is None:
        raise RuntimeError(f"engine_runtime_method_not_found:{method}")
    return target(**(payload or {}))


def run_engine_result(result: Any) -> Any:
    if asyncio.iscoroutine(result):
        return asyncio.run(result)
    if hasattr(result, "__aiter__"):

        async def _collect():
            items = []
            async for item in result:
                items.append(item)
            return items

        return asyncio.run(_collect())
    return result


def _engine_dict_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise RuntimeError("engine_runtime_result_dict_required")
    return result


def invoke_engine_class_method(
    *,
    engine_id: str,
    phase: str,
    method: str,
    payload: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> Any:
    engine_cls = load_engine_class(engine_id)
    if engine_cls is None:
        raise RuntimeError(f"engine_runtime_class_not_found:{engine_id}")
    install_phase = phase == "install"
    with process_guard_context(
        subject=engine_id,
        subject_kind="engine",
        access=get_engine_access(
            engine_id,
            phase,
            config=config,
        ),
        allowed_imports=get_engine_allowed_imports(engine_id, phase),
        allowed_subprocess_commands=get_engine_allowed_subprocess_commands(
            engine_id,
            phase,
        ),
        allow_subprocess=install_phase,
    ):
        phase_env = (
            get_engine_install_env(engine_id)
            if install_phase
            else get_engine_runtime_env(engine_id)
        )
        with engine_env_context(engine_id, env=phase_env):
            result = invoke_engine_method(engine_cls, method, payload)
            return run_engine_result(result)


def install_engine_runtime(
    *,
    engine_id: str,
    force: bool = False,
    node_id: str | None = None,
    event_id: str | None = None,
    source_node_id: str | None = None,
) -> dict[str, Any]:
    result = invoke_engine_class_method(
        engine_id=engine_id,
        phase="install",
        method="_install_local",
        payload={
            "force": force,
            "node_id": node_id,
            "event_id": event_id,
            "source_node_id": source_node_id,
        },
    )
    return _engine_dict_result(result)


def check_engine_ready_runtime(
    *,
    engine_id: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    venv_python = get_engine_venv_python_path(engine_id)
    if not venv_python.exists():
        return {
            "engine_id": engine_id,
            "node_id": node_id,
            "ready": False,
            "missing_shared": [],
            "missing_local": [],
            "message": "engine environment not provisioned",
        }
    subject = EngineWorkerSubject(
        engine_id=engine_id,
        config={},
        class_only=True,
    )
    try:
        result = invoke_engine_method(
            subject,
            "_check_ready_local",
            {"node_id": node_id},
        )
        return _engine_dict_result(result)
    finally:
        subject.close()


def check_engine_runtime_config(
    *,
    engine_id: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = invoke_engine_class_method(
        engine_id=engine_id,
        phase="runtime",
        method="_validate_config_local",
        payload={"config": config or {}},
        config=config or {},
    )
    return _engine_dict_result(result)


def check_engine_supported_runtime(
    *,
    engine_id: str,
    env: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = invoke_engine_class_method(
        engine_id=engine_id,
        phase="runtime",
        method="support_status",
        payload={"env": env or {}},
    )
    return _engine_dict_result(result)
