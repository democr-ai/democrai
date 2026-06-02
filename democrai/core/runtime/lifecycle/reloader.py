from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Iterable


RestartCallback = Callable[[], None]

_IGNORED_SUFFIXES = (".pyc", ".pyo", ".tmp", ".swp", "~")


def _normalize_path(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except Exception:
        return os.path.abspath(path)


def _is_within(path: str, root: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except Exception:
        normalized_path = _normalize_path(path)
        normalized_root = _normalize_path(root)
        return normalized_path == normalized_root or normalized_path.startswith(
            normalized_root + os.sep
        )


def _existing_paths(paths: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    resolved: list[str] = []
    for raw_path in paths:
        path = str(raw_path).strip()
        if not path:
            continue
        normalized = _normalize_path(path)
        if normalized in seen or not os.path.exists(normalized):
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return tuple(resolved)


class DevReloader:
    """Watch runtime extension and active client paths in dev mode."""

    def __init__(
        self,
        *,
        ctx: Any,
        module_paths: Iterable[str] = (),
        engine_paths: Iterable[str] = (),
        extractor_paths: Iterable[str] = (),
        restart_application: RestartCallback | None = None,
    ) -> None:
        self.ctx = ctx
        self.module_paths = _existing_paths(module_paths)
        self.engine_paths = _existing_paths(engine_paths)
        self.extractor_paths = _existing_paths(extractor_paths)
        self.paths = _existing_paths(
            (
                *self.module_paths,
                *self.engine_paths,
                *self.extractor_paths,
            )
        )
        self.restart_application = restart_application
        self._stop = threading.Event()
        self._changed_files: set[str] = set()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._debounce: threading.Timer | None = None

    def start(self) -> None:
        if not self.paths:
            self._log("warning", "[Reloader] No valid watch paths found; disabled.")
            return
        self._log(
            "info",
            f"[Reloader] Watching paths: {', '.join(self.paths)}",
        )
        self._thread = threading.Thread(
            target=self._run,
            name="reloader-thread",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._debounce is not None:
            self._debounce.cancel()
            self._debounce = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            from watchfiles import watch

            for changes in watch(*self.paths, stop_event=self._stop):
                if self._stop.is_set():
                    break
                for _, path in changes:
                    self._kick(path)
        except Exception as exc:
            self._log("warning", f"[Reloader] Watch error: {exc}")

    def _kick(self, path: str) -> None:
        with self._lock:
            self._changed_files.add(path)
            if self._debounce is not None:
                self._debounce.cancel()
            self._debounce = threading.Timer(0.25, self._handle_changes)
            self._debounce.daemon = True
            self._debounce.start()

    def _handle_changes(self) -> None:
        with self._lock:
            changed_files = self._changed_files
            self._changed_files = set()
            self._debounce = None
        relevant_files = self._relevant_files(changed_files)
        if not relevant_files:
            self._log(
                "info",
                "[Reloader] Ignoring changes because only cache/temp files were detected.",
            )
            return

        self._log("info", f"[Reloader] Changes detected in {len(relevant_files)} files.")
        for path in relevant_files:
            self._log("info", f"  - Detected change: {path}")

        if any(self._in_roots(path, self.engine_paths) for path in relevant_files):
            self._restart_application("[Reloader] Engine change detected.")
            return
        if any(self._in_roots(path, self.extractor_paths) for path in relevant_files):
            self._restart_application("[Reloader] Extractor change detected.")
            return

        module_changes = [
            path for path in relevant_files if self._in_roots(path, self.module_paths)
        ]

        if module_changes:
            self._reload_modules()
            self._broadcast_hot_reload()
            return

    def _relevant_files(self, changed_files: Iterable[str]) -> list[str]:
        relevant: list[str] = []
        for file_path in changed_files:
            path = _normalize_path(file_path)
            normalized = path.replace("\\", "/")
            if "__pycache__" in normalized or path.endswith(_IGNORED_SUFFIXES):
                continue
            relevant.append(path)
        return relevant

    @staticmethod
    def _in_roots(path: str, roots: Iterable[str]) -> bool:
        return any(_is_within(path, root) for root in roots)

    def _reload_modules(self) -> None:
        modules = getattr(self.ctx, "modules", None)
        reload_all = getattr(modules, "reload_all_modules", None)
        if not callable(reload_all):
            self._log("warning", "[Reloader] Module manager is not available.")
            return
        self._log("info", "[Reloader] Module change detected. Performing soft reload.")
        reload_all()

    def _broadcast_hot_reload(self) -> None:
        network = getattr(self.ctx, "network", None)
        raw_buses = getattr(network, "buses", None)
        buses = list(raw_buses) if raw_buses is not None else []
        if not buses:
            self._log("warning", "[Reloader] No bus available for hot_reload signal.")
            return
        self._log("info", "[Reloader] Broadcasting hot_reload signal.")
        for bus in buses:
            broadcast = getattr(bus, "broadcast", None)
            if callable(broadcast):
                broadcast({"type": "hot_reload"})

    def _restart_application(self, reason: str) -> None:
        if self.restart_application is None:
            self._log("warning", f"{reason} Application restart is not configured.")
            return
        self._log("warning", f"{reason} Restarting process.")
        self.restart_application()

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.ctx, "logger", None)
        method = getattr(logger, level, None)
        if callable(method):
            method(message)
            return
        print(message, file=sys.stderr)


def create_dev_reloader(
    *,
    ctx: Any,
    module_paths: Iterable[str] = (),
    engine_paths: Iterable[str] = (),
    extractor_paths: Iterable[str] = (),
    restart_application: RestartCallback | None = None,
) -> DevReloader | None:
    reloader = DevReloader(
        ctx=ctx,
        module_paths=module_paths,
        engine_paths=engine_paths,
        extractor_paths=extractor_paths,
        restart_application=restart_application,
    )
    if not reloader.paths:
        return None
    reloader.start()
    return reloader
