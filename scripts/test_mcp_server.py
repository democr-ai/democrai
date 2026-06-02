#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT_CHARS = 24000
ACTIVE_TRANSPORT = "stdio"
DIRECT_DELETE_PROBE_PATH = Path("/var/tmp/democrai_mcp_direct_delete_probe.txt")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    func: Callable[[dict[str, Any]], dict[str, Any]]


def _json_response(result: Any = None, *, error: dict[str, Any] | None = None, request_id: Any = None) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result if isinstance(result, dict) else {"content": result}
    return payload


def _tool_content(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        "isError": is_error,
    }


def _safe_repo_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("path_required")
    path = Path(raw)
    if path.is_absolute():
        raise ValueError(f"absolute_path_not_allowed:{raw}")
    resolved = (REPO_ROOT / path).resolve()
    root = REPO_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path_escapes_repo:{raw}")
    return str(path.as_posix()).strip("/")


def _safe_package_dir(value: str) -> str:
    raw = _safe_repo_path(value)
    allowed = {
        "clients/webclient",
        "clients/reactbootstrap",
        "clients/tauri",
        "docs_site",
    }
    if raw not in allowed:
        raise ValueError(f"package_dir_not_allowed:{raw}")
    return raw


def _string_list(value: Any, *, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if not isinstance(value, list):
        raise ValueError("expected_list")
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    return max(minimum, min(maximum, parsed))


def _run_command(argv: list[str], *, cwd: Path = REPO_ROOT, timeout_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    stdout = proc.stdout[-MAX_OUTPUT_CHARS:]
    stderr = proc.stderr[-MAX_OUTPUT_CHARS:]
    return {
        "command": argv,
        "cwd": str(cwd.relative_to(REPO_ROOT) if cwd != REPO_ROOT else "."),
        "returncode": proc.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout": stdout,
        "stderr": stderr,
        "ok": proc.returncode == 0,
    }


def _list_tests(args: dict[str, Any]) -> dict[str, Any]:
    root = _safe_repo_path(str(args.get("root") or "tests"))
    pattern = str(args.get("pattern") or "test_*.py").strip() or "test_*.py"
    limit = _bounded_int(args.get("limit"), default=200, minimum=1, maximum=1000)
    base = (REPO_ROOT / root).resolve()
    if not base.exists():
        return _tool_content({"root": root, "tests": [], "count": 0})
    tests = [
        item.relative_to(REPO_ROOT).as_posix()
        for item in sorted(base.rglob(pattern))
        if item.is_file()
    ][:limit]
    return _tool_content({"root": root, "tests": tests, "count": len(tests)})


def _run_py_compile(args: dict[str, Any]) -> dict[str, Any]:
    paths = _string_list(args.get("paths"), default=[])
    if not paths:
        raise ValueError("paths_required")
    safe_paths = [_safe_repo_path(path) for path in paths]
    timeout_seconds = _bounded_int(
        args.get("timeout_seconds"),
        default=120,
        minimum=1,
        maximum=1800,
    )
    result = _run_command(
        [sys.executable, "-m", "py_compile", *safe_paths],
        timeout_seconds=timeout_seconds,
    )
    return _tool_content(result, is_error=not result["ok"])


def _run_pytest(args: dict[str, Any]) -> dict[str, Any]:
    targets = [_safe_repo_path(path) for path in _string_list(args.get("targets"), default=["tests"])]
    timeout_seconds = _bounded_int(
        args.get("timeout_seconds"),
        default=1200,
        minimum=1,
        maximum=7200,
    )
    argv = [sys.executable, "-m", "pytest"]
    if bool(args.get("quiet", True)):
        argv.append("-q")
    maxfail = args.get("maxfail")
    if maxfail is not None:
        argv.append(f"--maxfail={_bounded_int(maxfail, default=1, minimum=1, maximum=100)}")
    keyword = str(args.get("keyword") or "").strip()
    if keyword:
        argv.extend(["-k", keyword])
    marker = str(args.get("marker") or "").strip()
    if marker:
        argv.extend(["-m", marker])
    argv.extend(targets)
    result = _run_command(argv, timeout_seconds=timeout_seconds)
    return _tool_content(result, is_error=not result["ok"])


def _run_package_script(args: dict[str, Any]) -> dict[str, Any]:
    package_dir = _safe_package_dir(str(args.get("package_dir") or ""))
    script = str(args.get("script") or "").strip()
    if not script:
        raise ValueError("script_required")
    timeout_seconds = _bounded_int(
        args.get("timeout_seconds"),
        default=1200,
        minimum=1,
        maximum=7200,
    )
    package_json = REPO_ROOT / package_dir / "package.json"
    if not package_json.exists():
        raise ValueError(f"package_json_not_found:{package_dir}")
    package = json.loads(package_json.read_text(encoding="utf-8"))
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    if script not in scripts:
        raise ValueError(f"script_not_found:{package_dir}:{script}")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    result = _run_command(
        [npm, "run", script],
        cwd=REPO_ROOT / package_dir,
        timeout_seconds=timeout_seconds,
    )
    return _tool_content(result, is_error=not result["ok"])


def _delete_direct_probe(_args: dict[str, Any]) -> dict[str, Any]:
    if ACTIVE_TRANSPORT == "http":
        raise ValueError("tool_not_available_over_http")
    DIRECT_DELETE_PROBE_PATH.unlink()
    return _tool_content(
        {
            "ok": True,
            "deleted": str(DIRECT_DELETE_PROBE_PATH),
        }
    )


TOOLS: dict[str, Tool] = {
    "list_tests": Tool(
        name="list_tests",
        description="List Python test files under a repository path.",
        input_schema={
            "type": "object",
            "properties": {
                "root": {"type": "string", "default": "tests"},
                "pattern": {"type": "string", "default": "test_*.py"},
                "limit": {"type": "integer", "default": 200},
            },
        },
        func=_list_tests,
    ),
    "run_py_compile": Tool(
        name="run_py_compile",
        description="Run python -m py_compile on explicit repository-relative files.",
        input_schema={
            "type": "object",
            "required": ["paths"],
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {"type": "integer", "default": 120},
            },
        },
        func=_run_py_compile,
    ),
    "run_pytest": Tool(
        name="run_pytest",
        description="Run pytest on repository-relative targets with constrained pytest options.",
        input_schema={
            "type": "object",
            "properties": {
                "targets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["tests"],
                },
                "keyword": {"type": "string"},
                "marker": {"type": "string"},
                "quiet": {"type": "boolean", "default": True},
                "maxfail": {"type": "integer"},
                "timeout_seconds": {"type": "integer", "default": 1200},
            },
        },
        func=_run_pytest,
    ),
    "run_package_script": Tool(
        name="run_package_script",
        description="Run an npm script from an allowed frontend/docs package directory.",
        input_schema={
            "type": "object",
            "required": ["package_dir", "script"],
            "properties": {
                "package_dir": {
                    "type": "string",
                    "enum": [
                        "clients/webclient",
                        "clients/reactbootstrap",
                        "clients/tauri",
                        "docs_site",
                    ],
                },
                "script": {"type": "string"},
                "timeout_seconds": {"type": "integer", "default": 1200},
            },
        },
        func=_run_package_script,
    ),
    "delete_direct_probe": Tool(
        name="delete_direct_probe",
        description="Delete the fixed direct MCP sandbox probe file.",
        input_schema={
            "type": "object",
            "properties": {},
        },
        func=_delete_direct_probe,
    ),
}


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
        }
        for tool in TOOLS.values()
    ]


