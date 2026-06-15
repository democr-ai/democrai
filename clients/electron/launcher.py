from __future__ import annotations

import os
import socket
import subprocess
import time
from typing import Any


def configure_core_args(args: Any) -> None:
    args.http = True


class ElectronDevProcess:
    def __init__(self, *, web_proc: subprocess.Popen, electron_proc: subprocess.Popen) -> None:
        self.web_proc = web_proc
        self.electron_proc = electron_proc
        self.pid = electron_proc.pid

    def poll(self):
        return self.electron_proc.poll()

    def terminate(self) -> None:
        self.electron_proc.terminate()
        self.web_proc.terminate()

    def kill(self) -> None:
        self.electron_proc.kill()
        self.web_proc.kill()

    def wait(self, timeout: float | None = None):
        result = self.electron_proc.wait(timeout=timeout)
        try:
            self.web_proc.wait(timeout=timeout)
        except Exception:
            pass
        return result


def _runtime_local_host(args: Any) -> str:
    host = str(getattr(args, "host", "127.0.0.1"))
    if host in {"127.0.0.1", "0.0.0.0", "::"}:
        return "localhost"
    return host


def _runtime_http_base_url(args: Any) -> str:
    host = _runtime_local_host(args)
    return f"http://{host}:{int(getattr(args, 'port', 8000))}"


def _runtime_ws_url(args: Any) -> str:
    host = _runtime_local_host(args)
    return f"ws://{host}:{int(getattr(args, 'port', 8000))}/ws"


def _yarn_command() -> str:
    return "yarn"


def _electron_cli_path(client_root: str) -> str:
    binary_name = "electron.cmd" if os.name == "nt" else "electron"
    return os.path.join(client_root, "node_modules", ".bin", binary_name)


def _electron_runtime_path(client_root: str) -> str | None:
    electron_pkg = os.path.join(client_root, "node_modules", "electron")
    path_file = os.path.join(electron_pkg, "path.txt")
    try:
        with open(path_file, "r", encoding="utf-8") as handle:
            relative_path = handle.read().strip()
    except OSError:
        return None
    if not relative_path:
        return None
    return os.path.join(electron_pkg, "dist", relative_path)


def _ensure_electron_installed(client_root: str) -> None:
    if not os.path.isfile(_electron_cli_path(client_root)):
        raise RuntimeError(
            "Electron is not installed for clients/electron. "
            "Run: yarn --cwd clients/electron install"
        )
    runtime_path = _electron_runtime_path(client_root)
    if not runtime_path or not os.path.exists(runtime_path):
        raise RuntimeError(
            "Electron package is installed but its runtime binary is missing. "
            "Run: yarn --cwd clients/electron install --force"
        )


def _is_port_free(*, host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def _find_free_port(*, host: str, start_port: int) -> int:
    for port in range(start_port, start_port + 100):
        if _is_port_free(host=host, port=port):
            return port
    raise RuntimeError(f"Unable to find a free Electron web client dev port from {start_port}")


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
    return len(parts) >= 2 and int(parts[1]) < 500


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
            raise RuntimeError(f"Electron web client exited early with code {return_code}")
        try:
            if _http_ready(host=host, port=port):
                return
        except OSError as exc:
            last_error = str(exc)
        time.sleep(0.2)

    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"Electron web client did not become ready at {url}{detail}")


def _wait_for_electron_startup(
    *,
    process: ElectronDevProcess,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        return_code = process.electron_proc.poll()
        if return_code is not None:
            process.terminate()
            raise RuntimeError(f"Electron client exited early with code {return_code}")
        time.sleep(0.2)


def start(*, args: Any, ipc_endpoint: str, app_dir: str, client_root: str):
    web_client_name = str(
        getattr(args, "tauri_web_client", "") or "webclient"
    ).strip()
    web_client_root = os.path.join(app_dir, "clients", web_client_name)
    if not os.path.isdir(web_client_root):
        raise RuntimeError(f"Client directory not found: {web_client_root}")
    if not os.path.isdir(client_root):
        raise RuntimeError(f"Electron client directory not found: {client_root}")
    _ensure_electron_installed(client_root)

    dev_host = "localhost"
    dev_port = _find_free_port(host=dev_host, start_port=5174)
    dev_url = f"http://{dev_host}:{dev_port}"

    yarn = _yarn_command()
    web_env = os.environ.copy()
    web_env["VITE_A2UI_TRANSPORT"] = "native-ipc"
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

    electron_env = os.environ.copy()
    electron_env["DEMOCRAI_ELECTRON_WEB_CLIENT"] = web_client_name
    electron_env["DEMOCRAI_ELECTRON_DEV_URL"] = dev_url
    electron_env["DEMOCRAI_ELECTRON_HTTP_BASE_URL"] = _runtime_http_base_url(args)
    electron_env["DEMOCRAI_IPC_ENDPOINT"] = str(ipc_endpoint)
    electron_proc = subprocess.Popen([yarn, "dev"], cwd=client_root, env=electron_env)
    process = ElectronDevProcess(web_proc=web_proc, electron_proc=electron_proc)
    _wait_for_electron_startup(process=process)
    return process
