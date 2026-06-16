from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict

try:
    import psutil
except Exception:  # pragma: no cover - fallback for constrained environments
    psutil = None


@dataclass
class ManagedProcess:
    name: str
    handle: Any


class ProcessSupervisor:
    """Track runtime child processes and terminate their full trees on shutdown."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: Dict[int, ManagedProcess] = {}

    def register(self, handle: Any, name: str = "child") -> None:
        pid = self._pid_from_handle(handle)
        if pid is None or pid <= 0:
            return
        with self._lock:
            self._processes[pid] = ManagedProcess(name=name, handle=handle)

    def unregister(self, handle: Any) -> None:
        pid = self._pid_from_handle(handle)
        if pid is None:
            return
        with self._lock:
            self._processes.pop(pid, None)

    def terminate(self, handle: Any, timeout_ms: int = 1500) -> None:
        pid = self._pid_from_handle(handle)
        if pid is None:
            return

        self._terminate_tree(pid, handle, timeout_ms)
        self.unregister(handle)

    def terminate_all(self, timeout_ms: int = 1500) -> None:
        with self._lock:
            items = list(self._processes.items())

        for pid, managed in items:
            self._terminate_tree(pid, managed.handle, timeout_ms)
            self.unregister(managed.handle)

    def _terminate_tree(self, pid: int, handle: Any, timeout_ms: int) -> None:
        timeout_s = max(timeout_ms, 0) / 1000.0
        descendants = self._descendants(pid)

        self._graceful_stop(handle)
        self._wait_handle(handle, timeout_ms)
        self._terminate_psutil(descendants)

        if self._wait_pid_exit(pid, timeout_s):
            return

        self._force_stop(handle)
        self._kill_psutil(descendants)
        self._wait_handle(handle, timeout_ms)

    def _descendants(self, pid: int) -> list[Any]:
        if psutil is None:
            return []
        try:
            proc = psutil.Process(pid)
            children = proc.children(recursive=True)
            children.sort(key=lambda child: len(child.parents()), reverse=True)
            return children
        except Exception:
            return []

    def _terminate_psutil(self, procs: list[Any]) -> None:
        for proc in procs:
            try:
                proc.terminate()
            except Exception:
                continue

        if psutil is None or not procs:
            return

        try:
            psutil.wait_procs(procs, timeout=1.0)
        except Exception:
            pass

    def _kill_psutil(self, procs: list[Any]) -> None:
        for proc in procs:
            try:
                if proc.is_running():
                    proc.kill()
            except Exception:
                continue

        if psutil is None or not procs:
            return

        try:
            psutil.wait_procs(procs, timeout=1.0)
        except Exception:
            pass

    def _wait_pid_exit(self, pid: int, timeout_s: float) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not self._pid_exists(pid):
                return True
            time.sleep(0.05)
        return not self._pid_exists(pid)

    def _pid_exists(self, pid: int) -> bool:
        if psutil is not None:
            try:
                return psutil.pid_exists(pid)
            except Exception:
                pass

        try:
            from democrai.core.platform.utils.process import pid_exists

            return pid_exists(pid)
        except Exception:
            return False

    @staticmethod
    def _pid_from_handle(handle: Any) -> int | None:
        if handle is None:
            return None

        for attr in ("processId", "pid"):
            try:
                value = getattr(handle, attr)
                pid = value() if callable(value) else value
                if pid:
                    return int(pid)
            except Exception:
                continue

        return None

    @staticmethod
    def _graceful_stop(handle: Any) -> None:
        for method_name in ("terminate",):
            try:
                method = getattr(handle, method_name, None)
                if callable(method):
                    method()
                    return
            except Exception:
                continue

    @staticmethod
    def _force_stop(handle: Any) -> None:
        for method_name in ("kill",):
            try:
                method = getattr(handle, method_name, None)
                if callable(method):
                    method()
                    return
            except Exception:
                continue

    @staticmethod
    def _wait_handle(handle: Any, timeout_ms: int) -> None:
        for method_name in ("waitForFinished", "wait"):
            try:
                method = getattr(handle, method_name, None)
                if callable(method):
                    try:
                        method(timeout_ms)
                    except TypeError:
                        method(timeout_ms / 1000.0)
                    return
            except Exception:
                continue


process_supervisor = ProcessSupervisor()
