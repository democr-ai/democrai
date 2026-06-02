from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict
from typing import Any, Callable
from urllib.parse import urlparse

from .media_ipc import (
    parse_proxy_source,
    send_media_resolve,
    send_media_stream_close,
    send_media_stream_open,
)


class MediaController:
    """Resolve proxied media URLs through the core IPC channel."""

    def __init__(self, window: Any) -> None:
        self.window = window
        self._pending: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(
            list
        )
        self._cache: dict[str, dict[str, Any]] = {}
        self._request_sources: dict[str, str] = {}
        self._request_paths: dict[str, str] = {}
        self._request_generations: dict[str, int] = {}
        self._source_requests: dict[str, str] = {}
        self._request_force_refresh: dict[str, bool] = {}
        self._request_started_at: dict[str, float] = {}
        self._pending_streams: dict[str, dict[str, Any]] = {}
        self._stream_callbacks: dict[
            str, dict[str, Callable[[dict[str, Any]], None] | None]
        ] = {}
        # source → True when denied (cleared on external_access_approved)
        self._denied_sources: set[str] = set()

    def is_proxy_source(self, source: str) -> bool:
        parsed = parse_proxy_source(str(source or ""))
        if parsed is None:
            return False
        _module_name, target_url = parsed
        raw_target = str(target_url or "").strip()
        if raw_target.startswith("/media/"):
            return False
        return True

    def request_resolution(
        self,
        source: str,
        callback: Callable[[dict[str, Any]], None],
        *,
        force_refresh: bool = False,
    ) -> bool:
        if not self.is_proxy_source(source):
            return False

        cached = self._cache.get(source)

        if cached is not None:
            if self._cache_expired(cached) or not self._cache_payload_usable(cached):
                self._cache.pop(source, None)
                cached = None
        if cached is not None:
            self._denied_sources.discard(source)
            callback(cached)
            return True

        if source in self._denied_sources and not force_refresh:
            callback({"error": "External url locked.", "error_code": "not_enabled"})
            return True

        existing_request_id = (
            None if force_refresh else self._source_requests.get(source)
        )
        if existing_request_id:
            if self._is_stale_request(existing_request_id):
                self._drop_request_state(existing_request_id)
                existing_request_id = None
            self._pending[existing_request_id].append(callback)
            return True
        if existing_request_id:
            self._pending[existing_request_id].append(callback)
            return True

        self._pending[source].append(callback)
        if len(self._pending[source]) > 1:
            return True

        parsed = parse_proxy_source(source)
        module_name, url = parsed or ("", "")
        request_id = str(uuid.uuid4())
        generation = self._current_generation()
        self._pending[request_id] = self._pending.pop(source)
        self._request_sources[request_id] = source
        self._request_paths[request_id] = self._current_path()
        self._request_generations[request_id] = generation
        self._source_requests[source] = request_id
        self._request_force_refresh[request_id] = bool(force_refresh)
        self._request_started_at[request_id] = time.time()
        send_media_resolve(
            self.window,
            request_id=request_id,
            module_name=module_name,
            url=url,
            force_refresh=force_refresh,
            client_generation=generation,
        )
        return True

    def request_stream(
        self,
        source: str,
        *,
        on_opened: Callable[[dict[str, Any]], None],
        on_chunk: Callable[[dict[str, Any]], None],
        on_end: Callable[[dict[str, Any]], None],
        on_error: Callable[[dict[str, Any]], None],
    ) -> bool:
        if not self.is_proxy_source(source):
            return False
        if source in self._denied_sources:
            on_error({"error": "External url locked.", "error_code": "not_enabled"})
            return True
        parsed = parse_proxy_source(source)
        module_name, url = parsed or ("", "")
        request_id = str(uuid.uuid4())
        generation = self._current_generation()
        self._pending_streams[request_id] = {
            "source": source,
            "path": self._current_path(),
            "generation": generation,
            "on_opened": on_opened,
            "on_chunk": on_chunk,
            "on_end": on_end,
            "on_error": on_error,
        }
        send_media_stream_open(
            self.window,
            request_id=request_id,
            module_name=module_name,
            url=url,
            client_generation=generation,
        )
        return True

    def close_stream(self, stream_id: str | None) -> None:
        if not stream_id:
            return
        self._stream_callbacks.pop(stream_id, None)
        send_media_stream_close(self.window, stream_id=stream_id)

    def clear_pending_requests(self) -> None:
        self._pending.clear()
        self._request_sources.clear()
        self._request_paths.clear()
        self._request_generations.clear()
        self._source_requests.clear()
        self._request_force_refresh.clear()
        self._request_started_at.clear()
        self._pending_streams.clear()

    def handle_media_resolved(
        self, payload: dict[str, Any], request_id: str | None
    ) -> None:
        if not request_id:
            return
        if self._is_stale_generation(payload, request_id):
            self._drop_request_state(request_id)
            return
        callbacks = self._pending.pop(request_id, [])
        source = self._request_sources.pop(request_id, "")
        self._request_paths.pop(request_id, None)
        self._request_generations.pop(request_id, None)
        self._request_force_refresh.pop(request_id, None)
        self._request_started_at.pop(request_id, None)
        if source:
            self._source_requests.pop(source, None)
        if not callbacks:
            return
        error_code = str(payload.get("error_code") or "")
        if error_code == "not_enabled" and source:
            self._denied_sources.add(source)
        if "error" not in payload and source:
            self._cache[source] = payload
        for callback in callbacks:
            try:
                callback(payload)
            except Exception:
                continue

    def handle_media_stream_opened(
        self, payload: dict[str, Any], request_id: str | None
    ) -> None:
        if not request_id:
            return
        pending = self._pending_streams.pop(request_id, None)
        if pending is None:
            return
        if self._is_stale_generation(
            payload, request_id, pending_generation=pending.get("generation")
        ):
            return
        stream_id = str(payload.get("stream_id") or "")
        if not stream_id:
            error_callback = pending.get("on_error")
            if callable(error_callback):
                error_callback({"error": "missing_stream_id"})
            return
        self._stream_callbacks[stream_id] = {
            "on_chunk": pending.get("on_chunk"),
            "on_end": pending.get("on_end"),
            "on_error": pending.get("on_error"),
        }
        opened_callback = pending.get("on_opened")
        if callable(opened_callback):
            opened_callback(payload)

    def handle_media_stream_chunk(self, payload: dict[str, Any]) -> None:
        stream_id = str(payload.get("stream_id") or "")
        callbacks = self._stream_callbacks.get(stream_id)
        if callbacks and callable(callbacks.get("on_chunk")):
            callbacks["on_chunk"](payload)

    def handle_media_stream_end(self, payload: dict[str, Any]) -> None:
        stream_id = str(payload.get("stream_id") or "")
        callbacks = self._stream_callbacks.pop(stream_id, None)
        if callbacks and callable(callbacks.get("on_end")):
            callbacks["on_end"](payload)
        self.close_stream(stream_id)

    def handle_media_stream_error(self, payload: dict[str, Any]) -> None:
        request_id = payload.get("request_id")
        if request_id is not None and request_id in self._pending_streams:
            pending = self._pending_streams.pop(str(request_id), None)
            if self._is_stale_generation(
                payload,
                str(request_id),
                pending_generation=(pending or {}).get("generation"),
            ):
                return
            if pending is not None and callable(pending.get("on_error")):
                pending["on_error"](payload)
            return
        stream_id = str(payload.get("stream_id") or "")
        callbacks = self._stream_callbacks.pop(stream_id, None)
        if callbacks and callable(callbacks.get("on_error")):
            callbacks["on_error"](payload)
        self.close_stream(stream_id)

    def handle_external_access_approved(self, module_name: str, target: str) -> None:
        """Clear denied cache for the approved resource and trigger a page reload."""
        target_value = str(target or "").strip()
        module_value = str(module_name or "").strip()

        # Clear denied_sources and cache entries matching this resource
        to_clear = []
        for source in list(self._denied_sources):
            parsed = parse_proxy_source(source)
            if parsed is not None:
                src_module, src_target = parsed
                if src_target == target_value and (
                    not module_value or src_module == module_value
                ):
                    to_clear.append(source)
            elif source == target_value:
                to_clear.append(source)
        for source in to_clear:
            self._denied_sources.discard(source)
            self._cache.pop(source, None)

        # Soft reload current page so denied images can retry
        self._trigger_page_reload()

    def _trigger_page_reload(self) -> None:
        current_path = self._current_path()
        if not current_path:
            return
        action_triggered = getattr(self.window, "action_triggered", None)
        if action_triggered is not None:
            try:
                action_triggered.emit("navigate", {"path": current_path}, "main", "")
            except Exception:
                pass

    # --- Internals ---

    def _is_stale_request(self, request_id: str, *, timeout: float = 30.0) -> bool:
        started = self._request_started_at.get(request_id)
        if started is None:
            return False
        return (time.time() - started) > timeout

    def _drop_request_state(self, request_id: str) -> None:
        self._pending.pop(request_id, None)
        source = self._request_sources.pop(request_id, "")
        self._request_paths.pop(request_id, None)
        self._request_generations.pop(request_id, None)
        self._request_force_refresh.pop(request_id, None)
        self._request_started_at.pop(request_id, None)
        if source:
            self._source_requests.pop(source, None)

    def _cache_expired(self, payload: dict[str, Any]) -> bool:
        expires_at = payload.get("cache_expires_at")
        if expires_at in (None, ""):
            return False
        try:
            return float(expires_at) <= time.time()
        except Exception:
            return False

    def _cache_payload_usable(self, payload: dict[str, Any]) -> bool:
        path = str(payload.get("path") or "")
        if not path:
            return True
        parsed = urlparse(path)
        if parsed.scheme in {"http", "https"}:
            return True
        return os.path.exists(path)

    def _current_path(self) -> str:
        store = getattr(self.window, "store", None)
        if store is None or not hasattr(store, "get"):
            return ""
        return str(store.get("/current_path", "", "global") or "")

    def _current_generation(self) -> int:
        return int(getattr(self.window, "_ui_generation", 0))

    def _is_stale_generation(
        self,
        payload: dict[str, Any],
        request_id: str,
        *,
        pending_generation: Any = None,
    ) -> bool:
        payload_generation = payload.get("client_generation")
        if isinstance(payload_generation, int):
            return payload_generation != self._current_generation()
        expected = self._request_generations.get(request_id)
        if expected is None and pending_generation is not None:
            try:
                expected = int(pending_generation)
            except Exception:
                expected = None
        if expected is None:
            return False
        return expected != self._current_generation()
