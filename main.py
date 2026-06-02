from __future__ import annotations

import logging
import os
import json
import signal
import socket
import sys
import threading
import time
import subprocess
import importlib
import importlib.util
import argparse

from democrai.sdk.runtime import start, stop


_LOGGER = logging.getLogger(__name__)
_IGNORED_RELOAD_SUFFIXES = (".pyc", ".pyo", ".tmp", ".swp", "~")
_CORE_CHILD_ENV = "DEMOCRAI_CORE_PROCESS"
_CORE_ENDPOINT_FD_ENV = "DEMOCRAI_CORE_ENDPOINT_FD"
_APPLICATION_RESTART_EXIT_CODE = 75


def _runner_base_dir() -> str:
    return os.path.dirname(_current_binary_path())


def _debug(message: str) -> None:
    _LOGGER.debug(message)


def _wait_for_shutdown(*, reloader=None, child_proc=None, reload_event=None) -> int:
    stop_event = threading.Event()
    exit_code = {"value": 0}
    signal_state = {"count": 0}

    def _request_shutdown(_signum, _frame) -> None:
        signal_state["count"] += 1
        if signal_state["count"] == 1:
            exit_code["value"] = 130
            stop_event.set()
        else:
            os._exit(130)

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_shutdown)

    try:
        while not stop_event.is_set():
            if reload_event is not None and reload_event.is_set():
                return _APPLICATION_RESTART_EXIT_CODE
            time.sleep(0.1)
    finally:
        stop(reloader=reloader, child_proc=child_proc)

    return exit_code["value"]


def _is_frozen_runtime() -> bool:
    return bool(
        getattr(sys, "frozen", False)
        or hasattr(sys, "nuitka_binary_dir")
        or "__compiled__" in globals()
    )


def _current_binary_path() -> str:
    candidates = []
    if _is_frozen_runtime():
        candidates.extend(
            [
                os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else None,
                os.path.abspath(sys.executable) if sys.executable else None,
            ]
        )
    else:
        candidates.append(os.path.abspath(__file__))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    return os.path.abspath(sys.argv[0] if sys.argv and sys.argv[0] else __file__)


def _server_command(
    args, *, listen_fd: int | None = None, worker_index: int | None = None
) -> list[str]:
    if _is_frozen_runtime():
        cmd = [_current_binary_path()]
    else:
        cmd = [sys.executable, _current_binary_path()]

    cmd.extend(
        [
            "--mode",
            "server",
            "--host",
            str(args.host),
            "--port",
            str(args.port),
            "--workers",
            "1",
            "--server-worker",
        ]
    )
    if args.http:
        cmd.append("--http")
    if args.dev:
        cmd.extend(["--dev", str(args.dev)])
    if listen_fd is not None:
        cmd.extend(["--listen-fd", str(listen_fd)])
    if worker_index is not None:
        cmd.extend(["--worker-index", str(worker_index)])
    return cmd


def _client_root(client_name: str) -> str:
    normalized = str(client_name or "").strip()
    return os.path.join(_runner_base_dir(), "clients", normalized)


def _client_watch_paths(client_name: str) -> tuple[str, ...]:
    return (_client_root(client_name),)


def _start_yarn_client(client_name: str):
    client_root = _client_root(client_name)
    if not os.path.isdir(client_root):
        raise RuntimeError(f"Client directory not found: {client_root}")
    proc = subprocess.Popen(["yarn", "dev"], cwd=client_root)
    return proc


def _client_launcher(client_name: str):
    module_name = f"clients.{client_name}.launcher"
    try:
        spec = importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        return None
    if spec is None:
        return None
    return importlib.import_module(module_name)


def _configure_desktop_client_runtime(args, client_name: str) -> None:
    launcher = _client_launcher(client_name)
    configure = getattr(launcher, "configure_core_args", None) if launcher else None
    if callable(configure):
        configure(args)


def _start_desktop_client(args, client_name: str, ipc_endpoint: str):
    launcher = _client_launcher(client_name)
    if launcher is not None:
        proc = launcher.start(
            args=args,
            ipc_endpoint=ipc_endpoint,
            app_dir=_runner_base_dir(),
            client_root=_client_root(client_name),
        )
        return proc
    return _start_yarn_client(client_name)


def _write_core_endpoint(endpoint: str | None) -> None:
    raw_fd = str(os.environ.get(_CORE_ENDPOINT_FD_ENV) or "").strip()
    if not raw_fd:
        return
    payload = json.dumps({"endpoint": endpoint}) + "\n"
    fd = int(raw_fd)
    with os.fdopen(fd, "w", encoding="utf-8", closefd=True) as handle:
        handle.write(payload)
        handle.flush()


