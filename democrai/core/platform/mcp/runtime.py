from __future__ import annotations

import asyncio
# The guarded HTTP client can trigger Python's IDNA codec lazily during connect.
import encodings.idna  # noqa: F401
import os
import shutil
import threading
import time
from contextlib import contextmanager
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.infrastructure.sandbox.process_guard import process_guard_bypass_context
from democrai.core.infrastructure.sandbox.process_guard import runtime_system_read_paths
from democrai.core.platform.mcp.access_constants import (
    mcp_runtime_create_paths,
    mcp_runtime_modify_paths,
    mcp_runtime_read_paths,
)
from democrai.core.platform.agents.models import AgentToolDefinition
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx
from democrai.core.runtime.foundation.paths import data_dir

from .client import McpClient
from .registry import McpServerRecord
from .registry import get_server_by_name


_TOOL_CACHE_TTL_SECONDS = 60.0


def _path_variants(path: str) -> list[str]:
    variants = [
        os.path.abspath(os.path.expanduser(path)),
        os.path.realpath(os.path.abspath(os.path.expanduser(path))),
    ]
    for item in list(variants):
        if os.path.isfile(item):
            variants.append(os.path.dirname(item))
    result: list[str] = []
    for item in variants:
        if item not in result:
            result.append(item)
    return result


def _under_data_dir(path: str) -> bool:
    try:
        resolved = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
        with process_guard_bypass_context():
            root = str(data_dir().resolve())
    except Exception:
        return False
    return resolved == root or resolved.startswith(root + os.sep)


