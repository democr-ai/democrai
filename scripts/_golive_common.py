from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

import websockets

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = APP_DIR.parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_BASE_PORT = 8001


def build_server_cmd(
    *,
    exe_path: str | None,
    host: str,
    port: int,
    workers: int,
    dev: int = 0,
) -> list[str]:
    if exe_path:
        cmd = [exe_path]
    else:
        cmd = [sys.executable, str(APP_DIR / "main.py")]

    cmd.extend(
        [
            "--mode",
            "server",
            "--http",
            "--host",
            host,
            "--port",
            str(port),
            "--workers",
            str(max(1, workers)),
        ]
    )
    if dev:
        cmd.extend(["--dev", str(dev)])
    return cmd


def launch_instances(
    *,
    instances: int,
    workers: int,
    exe_path: str | None,
    host: str,
    base_port: int,
    log_dir: Path,
    dev: int = 0,
    startup_delay_s: float = 1.5,
) -> tuple[list[subprocess.Popen], list[int], list[object]]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    processes: list[subprocess.Popen] = []
    ports: list[int] = []
    log_handles: list[object] = []
    log_dir.mkdir(parents=True, exist_ok=True)

    for index in range(max(1, instances)):
        port = base_port + index
        ports.append(port)
        cmd = build_server_cmd(
            exe_path=exe_path, host=host, port=port, workers=workers, dev=dev
        )
        log_path = log_dir / f"instance_{index}.log"
        log_handle = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(APP_DIR),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        processes.append(proc)
        log_handles.append(log_handle)
        time.sleep(startup_delay_s)

    return processes, ports, log_handles


def close_logs(log_handles: Iterable[object]) -> None:
    for handle in log_handles:
        try:
            handle.close()
        except Exception:
            continue


async def wait_for_ws(host: str, port: int, timeout_s: float = 60.0) -> bool:
    url = f"ws://{host}:{port}/ws"
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        try:
            async with websockets.connect(url) as ws:
                await asyncio.wait_for(ws.recv(), timeout=5.0)
                return True
        except Exception:
            await asyncio.sleep(0.5)
    return False


def wait_for_http_ping(host: str, port: int, timeout_s: float = 60.0) -> bool:
    url = f"http://{host}:{port}/ping"
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=5.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict):
                    candidate = payload
                elif (
                    isinstance(payload, list)
                    and payload
                    and isinstance(payload[0], dict)
                ):
                    candidate = payload[0]
                else:
                    candidate = None

                if (
                    candidate is not None
                    and candidate.get("ok") is True
                    and candidate.get("type") == "pong"
                ):
                    return True
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
        ):
            time.sleep(0.5)
    return False


async def ws_login_and_nav(
    *,
    host: str,
    port: int,
    username: str = "admin",
    password: str = "password",
    path: str = "/components/yaml_demo_page",
) -> dict:
    url = f"ws://{host}:{port}/ws"
    async with websockets.connect(url) as ws:
        await asyncio.wait_for(ws.recv(), timeout=10.0)

        login_req = {
            "type": "userAction",
            "userAction": {
                "name": "auth.login_submit",
                "context": {"username": username, "password": password},
            },
            "request_id": "golive_login",
        }
        await ws.send(json.dumps(login_req))

        jwt = None
        for _ in range(20):
            resp = await asyncio.wait_for(ws.recv(), timeout=10.0)
            data = json.loads(resp)
            if isinstance(data, dict) and "jwt" in data:
                jwt = data["jwt"]
                break
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "jwt" in item:
                        jwt = item["jwt"]
                        break
                if jwt:
                    break
        if not jwt:
            raise RuntimeError("JWT not received after login")

        nav_req = {
            "type": "userAction",
            "userAction": {"name": "nav", "context": {"path": path}},
            "jwt": jwt,
            "request_id": "golive_nav",
        }
        await ws.send(json.dumps(nav_req))

        for _ in range(30):
            resp = await asyncio.wait_for(ws.recv(), timeout=10.0)
            if _payload_contains_marker(resp, "beginRendering"):
                return {"ok": True, "jwt": jwt}

        raise RuntimeError("Navigation response did not contain beginRendering")


def _payload_contains_marker(payload: str, marker: str) -> bool:
    if marker in payload:
        return True
    try:
        decoded = json.loads(payload)
    except Exception:
        return False
    if isinstance(decoded, dict):
        return marker in decoded
    if isinstance(decoded, list):
        return any(isinstance(item, dict) and marker in item for item in decoded)
    return False


def _terminate_proc(proc: subprocess.Popen, force: bool = False) -> None:
    try:
        if force:
            proc.kill()
        else:
            proc.terminate()
    except Exception:
        pass


def _children_recursive(pid: int) -> list[int]:
    if psutil is None:
        return []
    try:
        root = psutil.Process(pid)
        return [child.pid for child in root.children(recursive=True)]
    except Exception:
        return []


def _pid_exists(pid: int) -> bool:
    if psutil is not None:
        try:
            return psutil.pid_exists(pid)
        except Exception:
            pass
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def terminate_processes(
    processes: Iterable[subprocess.Popen],
    *,
    sig: int = signal.SIGTERM,
    timeout_s: float = 5.0,
) -> list[int]:
    pending_pids: list[int] = []
    tracked: list[tuple[subprocess.Popen, list[int]]] = []

    for proc in processes:
        descendants = _children_recursive(proc.pid)
        tracked.append((proc, descendants))
        try:
            proc.send_signal(sig)
        except Exception:
            _terminate_proc(proc, force=False)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        alive = []
        for proc, descendants in tracked:
            if proc.poll() is None:
                alive.append(proc.pid)
            for pid in descendants:
                if _pid_exists(pid):
                    alive.append(pid)
        if not alive:
            return []
        time.sleep(0.2)

    for proc, descendants in tracked:
        _terminate_proc(proc, force=True)
        for pid in descendants:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

    for proc, descendants in tracked:
        if proc.poll() is None:
            pending_pids.append(proc.pid)
        for pid in descendants:
            if _pid_exists(pid):
                pending_pids.append(pid)

    return sorted(set(pending_pids))
