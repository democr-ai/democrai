from __future__ import annotations

import json
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any

from .registry import McpServerRecord


@dataclass(frozen=True)
class McpToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


class McpClient:
    def __init__(self, server: McpServerRecord):
        self.server = server

    def _request(self, *, method: str, params: dict[str, Any] | None = None, timeout_ms: int | None = None) -> dict[str, Any]:
        resolved_params = {} if params is None else dict(params)
        payload = {
            "jsonrpc": "2.0",
            "id": f"mcp-{self.server.name}-{method}",
            "method": method,
            "params": resolved_params,
        }
        if self.server.transport == "direct":
            return self._direct_request(payload=payload, timeout_ms=timeout_ms)
        return self._http_request(payload=payload, timeout_ms=timeout_ms)

    def _http_request(
        self,
        *,
        payload: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        config = {} if self.server.config is None else dict(self.server.config)
        config_headers = config.get("headers", {})
        headers_source = config_headers if isinstance(config_headers, dict) else {}
        for key, value in headers_source.items():
            header_name = key.strip() if isinstance(key, str) else ""
            if not header_name:
                continue
            headers[header_name] = value if isinstance(value, str) else ""
        timeout_seconds = max(1.0, float((timeout_ms or self.server.timeout_ms) / 1000.0))
        req = urllib.request.Request(
            self.server.endpoint_url,
            data=raw,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise RuntimeError("invalid_mcp_response_payload")
        if "error" in parsed and parsed["error"] is not None:
            raise RuntimeError(str(parsed["error"]))
        result = parsed.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("invalid_mcp_response_result")
        return result

    def _direct_request(
        self,
        *,
        payload: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        command = _direct_command(self.server.config)
        timeout_seconds = max(1.0, float((timeout_ms or self.server.timeout_ms) / 1000.0))
        raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        framed = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
        completed = subprocess.run(
            command,
            input=framed,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"mcp_direct_failed:{completed.returncode}:"
                f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
            )
        parsed = _parse_stdio_response(completed.stdout)
        if not isinstance(parsed, dict):
            raise RuntimeError("invalid_mcp_response_payload")
        if "error" in parsed and parsed["error"] is not None:
            raise RuntimeError(str(parsed["error"]))
        result = parsed.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("invalid_mcp_response_result")
        return result

    def list_tools(self) -> list[McpToolSpec]:
        result = self._request(method="tools/list", params={})
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise RuntimeError("invalid_mcp_tools_list")
        specs: list[McpToolSpec] = []
        for item in tools:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                continue
            raw_description = item.get("description")
            description = raw_description.strip() if isinstance(raw_description, str) else ""
            input_schema = item.get("inputSchema")
            if not isinstance(input_schema, dict):
                input_schema = {"type": "object", "properties": {}}
            specs.append(
                McpToolSpec(
                    name=name,
                    description=description,
                    input_schema=input_schema,
                )
            )
        return specs

    def call_tool(self, *, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        resolved_tool_name = tool_name.strip() if isinstance(tool_name, str) else ""
        resolved_arguments = {} if arguments is None else dict(arguments)
        result = self._request(
            method="tools/call",
            params={
                "name": resolved_tool_name,
                "arguments": resolved_arguments,
            },
        )
        return result.get("content", result)


def _direct_command(config: dict[str, Any]) -> list[str]:
    command = config.get("command") if isinstance(config, dict) else None
    args = config.get("args") if isinstance(config, dict) else None
    if not isinstance(command, list) or not command:
        raise ValueError("mcp_direct_command_required")
    if args is None:
        args = []
    if not isinstance(args, list):
        raise ValueError("mcp_direct_args_must_be_list")
    resolved = [item.strip() if isinstance(item, str) else "" for item in [*command, *args]]
    if not resolved or not resolved[0]:
        raise ValueError("mcp_direct_command_required")
    if any(not item for item in resolved):
        raise ValueError("mcp_direct_command_item_required")
    return resolved


def _parse_stdio_response(raw: bytes) -> dict[str, Any]:
    if raw.startswith(b"Content-Length:"):
        header, _, body = raw.partition(b"\r\n\r\n")
        if not body:
            header, _, body = raw.partition(b"\n\n")
        length_line = header.splitlines()[0]
        length = int(length_line.split(b":", 1)[1].strip())
        return json.loads(body[:length].decode("utf-8"))
    return json.loads(raw.decode("utf-8"))