def _read_core_endpoint(read_fd: int) -> str:
    with os.fdopen(read_fd, "r", encoding="utf-8", closefd=True) as handle:
        line = handle.readline()
    if not line:
        raise RuntimeError("Core process did not publish IPC endpoint")
    payload = json.loads(line)
    endpoint = str(payload.get("endpoint") or "").strip()
    if not endpoint:
        raise RuntimeError("Core process published an empty IPC endpoint")
    return endpoint


def _main_command() -> list[str]:
    if _is_frozen_runtime():
        return [_current_binary_path()]
    return [sys.executable, _current_binary_path()]


def _core_child_argv(args) -> list[str]:
    argv = [
        "--mode",
        "desktop",
        "--host",
        str(args.host),
        "--port",
        str(args.port),
    ]
    if bool(getattr(args, "http", False)):
        argv.append("--http")
    if int(getattr(args, "dev", 0) or 0):
        argv.extend(["--dev", str(args.dev)])
    return argv


def _start_desktop_core_process(args):
    read_fd, write_fd = os.pipe()
    env = os.environ.copy()
    env[_CORE_CHILD_ENV] = "1"
    env[_CORE_ENDPOINT_FD_ENV] = str(write_fd)
    proc = subprocess.Popen(
        [*_main_command(), *_core_child_argv(args)],
        env=env,
        pass_fds=(write_fd,),
        close_fds=True,
    )
    os.close(write_fd)
    try:
        endpoint = _read_core_endpoint(read_fd)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
        raise
    return proc, endpoint


def _kill_process_tree(proc) -> None:
    if proc is None:
        return
    pid = getattr(proc, "pid", None)
    try:
        if pid:
            import psutil

            root = psutil.Process(int(pid))
            children = root.children(recursive=True)
            children.sort(key=lambda child: len(child.parents()), reverse=True)
            for child in children:
                try:
                    child.kill()
                except Exception:
                    pass
            try:
                root.kill()
            except Exception:
                pass
            try:
                psutil.wait_procs([*children, root], timeout=2.0)
            except Exception:
                pass
            return
    except Exception:
        pass
    try:
        proc.kill()
        proc.wait(timeout=2.0)
    except Exception:
        pass


def _normalize_watch_path(path: str) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))


def _existing_watch_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    resolved: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = _normalize_watch_path(path)
        if normalized in seen or not os.path.exists(normalized):
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


