from __future__ import annotations
import re
from typing import Any, Dict
import shiboken6
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QTabWidget, QVBoxLayout, QWidget
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer, emit_action
from ...icon import get_icon, normalize_icon_name
from .common import apply_children_collection_patch


def _route_surface_id(comp_id: str, tab_id: str, pos: int) -> str:
    raw = f"{comp_id}__tab_route__{tab_id or pos}"
    return re.sub(r"[^a-zA-Z0-9_]", "_", raw)


def _tab_query_key(comp_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", str(comp_id or "tabs"))
    return f"tab_{safe}"


def _path_with_tab_query(path: str, query_key: str, tab_id: str) -> str:
    raw_path = str(path or "/")
    parsed = urlparse(raw_path)
    qs = parse_qs(parsed.query, keep_blank_values=False)
    qs[query_key] = [str(tab_id)]
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse(parsed._replace(query=new_query))


def _read_tab_from_path(path: str, query_key: str) -> str:
    parsed = urlparse(str(path or ""))
    qs = parse_qs(parsed.query, keep_blank_values=False)
    return str((qs.get(query_key) or [""])[0]).strip()


def _is_valid_widget(widget: QWidget | None) -> bool:
    try:
        return widget is not None and shiboken6.isValid(widget)
    except RuntimeError:
        return False


class TabsRenderer(BaseRenderer):
    component_type = "Tabs"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "tabs": self.COMPONENT,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        widget = QTabWidget()
        widget.setObjectName(comp_id)
        # Remove the baseline that visually connects the tab bar to the pane —
        # required for the pill/chip style to look correct.
        widget.tabBar().setDrawBase(False)

        if props.get("style", None):
            widget.setStyleSheet(qss_for_widget_style(props.get("style"), comp_id))
        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]
        widget._tab_query_key = _tab_query_key(comp_id)  # type: ignore[attr-defined]
        widget._route_map = {}  # type: ignore[attr-defined]
        widget._route_loaded = set()  # type: ignore[attr-defined]
        widget._tab_sync_guard = False  # type: ignore[attr-defined]
        widget._tab_sync_initialized = False  # type: ignore[attr-defined]
        widget._tab_change_origin = ""  # type: ignore[attr-defined]
        if not bool(getattr(widget, "_route_change_connected", False)):
            def _render_route_tab(index: int, _wgt=widget) -> None:
                if not _is_valid_widget(_wgt):
                    return
                route_map = getattr(_wgt, "_route_map", {})
                route_entry = route_map.get(index) if isinstance(route_map, dict) else None
                if not isinstance(route_entry, dict):
                    return
                route = str(route_entry.get("route") or "").strip()
                route_surface_id = str(route_entry.get("surface_id") or "").strip()
                if not route or not route_surface_id:
                    return
                loaded = getattr(_wgt, "_route_loaded", set())
                load_key = f"{route_surface_id}|{route}"
                surface_roots = getattr(_wgt._app_instance, "_surface_roots", {})
                root_id = (
                    surface_roots.get(route_surface_id)
                    if isinstance(surface_roots, dict)
                    else None
                )
                if isinstance(root_id, str) and root_id:
                    surfaces = getattr(_wgt._app_instance, "_surfaces", None)
                    render_tree = getattr(surfaces, "render_tree", None)
                    host = _wgt._app_instance._get_surface_host(route_surface_id)
                    host_layout = host.layout() if host is not None else None
                    host_empty = host_layout is None or host_layout.count() == 0
                    if (load_key not in loaded or host_empty) and callable(render_tree):
                        render_tree(route_surface_id, root_id)
                    loaded.add(load_key)
                    _wgt._route_loaded = loaded  # type: ignore[attr-defined]
                    return
                if load_key in loaded:
                    loaded.discard(load_key)
                    _wgt._route_loaded = loaded  # type: ignore[attr-defined]
                emit_action(
                    _wgt._app_instance,
                    "render_route_surface",
                    {"path": route, "surface_id": route_surface_id},
                    _wgt._surface_id,
                    _wgt._comp_id,
                )

            widget.currentChanged.connect(_render_route_tab)
            widget._render_route_tab = _render_route_tab  # type: ignore[attr-defined]
            widget._route_change_connected = True  # type: ignore[attr-defined]
        if not bool(getattr(widget, "_tab_query_sync_connected", False)):
            def _sync_query(index: int, _wgt=widget) -> None:
                if not _is_valid_widget(_wgt):
                    return
                if bool(getattr(_wgt, "_tab_sync_guard", False)):
                    return
                if not bool(getattr(_wgt, "_tab_sync_initialized", False)):
                    return
                tab_widget = _wgt.widget(index) if index >= 0 else None
                tab_name = str(tab_widget.objectName() or "").strip() if tab_widget is not None else ""
                if not tab_name:
                    return
                placeholder_prefix = f"{_wgt._comp_id}__route_tab__"
                tab_id = tab_name[len(placeholder_prefix):] if tab_name.startswith(placeholder_prefix) else tab_name
                if not tab_id:
                    return
                if str(getattr(_wgt, "_tab_change_origin", "")) != "user":
                    return
                current_path = "/"
                store = getattr(_wgt._app_instance, "store", None)
                if store is not None and hasattr(store, "get"):
                    try:
                        current_path = str(store.get("/current_path", "/", "global") or "/")
                    except Exception:
                        current_path = "/"
                next_path = _path_with_tab_query(
                    current_path,
                    str(getattr(_wgt, "_tab_query_key", "tab")),
                    str(tab_id),
                )
                if next_path == current_path:
                    _wgt._tab_change_origin = ""  # type: ignore[attr-defined]
                    return
                emit_action(
                    _wgt._app_instance,
                    "navigate",
                    {"path": next_path, "render": False},
                    _wgt._surface_id,
                    _wgt._comp_id,
                )
                _wgt._tab_change_origin = ""  # type: ignore[attr-defined]

            def _mark_user_tab_change(index: int, _wgt=widget) -> None:
                if not _is_valid_widget(_wgt):
                    return
                _wgt._tab_change_origin = "user"  # type: ignore[attr-defined]

            widget.currentChanged.connect(_sync_query)
            widget.tabBarClicked.connect(_mark_user_tab_change)
            widget._sync_query = _sync_query  # type: ignore[attr-defined]
            widget._tab_query_sync_connected = True  # type: ignore[attr-defined]

        return widget

    def before_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass

    def after_children_render(self, widget, props, surface_id, app_instance, comp_id):
        tabs_prop = props.get("tabs") or []
        if not tabs_prop:
            return
        tab_by_id: dict[str, dict] = {}
        for entry in tabs_prop:
            if not isinstance(entry, dict):
                continue
            tab_id = str(entry.get("id") or "").strip()
            if tab_id:
                tab_by_id[tab_id] = entry

        # Route tabs with matching inline children are treated as inline tabs.
        # Route-only tabs are rendered as lazy SurfaceHost containers inside the tab panel.
        placeholder_prefix = f"{comp_id}__route_tab__"
        for idx in range(widget.count() - 1, -1, -1):
            tab_widget = widget.widget(idx)
            tab_name = str(tab_widget.objectName() or "") if tab_widget is not None else ""
            if tab_name.startswith(placeholder_prefix):
                widget.removeTab(idx)
                tab_widget.deleteLater()

        existing_ids = set()
        for idx in range(widget.count()):
            tab_widget = widget.widget(idx)
            if tab_widget is None:
                continue
            tab_name = str(tab_widget.objectName() or "").strip()
            if tab_name:
                existing_ids.add(tab_name)

        route_map: dict[int, dict[str, str]] = {}
        for pos, tab in enumerate(tabs_prop):
            if not isinstance(tab, dict) or not tab.get("route"):
                continue
            tab_id = str(tab.get("id") or "").strip()
            if tab_id and tab_id in existing_ids:
                continue
            label = str(tab.get("label") or tab.get("id") or "")
            route = str(tab.get("route") or "").strip()
            route_surface_id = _route_surface_id(comp_id, tab_id, pos)
            placeholder = QFrame()
            placeholder.setObjectName(f"{placeholder_prefix}{tab_id or pos}")
            placeholder.setProperty("surface_host_id", route_surface_id)
            placeholder_layout = QVBoxLayout()
            placeholder_layout.setContentsMargins(0, 0, 0, 0)
            placeholder_layout.setSpacing(0)
            placeholder.setLayout(placeholder_layout)
            insert_pos = min(max(pos, 0), widget.count())
            widget.insertTab(insert_pos, placeholder, label)
            icon_asset = str(tab.get("icon_asset") or "").strip()
            if icon_asset:
                widget.setTabIcon(insert_pos, get_icon(icon_asset, "#94A3B8", 16))
            else:
                icon_name = normalize_icon_name(str(tab.get("icon") or "").strip())
                if icon_name:
                    widget.setTabIcon(insert_pos, get_icon(icon_name, "#94A3B8", 16))
            route_map[insert_pos] = {"route": route, "surface_id": route_surface_id}

        widget._route_map = route_map  # type: ignore[attr-defined]
        current_keys = {
            f"{entry.get('surface_id', '')}|{entry.get('route', '')}"
            for entry in route_map.values()
            if isinstance(entry, dict)
        }
        loaded = {
            key for key in getattr(widget, "_route_loaded", set()) if key in current_keys
        }
        widget._route_loaded = loaded  # type: ignore[attr-defined]

        # Apply labels/icons for inline tabs too (renderer_engine adds text but not icon).
        for idx in range(widget.count()):
            tab_widget = widget.widget(idx)
            if tab_widget is None:
                continue
            tab_name = str(tab_widget.objectName() or "").strip()
            if not tab_name:
                continue
            tab_id = tab_name
            if tab_name.startswith(placeholder_prefix):
                tab_id = tab_name[len(placeholder_prefix):]
            meta = tab_by_id.get(tab_id)
            if not isinstance(meta, dict):
                continue
            label = str(meta.get("label") or tab_id or widget.tabText(idx))
            if label:
                widget.setTabText(idx, label)
            icon_asset = str(meta.get("icon_asset") or "").strip()
            if icon_asset:
                widget.setTabIcon(idx, get_icon(icon_asset, "#94A3B8", 16))
            else:
                icon_name = normalize_icon_name(str(meta.get("icon") or "").strip())
                if icon_name:
                    widget.setTabIcon(idx, get_icon(icon_name, "#94A3B8", 16))
                else:
                    widget.setTabIcon(idx, QIcon())

        # Restore active tab from URL querystring when present.
        current_path = "/"
        store = getattr(widget._app_instance, "store", None)  # type: ignore[attr-defined]
        if store is not None and hasattr(store, "get"):
            try:
                current_path = str(store.get("/current_path", "/", "global") or "/")
            except Exception:
                current_path = "/"
        query_tab_raw = _read_tab_from_path(current_path, str(getattr(widget, "_tab_query_key", "tab")))
        matched_index = -1
        if query_tab_raw:
            for idx in range(widget.count()):
                tab_widget = widget.widget(idx)
                tab_name = str(tab_widget.objectName() or "").strip() if tab_widget is not None else ""
                if not tab_name:
                    continue
                tab_id = tab_name
                if tab_name.startswith(placeholder_prefix):
                    tab_id = tab_name[len(placeholder_prefix):]
                if tab_id == query_tab_raw:
                    matched_index = idx
                    break

            if matched_index < 0 and query_tab_raw.isdigit():
                query_index = int(query_tab_raw)
                if 0 <= query_index < widget.count():
                    matched_index = query_index

        if matched_index < 0 and widget.count() > 0:
            matched_index = 0

        if matched_index >= 0 and widget.currentIndex() != matched_index:
            widget._tab_sync_guard = True  # type: ignore[attr-defined]
            widget.setCurrentIndex(matched_index)
            widget._tab_sync_guard = False  # type: ignore[attr-defined]
        widget._tab_sync_initialized = True  # type: ignore[attr-defined]

        current_idx = widget.currentIndex()
        render_route_tab = getattr(widget, "_render_route_tab", None)
        if callable(render_route_tab) and current_idx >= 0:
            # Delay to let tab layout settle, so deferred surface mounting finds the host.
            def _render_current_route_tab(_wgt=widget) -> None:
                if not _is_valid_widget(_wgt):
                    return
                render_route_tab(_wgt.currentIndex())

            QTimer.singleShot(0, _render_current_route_tab)

    def apply_collection_patch(self, widget, prop, action, value) -> bool:
        return apply_children_collection_patch(widget, prop, action, value)
