from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

_MISSING = object()


def _path_to_segments(path: str) -> list[str | int]:
    normalized = str(path or "").strip()
    if not normalized:
        return []
    if normalized.startswith("/"):
        parts = [part for part in normalized.strip("/").split("/") if part]
    else:
        parts = [part for part in normalized.split(".") if part]

    segments: list[str | int] = []
    for part in parts:
        if part.isdigit():
            segments.append(int(part))
        else:
            segments.append(part)
    return segments


def _segments_to_path(segments: list[str | int]) -> str:
    parts = [str(segment) for segment in segments]
    return "/" + "/".join(parts) if parts else "/"


def _flatten_paths(data: Any, prefix: list[str | int] | None = None) -> list[str]:
    prefix = list(prefix or [])
    if isinstance(data, dict):
        paths: list[str] = [_segments_to_path(prefix)] if prefix else []
        for key, value in data.items():
            paths.extend(_flatten_paths(value, [*prefix, key]))
        return paths
    if isinstance(data, list):
        paths = [_segments_to_path(prefix)] if prefix else []
        for index, value in enumerate(data):
            paths.extend(_flatten_paths(value, [*prefix, index]))
        return paths
    if not prefix:
        return ["/"]
    return [_segments_to_path(prefix)]


def _flatten_state_values(mapping: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    def visit(path: str, value: Any) -> None:
        if not isinstance(value, dict) or isinstance(value, list):
            flattened[path] = value
            return
        if not value:
            flattened[path] = value
            return
        for key, child in value.items():
            visit(_segments_to_path([*_path_to_segments(path), key]), child)

    for key, value in (mapping or {}).items():
        resolved_path = _segments_to_path(_path_to_segments(key))
        visit(resolved_path, value)
    return flattened


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = _deep_copy(value)
    return base


def _collection_items(value: Any) -> list[Any]:
    return [_deep_copy(item) for item in value] if isinstance(value, list) else [_deep_copy(value)]


def _resolve_collection_index(items: list[Any], payload: Any) -> int | None:
    if isinstance(payload, int):
        return payload if 0 <= payload < len(items) else None

    if isinstance(payload, dict):
        index_value = payload.get("index")
        if isinstance(index_value, int):
            return index_value if 0 <= index_value < len(items) else None
        target_id = payload.get("id")
    else:
        target_id = payload if isinstance(payload, str) else None

    if target_id is None:
        return None

    for index, item in enumerate(items):
        if isinstance(item, str) and item == str(target_id):
            return index
        if isinstance(item, dict) and str(item.get("id", "")) == str(target_id):
            return index
    return None


def _patch_collection(current: Any, action: str, value: Any) -> list[Any] | None:
    items = [_deep_copy(item) for item in current] if isinstance(current, list) else []
    if action == "set":
        return [_deep_copy(item) for item in value] if isinstance(value, list) else []
    if action == "append":
        return [*items, *_collection_items(value)]
    if action == "prepend":
        return [*_collection_items(value), *items]
    if action == "remove":
        index = _resolve_collection_index(items, value)
        if index is None:
            return items
        items.pop(index)
        return items
    if action == "replace":
        index = _resolve_collection_index(items, value)
        replacement = value.get("item") if isinstance(value, dict) else None
        if index is None or replacement is None:
            return items
        items[index] = _deep_copy(replacement)
        return items
    return None


class Store(QObject):
    changed = Signal(str, object)
    scoped_changed = Signal(str, str, object)

    def __init__(self, initial=None, parent=None):
        super().__init__(parent)
        self._data = {
            "global": {},
            "page": {},
        }
        self._key_signals: dict[str, _KeySignal] = {}
        if isinstance(initial, dict):
            for key, value in initial.items():
                self.set(key, value, "page")

    def _normalize_scope_and_path(
        self,
        key: str,
        scope: str = "auto",
    ) -> tuple[str, str]:
        raw_key = str(key or "").strip()
        resolved_scope = scope if scope in {"auto", "page", "global"} else "auto"

        if raw_key.startswith("$global."):
            resolved_scope = "global"
            raw_key = raw_key[len("$global.") :]
        elif raw_key.startswith("$state."):
            resolved_scope = "page" if resolved_scope == "auto" else resolved_scope
            raw_key = raw_key[len("$state.") :]

        if not raw_key:
            return resolved_scope, "/"

        if raw_key.startswith("/"):
            return resolved_scope, _segments_to_path(_path_to_segments(raw_key))

        return resolved_scope, _segments_to_path(_path_to_segments(raw_key))

    def _scopes_for_read(self, scope: str) -> list[str]:
        if scope == "global":
            return ["global"]
        if scope == "page":
            return ["page"]
        return ["page", "global"]

    def _get_from_scope(self, scope: str, path: str, default: Any = _MISSING) -> Any:
        segments = _path_to_segments(path)
        if not segments:
            return self.snapshot((scope,))

        current: Any = self._data[scope]
        for segment in segments:
            if isinstance(segment, int):
                if not isinstance(current, list) or segment >= len(current):
                    return default
                current = current[segment]
            else:
                if not isinstance(current, dict) or segment not in current:
                    return default
                current = current[segment]
        return current

    def _set_in_scope(self, scope: str, path: str, value: Any) -> None:
        segments = _path_to_segments(path)
        if not segments:
            if isinstance(value, dict):
                self._data[scope] = _deep_copy(value)
            return

        current: Any = self._data[scope]
        for index, segment in enumerate(segments[:-1]):
            next_segment = segments[index + 1]
            if isinstance(segment, int):
                if not isinstance(current, list):
                    return
                while len(current) <= segment:
                    current.append([] if isinstance(next_segment, int) else {})
                if current[segment] is None:
                    current[segment] = [] if isinstance(next_segment, int) else {}
                current = current[segment]
                continue

            if not isinstance(current, dict):
                return
            if segment not in current or current[segment] is None:
                current[segment] = [] if isinstance(next_segment, int) else {}
            current = current[segment]

        leaf = segments[-1]
        if isinstance(leaf, int):
            if not isinstance(current, list):
                return
            while len(current) <= leaf:
                current.append(None)
            current[leaf] = _deep_copy(value)
            return
        if isinstance(current, dict):
            current[leaf] = _deep_copy(value)

    def get_all(self):
        return self.snapshot(("global", "page"))

    def get(self, key: str, default: Any = None, scope: str = "page") -> Any:
        resolved_scope, path = self._normalize_scope_and_path(key, scope)
        for candidate_scope in self._scopes_for_read(resolved_scope):
            value = self._get_from_scope(candidate_scope, path, _MISSING)
            if value is not _MISSING:
                return value
        return default

    def set(self, key: str, value: Any, scope: str = "page") -> None:
        resolved_scope, path = self._normalize_scope_and_path(key, scope)
        if resolved_scope == "auto":
            resolved_scope = "page"

        current = self._get_from_scope(resolved_scope, path, _MISSING)
        if current is not _MISSING and current == value:
            return
        self._set_in_scope(resolved_scope, path, value)
        self.changed.emit(path, value)
        self.scoped_changed.emit(resolved_scope, path, value)
        self._emit_key(path, value)

    def update(self, mapping: dict[str, Any], scope: str = "page") -> None:
        for k, v in _flatten_state_values(mapping).items():
            self.set(k, v, scope)

    def patch(self, key: str, action: str, value: Any, scope: str = "page") -> None:
        resolved_scope, path = self._normalize_scope_and_path(key, scope)
        if resolved_scope == "auto":
            resolved_scope = "page"
        current = self._get_from_scope(resolved_scope, path, [])
        patched = _patch_collection(current, str(action or ""), value)
        if patched is None:
            return
        self.set(path, patched, resolved_scope)

    def merge(self, mapping: dict[str, Any], scope: str = "page") -> None:
        resolved_scope = "page" if scope == "auto" else scope
        if resolved_scope not in {"page", "global"}:
            resolved_scope = "page"
        if not isinstance(mapping, dict):
            return

        target = self._data[resolved_scope]
        _deep_merge(target, mapping)
        for path in _flatten_paths(mapping):
            self.changed.emit(path, self.get(path, None, resolved_scope))
            self.scoped_changed.emit(resolved_scope, path, self.get(path, None, resolved_scope))
            self._emit_key(path, self.get(path, None, resolved_scope))

    def clear_scope(self, scope: str) -> None:
        resolved_scope = "page" if scope == "auto" else scope
        if resolved_scope not in {"page", "global"}:
            return
        previous = self._data[resolved_scope]
        self._data[resolved_scope] = {}
        for path in _flatten_paths(previous):
            self.changed.emit(path, None)
            self.scoped_changed.emit(resolved_scope, path, None)
            self._emit_key(path, None)

    def snapshot(self, scopes: tuple[str, ...] = ("global", "page")) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for scope in scopes:
            if scope not in self._data:
                continue
            _deep_merge(merged, self._data[scope])
        return merged

    def _emit_key(self, key: str, value: Any) -> None:
        obj = self._key_signals.get(key)
        if obj is not None:
            obj.valueChanged.emit(value)

    def signal_for(self, key: str) -> Signal:
        _, key = self._normalize_scope_and_path(key, "auto")
        if key not in self._key_signals:
            self._key_signals[key] = _KeySignal(self)
        return self._key_signals[key].valueChanged


class _KeySignal(QObject):
    valueChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
