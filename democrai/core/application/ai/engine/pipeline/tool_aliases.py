from __future__ import annotations

import re
from hashlib import sha1
from typing import Any

from democrai.core.application.ai.engine.schemas.completion import Function
from democrai.core.application.ai.engine.schemas.completion import Tool


TOOL_ALIAS_MAP_OPTION = "__democrai_tool_alias_map"
_MAX_TOOL_ALIAS_LENGTH = 128
_HASH_LENGTH = 10
_WIRE_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9-]+")


def tool_wire_name(runtime_name: str) -> str:
    resolved = runtime_name.strip() if isinstance(runtime_name, str) else ""
    if not resolved:
        raise ValueError("tool name is required")
    digest = sha1(resolved.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    prefix_limit = _MAX_TOOL_ALIAS_LENGTH - _HASH_LENGTH - 1
    prefix = _WIRE_UNSAFE_CHARS.sub("_", resolved)[:prefix_limit].strip("_")
    if not prefix:
        prefix = "tool"
    return f"{prefix}_{digest}"


def alias_completion_tools(
    tools: list[Any],
) -> tuple[list[Any], dict[str, str]]:
    alias_map: dict[str, str] = {}
    aliased_tools: list[Any] = []
    for tool in tools:
        aliased_tool, wire_name, runtime_name = _alias_completion_tool(tool)
        alias_map[wire_name] = runtime_name
        aliased_tools.append(aliased_tool)
    return aliased_tools, alias_map


_TOOL_NAME_SEP = re.compile(r"[._\-\s]+")
_HASH_TOKEN = re.compile(r"^[0-9a-f]{6,}$")


def _canonical_tool_name(name: str) -> str:
    """Forma canonica per il match dei nomi tool.

    Tratta ``. _ -`` come separatori equivalenti, e' case-insensitive, e scarta
    un eventuale token-hash finale (lo ``sha1[:10]`` appeso da ``tool_wire_name``).
    Serve a recuperare il nome runtime da cio' che i modelli realmente emettono:
    hash troncato/alterato, ritorno al nome a punti senza hash, separatori misti.
    """
    resolved = name.strip().lower() if isinstance(name, str) else ""
    if not resolved:
        return ""
    parts = [p for p in _TOOL_NAME_SEP.split(resolved) if p]
    if len(parts) > 1 and _HASH_TOKEN.match(parts[-1]):
        parts = parts[:-1]
    return ".".join(parts)


def resolve_tool_call_name(function_name: str, alias_map: dict[str, str] | None) -> str:
    name = function_name.strip() if isinstance(function_name, str) else ""
    if not alias_map:
        return name
    # 1. match esatto sul nome wire (il modello ha ri-emesso l'alias perfetto)
    exact = alias_map.get(name)
    if exact:
        return str(exact)
    runtime_names = list(dict.fromkeys(alias_map.values()))
    # 2. il modello e' tornato al nome runtime reale (es. "chat.list-attachments")
    if name in runtime_names:
        return name
    # 3. match canonico: recupera hash storpiato, hash assente, separatori misti
    target = _canonical_tool_name(name)
    if target:
        for runtime_name in runtime_names:
            if _canonical_tool_name(runtime_name) == target:
                return str(runtime_name)
        for wire_name, runtime_name in alias_map.items():
            if _canonical_tool_name(wire_name) == target:
                return str(runtime_name)
    return name


def alias_tool_choice(tool_choice: Any, alias_map: dict[str, str]) -> Any:
    if not isinstance(tool_choice, dict) or not alias_map:
        return tool_choice
    if isinstance(tool_choice.get("function"), dict):
        function = dict(tool_choice["function"])
        name = str(function.get("name") or "").strip()
        if name:
            function["name"] = _runtime_to_wire_name(name, alias_map)
        resolved = dict(tool_choice)
        resolved["function"] = function
        return resolved
    if "name" in tool_choice:
        resolved = dict(tool_choice)
        name = str(resolved.get("name") or "").strip()
        if name:
            resolved["name"] = _runtime_to_wire_name(name, alias_map)
        return resolved
    return tool_choice


def _runtime_to_wire_name(runtime_name: str, alias_map: dict[str, str]) -> str:
    for wire_name, mapped_runtime_name in alias_map.items():
        if mapped_runtime_name == runtime_name:
            return wire_name
    return runtime_name


def _alias_completion_tool(tool: Any) -> tuple[Any, str, str]:
    if isinstance(tool, Tool):
        runtime_name = tool.function.name
        wire_name = tool_wire_name(runtime_name)
        return (
            tool.model_copy(
                update={
                    "function": tool.function.model_copy(update={"name": wire_name})
                }
            ),
            wire_name,
            runtime_name,
        )
    if isinstance(tool, dict):
        function = tool.get("function")
        if not isinstance(function, dict):
            raise TypeError("completion_tool_function_expected")
        runtime_name = str(function.get("name") or "").strip()
        wire_name = tool_wire_name(runtime_name)
        resolved_function = dict(function)
        resolved_function["name"] = wire_name
        resolved_tool = dict(tool)
        resolved_tool["function"] = resolved_function
        return resolved_tool, wire_name, runtime_name
    function = getattr(tool, "function", None)
    runtime_name = str(getattr(function, "name", "") or "").strip()
    wire_name = tool_wire_name(runtime_name)
    return (
        Tool(
            type=str(getattr(tool, "type", "function") or "function"),
            function=Function(
                name=wire_name,
                description=getattr(function, "description", None),
                parameters=getattr(function, "parameters", None)
                or {"type": "object", "properties": {}},
            ),
        ),
        wire_name,
        runtime_name,
    )
