from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import shiboken6
from PySide6.QtCore import QObject, QTimer

from .bindings_logic import (
    collect_data_paths,
    collect_component_fallback_paths,
    collect_specs,
    collect_watch_paths,
    extract_component_props,
    extract_inline_store_key,
    normalize_spec,
    resolve_spec,
    resolve_string,
    with_action_cache,
)

_MISSING = object()


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        return json.dumps(str(value))


def _normalize_data_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return "/"
    return text if text.startswith("/") else f"/{text.lstrip('/')}"


@dataclass(frozen=True)
class BoundSpec:
    kind: str
    value: Any = None
    path: str | None = None
    scope: str = "auto"
    default: Any = None
    name: str | None = None
    args: dict[str, Any] | None = None
    cache_scope: str = "page"
    cache_path: str | None = None


class BindingController(QObject):
    """Resolve and observe component bound values with backward compatibility."""

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window = window
        self._pending_actions: dict[str, dict[str, Any]] = {}
        self._page_epoch = 0
        self._pending_rerenders: set[str] = set()
        self._pending_component_rerenders: set[str] = set()
        self._data_bindings: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._rerender_timer = QTimer(self)
        self._rerender_timer.setSingleShot(True)
        self._rerender_timer.setInterval(0)
        self._rerender_timer.timeout.connect(self._flush_rerenders)

    def on_page_scope_reset(self) -> None:
        self._page_epoch += 1
        stale = [
            request_id
            for request_id, meta in self._pending_actions.items()
            if meta.get("cache_scope") == "page"
        ]
        for request_id in stale:
            self._pending_actions.pop(request_id, None)
        self._pending_rerenders.clear()
        self._pending_component_rerenders.clear()
        self._data_bindings.clear()
        if self._rerender_timer.isActive() and hasattr(self._rerender_timer, "stop"):
            self._rerender_timer.stop()

    def resolve_value(self, data: Any, item: dict[str, Any] | None = None) -> Any:
        return self.resolve_value_for_surface(data, None, item)

    def resolve_value_for_surface(
        self,
        data: Any,
        surface_id: str | None,
        item: dict[str, Any] | None = None,
        *,
        allow_implicit_path: bool = True,
    ) -> Any:
        spec = self.normalize_spec(data, allow_implicit_path=allow_implicit_path)
        if spec is not None:
            return self._resolve_spec(spec, item, surface_id)

        if isinstance(data, str):
            return self._resolve_string(data, item, surface_id)
        if isinstance(data, dict):
            return {
                key: self.resolve_value_for_surface(value, surface_id, item)
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [self.resolve_value_for_surface(value, surface_id, item) for value in data]
        return data

    def prepare_component_bindings(
        self,
        comp_def: dict[str, Any],
        *,
        surface_id: str,
        comp_id: str,
        item: dict[str, Any] | None = None,
    ) -> None:
        for spec in self._collect_specs(comp_def):
            if spec.kind != "action":
                continue
            action_spec = self._with_action_cache(spec, surface_id, comp_id, item)
            self._ensure_action_request(action_spec, surface_id, item)

    def bind_component(
        self,
        widget: QObject,
        *,
        surface_id: str,
        comp_id: str,
        comp_def: dict[str, Any],
        renderer: Any,
        item: dict[str, Any] | None = None,
    ) -> None:
        if widget is not None and not shiboken6.isValid(widget):
            return

        props = self._extract_component_props(comp_def)
        policies = renderer.binding_strategies() if renderer is not None else {}
        handled_props: set[str] = set()

        for prop_name, strategy in policies.items():
            if prop_name not in props:
                continue

            prop_value = props[prop_name]
            paths = self._collect_watch_paths(
                prop_value,
                surface_id=surface_id,
                comp_id=comp_id,
                item=item,
            )
            data_paths = self._collect_data_paths(prop_value)
            if not paths and not data_paths:
                continue

            handled_props.add(prop_name)

            if strategy == getattr(renderer, "PROPERTY", "property"):
                callback = lambda prop=prop_name, raw=prop_value: self._apply_property_binding(
                    widget,
                    renderer,
                    prop,
                    raw,
                    item,
                    surface_id,
                )
                if paths:
                    self.window.binder.bind_many(
                        sorted(paths),
                        callback,
                        owner=widget,
                        immediate=False,
                    )
                for path in data_paths:
                    self._bind_data_path(
                        surface_id,
                        path,
                        {
                            "kind": "property",
                            "widget": widget,
                            "renderer": renderer,
                            "prop": prop_name,
                            "raw": prop_value,
                            "item": item,
                        },
                    )
                continue

            if strategy == getattr(renderer, "COMPONENT", "component"):
                callback = lambda cid=comp_id: self._schedule_component_rerender(cid)
                if paths:
                    self.window.binder.bind_many(
                        sorted(paths),
                        callback,
                        owner=widget,
                        immediate=False,
                    )
                for path in data_paths:
                    self._bind_data_path(
                        surface_id,
                        path,
                        {
                            "kind": "component",
                            "widget": widget,
                            "comp_id": comp_id,
                        },
                    )
                continue

            callback = lambda: self._schedule_rerender(surface_id)
            if paths:
                self.window.binder.bind_many(
                    sorted(paths),
                    callback,
                    owner=widget,
                    immediate=False,
                )
            for path in data_paths:
                self._bind_data_path(
                    surface_id,
                    path,
                    {
                        "kind": "surface",
                        "widget": widget,
                        "surface_id": surface_id,
                    },
                )

        fallback_paths = self._collect_component_fallback_paths(
            comp_def,
            surface_id=surface_id,
            comp_id=comp_id,
            item=item,
            handled_props=handled_props,
            renderer=renderer,
        )
        if not fallback_paths:
            return

        self.window.binder.bind_many(
            sorted(fallback_paths),
            lambda: self._schedule_rerender(surface_id),
            owner=widget,
            immediate=False,
        )

    def handle_data_model_update(self, surface_id: str, data: dict[str, Any]) -> bool:
        from ..state_store import _flatten_paths

        changed_paths = {_normalize_data_path(path) for path in _flatten_paths(data)}
        if not changed_paths:
            return False

        handled = False
        entries: list[dict[str, Any]] = []
        for (bound_surface_id, path), bound_entries in list(self._data_bindings.items()):
            if bound_surface_id != surface_id:
                continue
            if path not in changed_paths:
                continue
            entries.extend(bound_entries)

        for entry in entries:
            widget = entry.get("widget")
            if widget is not None and not shiboken6.isValid(widget):
                continue
            handled = True
            kind = entry.get("kind")
            if kind == "property":
                self._apply_property_binding(
                    widget,
                    entry.get("renderer"),
                    str(entry.get("prop") or ""),
                    entry.get("raw"),
                    entry.get("item"),
                    surface_id,
                )
            elif kind == "component":
                self._schedule_component_rerender(str(entry.get("comp_id") or ""))
            elif kind == "surface":
                self._schedule_rerender(str(entry.get("surface_id") or surface_id))
            elif kind == "callback":
                callback = entry.get("callback")
                if callable(callback):
                    callback()

        return handled

    def handle_action_result(self, payload: dict[str, Any]) -> None:
        request_id = str(payload.get("requestId", "")).strip()
        meta = self._pending_actions.pop(request_id, None)
        if meta is None:
            return

        if meta.get("cache_scope") == "page" and meta.get("page_epoch") != self._page_epoch:
            return

        value = payload.get("value", meta.get("default"))
        if payload.get("ok") is False:
            value = meta.get("default")

        cache_path = meta.get("cache_path")
        cache_scope = meta.get("cache_scope", "page")
        if cache_path:
            self.window.store.set(cache_path, value, cache_scope)

    def normalize_spec(
        self,
        value: Any,
        *,
        allow_implicit_path: bool = True,
    ) -> BoundSpec | None:
        return normalize_spec(
            value,
            BoundSpec,
            allow_implicit_path=allow_implicit_path,
        )

    def _collect_specs(self, data: Any) -> list[BoundSpec]:
        return collect_specs(self, data)

    def _collect_watch_paths(
        self,
        data: Any,
        *,
        surface_id: str,
        comp_id: str,
        item: dict[str, Any] | None = None,
    ) -> set[str]:
        return collect_watch_paths(
            self,
            data,
            surface_id=surface_id,
            comp_id=comp_id,
            item=item,
        )

    def _collect_data_paths(self, data: Any) -> set[str]:
        return collect_data_paths(self, data)

    def _extract_component_props(self, comp_def: dict[str, Any]) -> dict[str, Any]:
        return extract_component_props(comp_def)

    def _collect_component_fallback_paths(
        self,
        comp_def: dict[str, Any],
        *,
        surface_id: str,
        comp_id: str,
        item: dict[str, Any] | None,
        handled_props: set[str],
        renderer: Any,
    ) -> set[str]:
        return collect_component_fallback_paths(
            self,
            comp_def,
            surface_id=surface_id,
            comp_id=comp_id,
            item=item,
            handled_props=handled_props,
            renderer=renderer,
        )

    def _apply_property_binding(
        self,
        widget: QObject,
        renderer: Any,
        prop_name: str,
        raw_value: Any,
        item: dict[str, Any] | None,
        surface_id: str | None = None,
    ) -> None:
        if widget is not None and not shiboken6.isValid(widget):
            return
        resolved_surface_id = surface_id or getattr(widget, "_surface_id", None)
        resolved = self.resolve_value_for_surface(raw_value, resolved_surface_id, item)
        renderer.update_widget_property(widget, prop_name, resolved)

    def _bind_data_path(
        self,
        surface_id: str,
        path: str,
        entry: dict[str, Any],
    ) -> None:
        key = (str(surface_id or "main"), _normalize_data_path(path))
        self._data_bindings.setdefault(key, []).append(entry)

    def _resolve_spec(
        self,
        spec: BoundSpec,
        item: dict[str, Any] | None,
        surface_id: str | None = None,
    ) -> Any:
        return resolve_spec(self, spec, item, surface_id)

    def _resolve_string(
        self,
        data: str,
        item: dict[str, Any] | None,
        surface_id: str | None = None,
    ) -> Any:
        return resolve_string(self, data, item, surface_id)

    def _extract_inline_store_key(self, value: str, item: dict[str, Any] | None) -> str | None:
        return extract_inline_store_key(value, item)

    def _with_action_cache(
        self,
        spec: BoundSpec,
        surface_id: str,
        comp_id: str,
        item: dict[str, Any] | None,
    ) -> BoundSpec:
        return with_action_cache(spec, item, stable_json=_stable_json, bound_spec_cls=BoundSpec)

    def _ensure_action_request(
        self,
        spec: BoundSpec,
        surface_id: str | None,
        item: dict[str, Any] | None,
    ) -> None:
        cache_path = spec.cache_path or "/"
        if self.window.store.get(cache_path, _MISSING, spec.cache_scope) is _MISSING:
            self.window.store.set(cache_path, spec.default, spec.cache_scope)

        resolved_args = self.resolve_value_for_surface(spec.args or {}, surface_id, item)
        fingerprint = _stable_json({"name": spec.name, "args": resolved_args, "cache_path": cache_path})
        pending_fingerprint = next(
            (
                request_id
                for request_id, meta in self._pending_actions.items()
                if meta.get("fingerprint") == fingerprint
            ),
            None,
        )
        if pending_fingerprint is not None:
            return

        request_id = str(uuid.uuid4())
        self._pending_actions[request_id] = {
            "binding_id": cache_path,
            "cache_path": cache_path,
            "cache_scope": spec.cache_scope,
            "default": spec.default,
            "page_epoch": self._page_epoch,
            "fingerprint": fingerprint,
        }
        self.window._action.send_binding_action(
            request_id=request_id,
            binding_id=cache_path,
            name=spec.name or "",
            context=resolved_args if isinstance(resolved_args, dict) else {},
        )

    def _rerender_surface(self, surface_id: str) -> None:
        root_id = self.window._surface_roots.get(surface_id)
        if not root_id:
            return
        self.window._surfaces.render_tree(surface_id, root_id)

    def _schedule_rerender(self, surface_id: str) -> None:
        self._pending_rerenders.add(surface_id)
        if not self._rerender_timer.isActive():
            self._rerender_timer.start()

    def _schedule_component_rerender(self, comp_id: str) -> None:
        self._pending_component_rerenders.add(comp_id)
        if not self._rerender_timer.isActive():
            self._rerender_timer.start()

    def _flush_rerenders(self) -> None:
        pending_components = list(self._pending_component_rerenders)
        self._pending_component_rerenders.clear()
        for comp_id in pending_components:
            self.window._surfaces.rerender_component(comp_id)

        pending = list(self._pending_rerenders)
        self._pending_rerenders.clear()
        for surface_id in pending:
            self._rerender_surface(surface_id)

    def read_surface_data(
        self,
        surface_id: str | None,
        path: str,
        default: Any = None,
    ) -> Any:
        if not surface_id:
            return default
        surface = self.window.surfaces.get(surface_id, {})
        data_model = surface.get("data_model", {}) if isinstance(surface, dict) else {}
        if not isinstance(data_model, dict):
            return default

        keys = [key for key in str(path or "").strip("/").split("/") if key]
        value: Any = data_model
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        return default if value is None else value
