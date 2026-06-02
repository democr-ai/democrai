from __future__ import annotations

import asyncio
import importlib
import sys
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.modules.access_constants import (
    module_runtime_create_paths,
    module_runtime_modify_paths,
    module_runtime_read_paths,
)
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.sdk.ui import Builder
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import (
    RequestContext,
    app_ctx,
    req_ctx,
    reset_req_ctx,
    set_req_ctx,
)
from democrai.core.runtime.observability.profiling import current_request_profiler


def _profile_span(name: str):
    profiler = current_request_profiler()
    if profiler is None:
        return nullcontext()
    return profiler.span(name)


class _SerializedComponent:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    @property
    def id(self) -> str:
        return self.payload["id"]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def _session_identity(
    session: dict[str, Any],
) -> tuple[int | None, int | None, str | None, str | None, int | None]:
    user = dict(session.get("user") or {})
    user_id = to_optional_int(user.get("id"))
    organization_id = to_optional_int(user.get("organization_id"))
    role = user.get("role")
    access_level = to_optional_int(user.get("access_level"))
    session_key = session.get("session_key")
    return (
        user_id,
        organization_id,
        session_key or None,
        role or None,
        access_level,
    )


def build_module_reuse_key(
    module_name: str, session: dict[str, Any] | None = None
) -> str:
    resolved_session = {} if session is None else dict(session)
    user_id, organization_id, session_key, _role, _access_level = _session_identity(
        resolved_session
    )
    user_part = str(user_id) if user_id is not None else "anon"
    org_part = str(organization_id) if organization_id is not None else "none"
    session_part = session_key or "no-session"
    return f"module:{module_name}:u:{user_part}:o:{org_part}:s:{session_part}"


def _install_module_import_paths(module_path: str, *, is_builtin: bool) -> None:
    deps_path = str(Path(module_path).resolve() / "deps")
    if Path(deps_path).exists() and deps_path not in sys.path:
        sys.path.insert(0, deps_path)
    if is_builtin:
        modules_parent = str(Path(module_path).resolve().parent.parent)
        if modules_parent not in sys.path:
            sys.path.insert(0, modules_parent)
        return
    parent_path = str(Path(module_path).resolve().parent)
    if parent_path not in sys.path:
        sys.path.insert(0, parent_path)


def _module_allowed_imports(module: Any) -> list[str]:
    cached = getattr(module, "_runtime_allowed_imports", None)
    if isinstance(cached, list):
        return cached
    deduped: list[str] = []
    seen: set[str] = set()
    for item in module.allowed_imports:
        normalized = item.strip().split(".", 1)[0]
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    setattr(module, "_runtime_allowed_imports", deduped)
    return deduped


def _module_access(module: Any) -> tuple[AccessManifestRule, ...]:
    cached = getattr(module, "_runtime_access_rules", None)
    if isinstance(cached, tuple):
        return cached
    subject_name = module.name.strip()
    rules = list(module.access)
    if not subject_name:
        resolved = tuple(rules)
        setattr(module, "_runtime_access_rules", resolved)
        return resolved
    subject = AccessSubject.create("module", subject_name)
    for operation, paths in (
        ("read", module_runtime_read_paths()),
        ("create", module_runtime_create_paths()),
        ("modify", module_runtime_modify_paths()),
    ):
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation=operation,
                    target=path,
                ),
            )
            for path in paths
        )
    resolved = tuple(rules)
    setattr(module, "_runtime_access_rules", resolved)
    return resolved


