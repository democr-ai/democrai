from __future__ import annotations

import os
import socket
import subprocess
import time
from typing import Any


def configure_core_args(args: Any) -> None:
    args.http = True


class TauriDevProcess:
    def __init__(self, *, web_proc: subprocess.Popen, tauri_proc: subprocess.Popen) -> None:
        self.web_proc = web_proc
        self.tauri_proc = tauri_proc
        self.pid = tauri_proc.pid

    def poll(self):
        return self.tauri_proc.poll()

    def terminate(self) -> None:
        self.tauri_proc.terminate()
        self.web_proc.terminate()

    def kill(self) -> None:
        self.tauri_proc.kill()
        self.web_proc.kill()

    def wait(self, timeout: float | None = None):
        result = self.tauri_proc.wait(timeout=timeout)
        try:
            self.web_proc.wait(timeout=timeout)
        except Exception:
            pass
        return result


def _runtime_http_base_url(args: Any) -> str:
    host = _runtime_local_host(args)
    return f"http://{host}:{int(getattr(args, 'port', 8000))}"


def _runtime_ws_url(args: Any) -> str:
    host = _runtime_local_host(args)
    return f"ws://{host}:{int(getattr(args, 'port', 8000))}/ws"


def _runtime_local_host(args: Any) -> str:
    host = str(getattr(args, "host", "127.0.0.1"))
    if host in {"127.0.0.1", "0.0.0.0", "::"}:
        return "localhost"
    return host


def _tauri_cli_path(client_root: str) -> str:
    binary_name = "tauri.cmd" if os.name == "nt" else "tauri"
    return os.path.join(client_root, "node_modules", ".bin", binary_name)


def _env_with_user_cargo_path() -> dict:
    env = os.environ.copy()
    cargo_bin = os.path.join(os.path.expanduser("~"), ".cargo", "bin")
    if os.path.isdir(cargo_bin):
        path = env.get("PATH", "")
        parts = path.split(os.pathsep) if path else []
        if cargo_bin not in parts:
            env["PATH"] = cargo_bin + (os.pathsep + path if path else "")
    return env


def _yarn_command() -> str:
    return "yarn"


def _ensure_dev_port_free(*, host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((host, port)) == 0:
            raise RuntimeError(
                f"Tauri web client dev port already in use: {host}:{port}"
            )


def _wait_for_web_client_ready(
    *,
    web_proc: subprocess.Popen,
    url: str,
    timeout_seconds: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    host, port = _host_port_from_http_url(url)

    while time.monotonic() < deadline:
        return_code = web_proc.poll()
        if return_code is not None:
            raise RuntimeError(f"Tauri web client exited early with code {return_code}")

        try:
            if _http_ready(host=host, port=port):
                return
        except OSError as exc:
            last_error = str(exc)

        time.sleep(0.2)

    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"Tauri web client did not become ready at {url}{detail}")


def _host_port_from_http_url(url: str) -> tuple[str, int]:
    normalized = url.removeprefix("http://")
    host_port = normalized.split("/", 1)[0]
    host, port = host_port.rsplit(":", 1)
    return host, int(port)


def _http_ready(*, host: str, port: int) -> bool:
    with socket.create_connection((host, port), timeout=1.0) as sock:
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = sock.recv(64)
    if not response.startswith(b"HTTP/"):
        return False
    parts = response.split(b" ", 2)
    if len(parts) < 2:
        return False
    return int(parts[1]) < 500


def _wait_for_tauri_startup(
    *,
    process: TauriDevProcess,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        return_code = process.tauri_proc.poll()
        if return_code is not None:
            process.terminate()
            raise RuntimeError(f"Tauri client exited early with code {return_code}")
        time.sleep(0.2)


def start(*, args: Any, ipc_endpoint: str, app_dir: str, client_root: str):
    web_client_name = str(
        getattr(args, "tauri_web_client", "") or "webclient"
    ).strip()
    web_client_root = os.path.join(app_dir, "clients", web_client_name)
    if not os.path.isdir(web_client_root):
        raise RuntimeError(f"Client directory not found: {web_client_root}")
    if not os.path.isdir(client_root):
        raise RuntimeError(f"Tauri client directory not found: {client_root}")
    if not os.path.isfile(_tauri_cli_path(client_root)):
        raise RuntimeError(
            "Tauri CLI not installed for clients/tauri. "
            "Run: yarn --cwd clients/tauri install"
        )

    dev_host = "localhost"
    dev_port = 5173
    dev_url = f"http://{dev_host}:{dev_port}"
    _ensure_dev_port_free(host=dev_host, port=dev_port)

    yarn = _yarn_command()
    web_env = os.environ.copy()
    web_env["VITE_A2UI_TRANSPORT"] = "tauri-ipc"
    web_env["VITE_A2UI_HTTP_BASE_URL"] = _runtime_http_base_url(args)
    web_env["VITE_A2UI_WS_URL"] = _runtime_ws_url(args)
    web_proc = subprocess.Popen(
        [
            yarn,
            "dev",
            "--host",
            dev_host,
            "--port",
            str(dev_port),
            "--strictPort",
        ],
        cwd=web_client_root,
        env=web_env,
    )

    try:
        _wait_for_web_client_ready(web_proc=web_proc, url=dev_url)
    except Exception:
        web_proc.terminate()
        raise

    tauri_env = _env_with_user_cargo_path()
    tauri_env["DEMOCRAI_TAURI_WEB_CLIENT"] = web_client_name
    tauri_env["DEMOCRAI_TAURI_DEV_URL"] = dev_url
    tauri_env["DEMOCRAI_TAURI_HTTP_BASE_URL"] = _runtime_http_base_url(args)
    tauri_env["DEMOCRAI_IPC_ENDPOINT"] = str(ipc_endpoint)
    tauri_proc = subprocess.Popen([yarn, "dev"], cwd=client_root, env=tauri_env)
    process = TauriDevProcess(web_proc=web_proc, tauri_proc=tauri_proc)
    _wait_for_tauri_startup(process=process)
    return process
