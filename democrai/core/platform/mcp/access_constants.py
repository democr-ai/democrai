from __future__ import annotations

from democrai.core.platform.utils.normalize import os_key

MCP_RUNTIME_READ_PATHS_BY_OS = {
    "linux": (),
    "darwin": (),
    "win32": (),
}

MCP_RUNTIME_CREATE_PATHS_BY_OS = {
    "linux": (),
    "darwin": (),
    "win32": (),
}

MCP_RUNTIME_MODIFY_PATHS_BY_OS = {
    "linux": (),
    "darwin": (),
    "win32": (),
}


def mcp_runtime_read_paths() -> tuple[str, ...]:
    return MCP_RUNTIME_READ_PATHS_BY_OS.get(os_key(), ())


def mcp_runtime_create_paths() -> tuple[str, ...]:
    return MCP_RUNTIME_CREATE_PATHS_BY_OS.get(os_key(), ())


def mcp_runtime_modify_paths() -> tuple[str, ...]:
    return MCP_RUNTIME_MODIFY_PATHS_BY_OS.get(os_key(), ())