def _outside_data_dir(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(path for path in paths if not _under_data_dir(path))


class McpRuntime:
    def __init__(self) -> None:
        self._tool_cache: dict[str, tuple[list[AgentToolDefinition], float]] = {}
        self._tool_cache_lock = threading.Lock()

    def invalidate_tool_cache(self, *, server_name: str | None = None) -> None:
        with self._tool_cache_lock:
            if server_name is None:
                self._tool_cache.clear()
                return
            key = server_name.strip() if isinstance(server_name, str) else ""
            self._tool_cache.pop(key, None)

    def _cached_tools(self, server_name: str) -> list[AgentToolDefinition] | None:
        with self._tool_cache_lock:
            entry = self._tool_cache.get(server_name)
            if entry is None:
                return None
            tools, expires_at = entry
            if expires_at < time.monotonic():
                self._tool_cache.pop(server_name, None)
                return None
            return list(tools)

    def _store_cached_tools(
        self, server_name: str, tools: list[AgentToolDefinition]
    ) -> None:
        with self._tool_cache_lock:
            self._tool_cache[server_name] = (
                list(tools),
                time.monotonic() + _TOOL_CACHE_TTL_SECONDS,
            )

    def _request_scope(self) -> tuple[int | None, int | None, str | None]:
        try:
            ctx = req_ctx()
        except Exception:
            return None, None, None
        return (
            to_optional_int(ctx.user),
            to_optional_int(ctx.organization_id),
            ctx.session_key.strip() if isinstance(ctx.session_key, str) and ctx.session_key.strip() else None,
        )

    def _direct_access_rules(self, *, server: McpServerRecord) -> list[AccessManifestRule]:
        config = {} if server.config is None else dict(server.config)
        command = config.get("command")
        args = config.get("args") if isinstance(config.get("args"), list) else []
        if not isinstance(command, list) or not command:
            return []
        executable = command[0].strip() if isinstance(command[0], str) else ""
        if not executable:
            return []
        target = executable
        if not os.path.isabs(target) and os.sep not in target:
            target = shutil.which(target) or target
        subject = AccessSubject.create("mcp", f"mcp.{server.name}")
        executable_paths = [] if _under_data_dir(target) else _path_variants(target)
        rules = [
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="execute",
                    target=path,
                ),
            )
            for path in executable_paths
            if not _under_data_dir(path)
        ]
        for item in [*command[1:], *args]:
            path = item.strip() if isinstance(item, str) else ""
            if not path or _under_data_dir(path) or not os.path.exists(path):
                continue
            rules.extend(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type="filesystem",
                        operation="read",
                        target=variant,
                    ),
                )
                for variant in _path_variants(path)
                if not _under_data_dir(variant)
            )
        return rules

    @contextmanager
    def _mcp_guard(self, *, server: McpServerRecord):
        user_id, organization_id, session_key = self._request_scope()
        subject = AccessSubject.create("mcp", f"mcp.{server.name}")
        access = []
        if server.transport == "http":
            access.extend(
                [
                    AccessManifestRule(
                        subject=subject,
                        resource=AccessResource.create(
                            resource_type="network",
                            operation="connect",
                            target=server.endpoint_url,
                        ),
                    ),
                    AccessManifestRule(
                        subject=subject,
                        resource=AccessResource.create(
                            resource_type="network",
                            operation="send",
                            target=server.endpoint_url,
                        ),
                    ),
                    AccessManifestRule(
                        subject=subject,
                        resource=AccessResource.create(
                            resource_type="network",
                            operation="receive",
                            target=server.endpoint_url,
                        ),
                    ),
                ]
            )
        if server.transport == "direct":
            with process_guard_bypass_context():
                access.extend(self._direct_access_rules(server=server))
            access.extend(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type="filesystem",
                        operation="read",
                        target=path,
                    ),
                )
                for path in runtime_system_read_paths()
            )
        for operation, paths in (
            ("read", _outside_data_dir(mcp_runtime_read_paths())),
            ("create", _outside_data_dir(mcp_runtime_create_paths())),
            ("modify", _outside_data_dir(mcp_runtime_modify_paths())),
        ):
            access.extend(
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
        with process_guard_context(
            subject=f"mcp.{server.name}",
            subject_kind="mcp",
            access=access,
            allow_subprocess=False,
            include_runtime_access=False,
            inherit_parent_access=False,
            user_id=user_id,
            organization_id=organization_id,
            session_key=session_key,
        ):
            yield

    def _log_skipped_server(self, name: str, reason: str) -> None:
        logger = getattr(app_ctx(), "logger", None)
        if logger is None:
            return
        warn = getattr(logger, "warning", None) or getattr(logger, "info", None)
        if callable(warn):
            warn(f"[mcp_runtime] skipped_server name={name} reason={reason}", "mcp")

    def _fetch_server_tools(
        self,
        *,
        server: McpServerRecord,
        module_name: str,
    ) -> list[AgentToolDefinition]:
        cached = self._cached_tools(server.name)
        if cached is not None:
            return cached
        with self._mcp_guard(server=server):
            tools = McpClient(server).list_tools()
        defs: list[AgentToolDefinition] = [
            AgentToolDefinition(
                name=f"mcp.{server.name}.{tool.name}",
                func=lambda **_: None,
                title=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                module_name="mcp",
            )
            for tool in tools
        ]
        self._store_cached_tools(server.name, defs)
        return list(defs)

    def list_agent_tool_definitions(
        self,
        *,
        module_name: str,
        server_names: tuple[str, ...] = (),
    ) -> list[AgentToolDefinition]:
        if not server_names:
            return []
        defs: list[AgentToolDefinition] = []
        for raw_name in server_names:
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                continue
            server = get_server_by_name(name)
            if server is None:
                self._log_skipped_server(name, "not_found_or_disabled")
                continue
            defs.extend(
                self._fetch_server_tools(
                    server=server,
                    module_name=module_name,
                )
            )
        return defs

    def invoke_tool(
        self,
        *,
        full_name: str,
        arguments: dict[str, Any] | None,
        module_name: str,
    ) -> Any:
        raw_name = full_name.strip() if isinstance(full_name, str) else ""
        if not raw_name.startswith("mcp."):
            raise ValueError("invalid_mcp_tool_name")
        parts = raw_name.split(".")
        if len(parts) < 3:
            raise ValueError("invalid_mcp_tool_name")
        server_name = parts[1]
        remote_tool_name = ".".join(parts[2:])
        server = get_server_by_name(server_name)
        if server is None:
            raise ValueError(f"unknown_mcp_server:{server_name}")
        with self._mcp_guard(server=server):
            return McpClient(server).call_tool(
                tool_name=remote_tool_name,
                arguments={} if arguments is None else dict(arguments),
            )

    async def list_agent_tool_definitions_async(
        self,
        *,
        module_name: str,
        server_names: tuple[str, ...] = (),
    ) -> list[AgentToolDefinition]:
        return await asyncio.to_thread(
            self.list_agent_tool_definitions,
            module_name=module_name,
            server_names=server_names,
        )

    async def invoke_tool_async(
        self,
        *,
        full_name: str,
        arguments: dict[str, Any] | None,
        module_name: str,
    ) -> Any:
        return await asyncio.to_thread(
            self.invoke_tool,
            full_name=full_name,
            arguments=arguments,
            module_name=module_name,
        )


mcp_runtime = McpRuntime()