def handle_jsonrpc(message: dict[str, Any]) -> dict[str, Any] | None:
    method = str(message.get("method") or "").strip()
    request_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if not request_id and method.startswith("notifications/"):
        return None
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "democrai-test-mcp", "version": "0.1.0"},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": _tool_specs()}
        elif method == "tools/call":
            name = str(params.get("name") or "").strip()
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            tool = TOOLS.get(name)
            if tool is None:
                raise ValueError(f"unknown_tool:{name}")
            result = tool.func(arguments)
        else:
            return _json_response(
                error={"code": -32601, "message": f"method_not_found:{method}"},
                request_id=request_id,
            )
        return _json_response(result=result, request_id=request_id)
    except subprocess.TimeoutExpired as exc:
        return _json_response(
            result=_tool_content(
                {
                    "ok": False,
                    "error": "timeout",
                    "command": list(exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd),
                    "timeout_seconds": exc.timeout,
                },
                is_error=True,
            ),
            request_id=request_id,
        )
    except Exception as exc:
        return _json_response(
            error={"code": -32000, "message": str(exc)},
            request_id=request_id,
        )


class McpHttpHandler(BaseHTTPRequestHandler):
    server_version = "DemocraiTestMCP/0.1"

    def do_GET(self) -> None:
        if self.path.rstrip("/") not in {"", "/health"}:
            self.send_error(404)
            return
        self._write_json({"ok": True, "server": "democrai-test-mcp"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        try:
            message = json.loads(raw.decode("utf-8"))
            if not isinstance(message, dict):
                raise ValueError("jsonrpc_payload_must_be_object")
            response = handle_jsonrpc(message)
            self._write_json(response or {})
        except Exception as exc:
            self._write_json(
                _json_response(
                    error={"code": -32700, "message": str(exc)},
                    request_id=None,
                ),
                status=400,
            )

    def log_message(self, fmt: str, *args: Any) -> None:
        print(fmt % args, file=sys.stderr)

    def _write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _read_stdio_message() -> dict[str, Any] | None:
    first = sys.stdin.buffer.readline()
    if not first:
        return None
    if first.startswith(b"Content-Length:"):
        length = int(first.split(b":", 1)[1].strip())
        while True:
            line = sys.stdin.buffer.readline()
            if line in {b"\r\n", b"\n", b""}:
                break
        raw = sys.stdin.buffer.read(length)
        return json.loads(raw.decode("utf-8"))
    return json.loads(first.decode("utf-8"))


def _write_stdio_message(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def run_stdio() -> None:
    global ACTIVE_TRANSPORT
    ACTIVE_TRANSPORT = "stdio"
    while True:
        message = _read_stdio_message()
        if message is None:
            return
        response = handle_jsonrpc(message)
        if response is not None:
            _write_stdio_message(response)


def run_http(host: str, port: int) -> None:
    global ACTIVE_TRANSPORT
    ACTIVE_TRANSPORT = "http"
    httpd = ThreadingHTTPServer((host, port), McpHttpHandler)
    print(f"democrai-test-mcp listening on http://{host}:{port}", file=sys.stderr)
    httpd.serve_forever()


def run_direct(tool_name: str, arguments: str) -> int:
    global ACTIVE_TRANSPORT
    ACTIVE_TRANSPORT = "direct"
    parsed_args = json.loads(arguments or "{}")
    if not isinstance(parsed_args, dict):
        raise ValueError("arguments_must_be_object")
    response = handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": "direct",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": parsed_args},
        }
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))
    if not response or response.get("error"):
        return 1
    content = response.get("result", {}).get("content", [])
    if content and isinstance(content, list):
        try:
            payload = json.loads(content[0].get("text") or "{}")
            return 0 if payload.get("ok", True) else 1
        except Exception:
            return 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="External MCP server for Democr.ai tests.")
    parser.add_argument(
        "--transport",
        choices=["http", "stdio", "direct"],
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--tool", default="")
    parser.add_argument("--arguments", default="{}")
    args = parser.parse_args()

    if args.transport == "http":
        run_http(args.host, args.port)
        return 0
    if args.transport == "direct":
        if not args.tool:
            raise ValueError("--tool is required with --transport direct")
        return run_direct(args.tool, args.arguments)
    run_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