class MainReloader:
    def __init__(
        self,
        *,
        core_paths: tuple[str, ...],
        client_paths: tuple[str, ...],
        restart_application,
        restart_client,
    ) -> None:
        self.core_paths = _existing_watch_paths(core_paths)
        self.client_paths = _existing_watch_paths(client_paths)
        self.paths = (*self.core_paths, *self.client_paths)
        self.restart_application = restart_application
        self.restart_client = restart_client
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.paths:
            _debug("[MainReloader] No valid watch paths found; disabled.")
            return
        self._thread = threading.Thread(
            target=self._run,
            name="main-reloader-thread",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            from watchfiles import watch

            for changes in watch(*self.paths, stop_event=self._stop):
                if self._stop.is_set():
                    break
                change_kind = self._change_kind(changes)
                if change_kind == "application":
                    self.restart_application()
                    return
                if change_kind == "client":
                    self.restart_client()
        except Exception as exc:
            _debug(f"[MainReloader] Watch error: {exc}")

    def _change_kind(self, changes) -> str | None:
        core_changed = False
        client_changed = False
        for _, raw_path in changes:
            path = str(raw_path)
            normalized = path.replace("\\", "/")
            if "__pycache__" in normalized or path.endswith(_IGNORED_RELOAD_SUFFIXES):
                continue
            real_path = _normalize_watch_path(path)
            if any(
                real_path == root or real_path.startswith(root + os.sep)
                for root in self.core_paths
            ):
                core_changed = True
                continue
            if any(
                real_path == root or real_path.startswith(root + os.sep)
                for root in self.client_paths
            ):
                client_changed = True

        if core_changed:
            return "application"
        if client_changed:
            return "client"
        return None


def _start_main_reloader(
    *,
    client_name: str,
    restart_application,
    restart_client,
) -> MainReloader | None:
    reloader = MainReloader(
        core_paths=(
            os.path.join(_runner_base_dir(), "democrai"),
        ),
        client_paths=_client_watch_paths(client_name),
        restart_application=restart_application,
        restart_client=restart_client,
    )
    if not reloader.paths:
        return None
    reloader.start()
    return reloader


def _start_server_reloader(*, restart_application) -> MainReloader | None:
    reloader = MainReloader(
        core_paths=(
            os.path.join(_runner_base_dir(), "democrai"),
        ),
        client_paths=(),
        restart_application=restart_application,
        restart_client=lambda: None,
    )
    if not reloader.paths:
        return None
    reloader.start()
    return reloader


def _restart_current_process() -> None:
    command = _main_command()
    os.execv(command[0], [*command, *sys.argv[1:]])


def _create_shared_listener(host: str, port: int) -> socket.socket:
    server_sock = socket.create_server((host, port), backlog=2048, reuse_port=False)
    server_sock.set_inheritable(True)
    return server_sock


def _run_server_master(args) -> int:
    if os.name == "nt":
        print("[ServerMaster] --workers>1 is not supported on Windows yet.")
        return 2

    worker_count = max(1, int(args.workers or 1))
    listener = _create_shared_listener(args.host, args.port)
    stop_event = threading.Event()
    reload_event = threading.Event()
    exit_code = {"value": 0}
    children: list[subprocess.Popen] = []
    reloader = None

    def _shutdown_children(force: bool = False) -> None:
        for child in list(children):
            try:
                if force:
                    child.kill()
                else:
                    child.terminate()
            except Exception:
                continue

        deadline = time.time() + 3.0
        for child in list(children):
            remaining = max(0.0, deadline - time.time())
            try:
                child.wait(timeout=remaining)
            except Exception:
                try:
                    child.kill()
                except Exception:
                    pass
                try:
                    child.wait(timeout=1.0)
                except Exception:
                    pass
    def _request_shutdown(_signum, _frame) -> None:
        if stop_event.is_set():
            _shutdown_children(force=True)
            os._exit(130)
        exit_code["value"] = 130
        stop_event.set()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_shutdown)

    try:
        if int(getattr(args, "dev", 0) or 0) == 1:
            reloader = _start_server_reloader(
                restart_application=reload_event.set,
            )
        print(
            f"[ServerMaster] Starting {worker_count} workers on {args.host}:{args.port}"
        )
        for worker_index in range(worker_count):
            child = subprocess.Popen(
                _server_command(
                    args,
                    listen_fd=listener.fileno(),
                    worker_index=worker_index,
                ),
                pass_fds=(listener.fileno(),),
                close_fds=True,
            )
            children.append(child)

        while not stop_event.is_set():
            if reload_event.is_set():
                exit_code["value"] = _APPLICATION_RESTART_EXIT_CODE
                stop_event.set()
                break
            for child in children:
                rc = child.poll()
                if rc is None:
                    continue
                if rc != 0 and exit_code["value"] == 0:
                    exit_code["value"] = rc
                stop_event.set()
                break
            if not stop_event.is_set():
                time.sleep(0.1)
    finally:
        if reloader is not None:
            reloader.stop()
        _shutdown_children(force=exit_code["value"] not in (0, 130))
        try:
            listener.close()
        except Exception:
            pass

    return exit_code["value"]


def _configure_runtime_args(args) -> None:
    if str(getattr(args, "mode", "") or "") != "desktop":
        return
    client_name = str(getattr(args, "client", "") or "").strip() or "qtdesktop"
    _configure_desktop_client_runtime(args, client_name)


def _run_core_child(handle) -> int:
    _write_core_endpoint(handle.endpoint)
    return _wait_for_shutdown()