class _ModuleRuntimeSubject:
    def __init__(self, *, module_name: str, module_path: str, is_builtin: bool) -> None:
        self.module_name = module_name
        self.module_path = module_path
        self.is_builtin = is_builtin
        _install_module_import_paths(self.module_path, is_builtin=self.is_builtin)

    def _sdk(
        self, *, current_path: str = "", session: dict[str, Any] | None = None
    ) -> Any:
        from democrai.sdk.client import SDK as ModuleSDK

        return ModuleSDK(
            module_path=self.module_path,
            module_name=self.module_name,
            current_path=current_path,
            session={} if session is None else dict(session),
        )

    @contextmanager
    def _runtime_context(
        self,
        *,
        action_name: str | None = None,
        session: dict[str, Any] | None = None,
        current_path: str = "",
    ) -> Iterator[Any]:
        from democrai.sdk.client import current_sdk as _current_module_sdk

        resolved_session = {} if session is None else dict(session)
        with _profile_span("module_subject.sdk_init"):
            sdk = self._sdk(current_path=current_path, session=resolved_session)
        try:
            req_ctx()
            has_request_context = True
        except LookupError:
            has_request_context = False
        sdk_token = _current_module_sdk.set(sdk)
        if has_request_context:
            try:
                yield sdk
            finally:
                _current_module_sdk.reset(sdk_token)
            return

        user_id, organization_id, session_key, role, access_level = _session_identity(
            resolved_session
        )
        req_token = set_req_ctx(
            RequestContext(
                request_id=f"runtime:{self.module_name}",
                user=user_id,
                role=role,
                organization_id=organization_id,
                access_level=access_level,
                channel="ipc",
                app=app_ctx(),
                session_key=session_key,
                client_ip=None,
                action_name=action_name,
                module_name=self.module_name,
                stream_id=str(resolved_session.get("stream_id") or "").strip() or None,
            )
        )
        try:
            yield sdk
        finally:
            reset_req_ctx(req_token)
            _current_module_sdk.reset(sdk_token)

    async def _invoke_handler(
        self,
        *,
        handler_module: str,
        handler_name: str,
        call_args: list[Any],
        call_kwargs: dict[str, Any],
    ) -> Any:
        handler = getattr(importlib.import_module(handler_module), handler_name)
        result = handler(*call_args, **call_kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    @staticmethod
    def _snapshot_builder(builder: Builder) -> dict[str, Any]:
        return builder.snapshot()

    async def invoke(
        self, *, operation: str, payload: dict[str, Any] | None = None
    ) -> Any:
        op = operation
        if payload is None:
            raise RuntimeError("module_runtime_payload_required")
        call = payload

        if op == "action":
            session = dict(call["session"])
            with self._runtime_context(
                action_name=call["action_name"],
                session=session,
                current_path=session["current_path"],
            ) as sdk:
                result = await self._invoke_handler(
                    handler_module=call["handler_module"],
                    handler_name=call["handler_name"],
                    call_args=[dict(call["ctx"]), session, sdk],
                    call_kwargs={},
                )
                return {
                    "result": result,
                    "session": session,
                }

        if op == "render":
            session = dict(call["session"])
            current_path = call["current_path"]
            page_module = call["page_module"]
            with self._runtime_context(session=session, current_path=current_path):
                with _profile_span("module_subject.import_page"):
                    module = importlib.import_module(page_module)
                render = getattr(module, "render", None)
                if render is None:
                    raise RuntimeError(f"module_render_not_found:{page_module}")
                with _profile_span("module_subject.render_call"):
                    params = call.get("params")
                    builder = render({} if params is None else dict(params), session)
                    if asyncio.iscoroutine(builder):
                        builder = await builder
                if not isinstance(builder, Builder):
                    raise RuntimeError(f"module_render_invalid_builder:{page_module}")
                if hasattr(render, "_template_name"):
                    builder.set_template(render._template_name)
                with _profile_span("module_subject.snapshot_builder"):
                    return self._snapshot_builder(builder)

        if op == "command":
            kwargs = dict(call["call_kwargs"])
            if bool(call.get("include_stop_event")) and "stop_event" not in kwargs:
                kwargs["stop_event"] = asyncio.Event()
            with self._runtime_context(
                action_name=call["command_name"],
                session=dict(call["session"]),
            ):
                return await self._invoke_handler(
                    handler_module=call["handler_module"],
                    handler_name=call["handler_name"],
                    call_args=list(call["call_args"]),
                    call_kwargs=kwargs,
                )

        raise RuntimeError(f"module_runtime_unknown_operation:{op}")


def restore_builder_snapshot(payload: dict[str, Any]) -> Builder:
    builder = Builder()
    builder.merge(
        payload,
        components=True,
        metadata=True,
        replace=True,
        component_factory=lambda item: _SerializedComponent(dict(item)),
    )
    return builder


@dataclass
class _ModuleHandle:
    subject: _ModuleRuntimeSubject
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    locks_guard: threading.Lock = field(default_factory=threading.Lock)

    def lock_for(self, key: str) -> asyncio.Lock:
        if not key:
            return self.lock
        with self.locks_guard:
            existing = self.locks.get(key)
            if existing is not None:
                return existing
            created = asyncio.Lock()
            self.locks[key] = created
            return created


class ModuleRuntime:
    def __init__(self) -> None:
        self._handles: dict[str, _ModuleHandle] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _build_subject(module: Any) -> _ModuleRuntimeSubject:
        return _ModuleRuntimeSubject(
            module_name=module.name,
            module_path=module.path,
            is_builtin=bool(module.is_builtin),
        )

    def _ensure_handle(self, *, module: Any, reuse_key: str) -> _ModuleHandle:
        with self._lock:
            handle = self._handles.get(reuse_key)
            if handle is not None:
                return handle
        created = _ModuleHandle(subject=self._build_subject(module))
        with self._lock:
            self._handles[reuse_key] = created
            return created

    @staticmethod
    async def _invoke_subject(
        *,
        subject: _ModuleRuntimeSubject,
        module: Any,
        operation: str,
        payload: dict[str, Any],
        session: dict[str, Any] | None = None,
    ) -> Any:
        try:
            current_request = req_ctx()
        except LookupError:
            current_request = None
        if current_request is not None:
            user_id = current_request.user
            organization_id = current_request.organization_id
            session_key = (
                str(getattr(current_request, "session_key", "") or "").strip()
                or None
            )
        else:
            resolved_session = {} if session is None else dict(session)
            user_id, organization_id, session_key, _role, _access_level = _session_identity(
                resolved_session
            )
        with _profile_span("module_runtime.access_rules"):
            access_rules = _module_access(module)
            allowed_imports = _module_allowed_imports(module)
        with _profile_span("module_runtime.process_guard"):
            with process_guard_context(
                subject=module.name,
                subject_kind="module",
                access=access_rules,
                allowed_imports=allowed_imports,
                user_id=user_id,
                organization_id=organization_id,
                session_key=session_key,
            ):
                with _profile_span("module_runtime.process_guard.body"):
                    with _profile_span("module_runtime.subject.invoke"):
                        return await subject.invoke(operation=operation, payload=payload)

    async def invoke(
        self,
        *,
        module: Any,
        operation: str,
        payload: dict[str, Any],
        session: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        persistent: bool = True,
        reuse_key: str | None = None,
        lock_key: str | None = None,
    ) -> Any:
        resolved_reuse_key = reuse_key or f"module:{module.name}"
        if session is not None and not reuse_key:
            resolved_reuse_key = build_module_reuse_key(module.name, session=session)
        if persistent:
            handle = self._ensure_handle(module=module, reuse_key=resolved_reuse_key)
            resolved_lock_key = lock_key or resolved_reuse_key
            with _profile_span("module_runtime.lock"):
                lock = handle.lock_for(resolved_lock_key)
                with _profile_span("module_runtime.lock.wait"):
                    await lock.acquire()
                try:
                    with _profile_span("module_runtime.lock.body"):
                        result = await self._invoke_subject(
                            subject=handle.subject,
                            module=module,
                            operation=operation,
                            payload=payload,
                            session=session,
                        )
                finally:
                    lock.release()
        else:
            subject = self._build_subject(module)
            result = await self._invoke_subject(
                subject=subject,
                module=module,
                operation=operation,
                payload=payload,
                session=session,
            )
        if operation == "render":
            with _profile_span("module_runtime.restore_builder"):
                return restore_builder_snapshot(dict(result))
        return result

    def stop_module(self, module_name: str) -> None:
        prefix = f"module:{module_name}"
        with self._lock:
            keys = [key for key in self._handles if key.startswith(prefix)]
            for key in keys:
                self._handles.pop(key, None)

    def shutdown(self) -> None:
        with self._lock:
            self._handles.clear()


def get_module_runtime() -> ModuleRuntime:
    ctx = app_ctx()
    runtime = getattr(ctx, "module_runtime", None)
    if runtime is None:
        runtime = ModuleRuntime()
        ctx.module_runtime = runtime
    return runtime