def _parse_launcher_args(argv: list[str]):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", choices=["desktop", "server"], default="desktop")
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--dev", type=int, default=0)
    parser.add_argument("--client", default=None)
    parser.add_argument("--tauri-web-client", default="webclient")
    parser.add_argument("--server-worker", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    return args, unknown


def _has_runtime_command(unknown: list[str]) -> bool:
    return any(str(item).strip() and not str(item).startswith("-") for item in unknown)


def _run_desktop_mode(args) -> int:
    client_name = str(getattr(args, "client", "") or "").strip() or "qtdesktop"

    core_proc = None
    child_proc = None
    reloader = None
    ipc_endpoint = ""
    stop_event = threading.Event()
    reload_event = threading.Event()
    client_reload_event = threading.Event()
    exit_code = {"value": 0}
    signal_state = {"count": 0}

    def _restart_core_for_reload() -> None:
        nonlocal core_proc, ipc_endpoint

        if core_proc is not None:
            _kill_process_tree(core_proc)
        core_proc, ipc_endpoint = _start_desktop_core_process(args)

    def _request_application_reload() -> None:
        reload_event.set()

    def _request_client_reload() -> None:
        client_reload_event.set()

    def _request_shutdown(_signum, _frame) -> None:
        signal_state["count"] += 1
        if signal_state["count"] == 1:
            exit_code["value"] = 130
            stop_event.set()
        else:
            os._exit(130)

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_shutdown)

    try:
        core_proc, ipc_endpoint = _start_desktop_core_process(args)
        child_proc = _start_desktop_client(args, client_name, str(ipc_endpoint))

        if args.dev == 1:
            reloader = _start_main_reloader(
                client_name=client_name,
                restart_application=_request_application_reload,
                restart_client=_request_client_reload,
            )

        while not stop_event.is_set():
            if reload_event.is_set():
                reload_event.clear()
                _restart_core_for_reload()
            if client_reload_event.is_set():
                client_reload_event.clear()
                if child_proc is not None:
                    child_proc.terminate()
                    try:
                        child_proc.wait(timeout=5.0)
                    except Exception:
                        child_proc.kill()
                child_proc = _start_desktop_client(args, client_name, str(ipc_endpoint))
            core_rc = core_proc.poll() if core_proc is not None else 0
            if core_rc is not None:
                from democrai.core.runtime.lifecycle.restart import (
                    APPLICATION_RESTART_EXIT_CODE,
                )

                if int(core_rc) == APPLICATION_RESTART_EXIT_CODE:
                    _restart_core_for_reload()
                    continue
                exit_code["value"] = int(core_rc or 0)
                break
            rc = child_proc.poll() if child_proc is not None else 0
            if rc is not None:
                exit_code["value"] = int(rc or 0)
                break
            time.sleep(0.1)
        return int(exit_code["value"])
    finally:
        if reloader is not None:
            reloader.stop()
        if child_proc is not None:
            child_proc.terminate()
        if core_proc is not None:
            core_proc.terminate()
            try:
                core_proc.wait(timeout=5.0)
            except Exception:
                core_proc.kill()
        elif child_proc is not None:
            child_proc.wait(timeout=5.0)


def main() -> int:
    # Pip helper re-entry: when main process spawns itself as pip,
    # skip all bootstrap and act as pip cli.
    if "--pip-helper" in sys.argv:
        sys.argv.remove("--pip-helper")
        from pip._internal.cli.main import main as pip_main

        return int(pip_main(sys.argv[1:]) or 0)

    launcher_args, unknown = _parse_launcher_args(sys.argv[1:])

    if os.environ.get(_CORE_CHILD_ENV) != "1" and launcher_args.mode == "desktop" and not _has_runtime_command(unknown):
        _configure_runtime_args(launcher_args)
        return _run_desktop_mode(launcher_args)

    bootstrap = start(
        app_dir=_runner_base_dir(),
        configure_args=_configure_runtime_args,
    )
    if bootstrap.exit_code is not None:
        return int(bootstrap.exit_code)
    args = bootstrap.args

    if os.environ.get(_CORE_CHILD_ENV) == "1":
        return _run_core_child(bootstrap)

    if args.mode == "server":
        client_proc = None
        reloader = None
        reload_event = threading.Event()
        client_name = str(getattr(args, "client", "") or "").strip()
        if not args.server_worker and int(args.workers or 1) > 1:
            if client_name:
                client_proc = _start_yarn_client(client_name)
            try:
                rc = _run_server_master(args)
            finally:
                if client_proc is not None:
                    client_proc.terminate()
            if int(rc) == _APPLICATION_RESTART_EXIT_CODE:
                _restart_current_process()
            return rc
        try:
            if client_name:
                client_proc = _start_yarn_client(client_name)
            if not args.server_worker and int(getattr(args, "dev", 0) or 0) == 1:
                reloader = _start_server_reloader(
                    restart_application=reload_event.set,
                )
            rc = _wait_for_shutdown(
                reloader=reloader,
                child_proc=client_proc,
                reload_event=reload_event,
            )
            if int(rc) == _APPLICATION_RESTART_EXIT_CODE:
                _restart_current_process()
            return rc
        except Exception:
            if client_proc is not None:
                client_proc.terminate()
            raise

    return _run_desktop_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
