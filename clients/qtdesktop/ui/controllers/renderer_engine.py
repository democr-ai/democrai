from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import types
from typing import Any, Optional, Set

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QBoxLayout,
    QGridLayout,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..renderers.base import BaseRenderer, emit_action


def _discover_submodules(package_name: str, *, recursive: bool) -> list[str]:
    modules: set[str] = set()
    package = importlib.import_module(package_name)
    for _name, obj in inspect.getmembers(package):
        if isinstance(obj, types.ModuleType) and obj.__name__.startswith(package_name):
            if obj.__name__ != package_name:
                modules.add(obj.__name__)
    if not hasattr(package, "__path__"):
        return sorted(modules)
    iterator = (
        pkgutil.walk_packages(package.__path__, f"{package_name}.")
        if recursive
        else pkgutil.iter_modules(package.__path__, f"{package_name}.")
    )
    for info in iterator:
        modules.add(info.name)
    return sorted(modules)


class RendererEngine:
    def __init__(self, host: Any) -> None:
        self.host = host

    def load_renderers(self) -> None:
        package_root = (__package__ or "qtdesktop.ui.controllers").split(".ui.", 1)[0]
        package = f"{package_root}.ui.renderers.domains"

        renderer_modules = _discover_submodules(package, recursive=True)

        for module_name in renderer_modules:
            if module_name.endswith(".base"):
                continue

            try:
                module = importlib.import_module(module_name)
            except Exception as e:
                self.host._error(f"Error importing renderer module {module_name}: {e}")
                continue

            for attr_name in dir(module):
                cls = getattr(module, attr_name)
                if (
                    inspect.isclass(cls)
                    and issubclass(cls, BaseRenderer)
                    and cls is not BaseRenderer
                ):
                    comp_type = getattr(cls, "component_type", None)
                    if comp_type:
                        try:
                            self.host.registry[comp_type] = cls()
                            self.host._debug(
                                f"Registered Renderer: "
                                f"{comp_type} -> {module_name}.{attr_name}"
                            )
                        except Exception as e:
                            self.host._error(
                                f"Error instantiating renderer "
                                f"{module_name}.{attr_name}: {e}"
                            )

    def resolve_bindings(
        self,
        data: Any,
        item: Optional[dict] = None,
        property_name: Optional[str] = None,
        surface_id: Optional[str] = None,
    ) -> Any:
        bindings = getattr(self.host, "bindings", None)
        if isinstance(data, str):
            if bindings is not None:
                if hasattr(bindings, "resolve_value_for_surface"):
                    return bindings.resolve_value_for_surface(data, surface_id, item)
                if hasattr(bindings, "resolve_value"):
                    return bindings.resolve_value(data, item)
            return data
        if isinstance(data, dict):
            if bindings is not None and hasattr(bindings, "normalize_spec"):
                try:
                    allow_implicit_path = property_name != "context"
                    if bindings.normalize_spec(
                        data,
                        allow_implicit_path=allow_implicit_path,
                    ) is not None:
                        return bindings.resolve_value_for_surface(
                            data,
                            surface_id,
                            item,
                            allow_implicit_path=allow_implicit_path,
                        )
                except Exception:
                    return data
            return {
                k: (
                    v
                    if k in {"children", "dataSource"}
                    else self.resolve_bindings(v, item, k, surface_id)
                )
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [self.resolve_bindings(i, item, property_name, surface_id) for i in data]
        return data

    def render_component(
        self,
        component_data: dict,
        surface_id: str,
        app_instance=None,
        item: Optional[dict] = None,
    ):
        if not isinstance(component_data.get("component"), dict):
            return None

        c_type = list(component_data["component"].keys())[0]
        renderer = self.host.registry.get(c_type)
        if not renderer:
            self.host._debug(f"Unknown component type: {c_type}")
            return None

        runtime = app_instance or self.host
        if not renderer.is_component_visible(
            component_data,
            runtime,
            item,
            surface_id=surface_id,
        ):
            return None

        props = component_data["component"][c_type]
        return renderer.render(
            props,
            surface_id,
            runtime,
            comp_id=component_data.get("id", "unknown"),
        )

    def build_widget(
        self,
        surface_id: str,
        surfaces: dict,
        comp_id: str | None = None,
        comp_def: dict | None = None,
        item: Optional[dict] = None,
        app_instance: Any = None,
        seen_dialogs: Optional[Set[str]] = None,
        wrap_visibility: bool = True,
    ):
        if comp_id and not comp_def:
            comp_def = surfaces.get(surface_id, {}).get("components", {}).get(comp_id)

        if not comp_def:
            self.host._debug(
                f"build_widget failed: component {comp_id} not found in surface {surface_id}"
            )
            return None

        c_type = list(comp_def["component"].keys())[0]
        renderer = self.host.registry.get(c_type)
        comp_id = comp_id or comp_def.get("id", "unknown")

        if c_type == "Dialog" and seen_dialogs is not None:
            seen_dialogs.add(comp_id)

        raw_props = comp_def["component"][c_type]
        if wrap_visibility and self._needs_visibility_host(comp_def):
            return self._build_visibility_host(
                surface_id,
                surfaces,
                comp_id,
                comp_def,
                item,
                app_instance,
                seen_dialogs,
            )

        bindings = getattr(self.host, "bindings", None)
        if bindings is not None:
            bindings.prepare_component_bindings(
                comp_def,
                surface_id=surface_id,
                comp_id=comp_id,
                item=item,
            )
        resolved_comp_def = self.resolve_bindings(comp_def, item, surface_id=surface_id)

        widget = self.render_component(
            resolved_comp_def, surface_id, app_instance or self.host, item=item
        )
        if not widget or not renderer:
            return widget

        renderer.configure_widget(
            widget,
            raw_props,
            resolved_comp_def["component"][c_type],
            app_instance or self.host,
            comp_id,
        )

        # Handle generic auto-refresh if enabled for this component
        auto_refresh = resolved_comp_def["component"][c_type].get("auto_refresh")
        on_refresh = resolved_comp_def["component"][c_type].get("on_refresh")
        # Fallback for DataTable which uses on_page_change historically
        if not on_refresh and c_type == "DataTable":
            on_refresh = resolved_comp_def["component"][c_type].get("on_page_change")

        if auto_refresh and on_refresh and widget:
            timer = QTimer(widget)
            timer.setInterval(int(auto_refresh) * 1000)

            def _tick(_w=widget, _a=on_refresh, _id=comp_id, _t=timer):
                # Stop and cleanup if the widget is no longer active/visible
                if not _w.isVisible() or _w.window() is None:
                    _t.stop()
                    return

                # For DataTable, we might need extra context (page, filters)
                # But for a generic refresh, we just emit the action
                ctx = dict(_a.get("context", {}))
                if c_type == "DataTable":
                    ctx.update({
                        "page": getattr(_w, "_dt_page", 0),
                        "pageSize": getattr(_w, "_dt_page_size", 25),
                        "filters": getattr(_w, "_dt_filters", {}),
                        "autoRefresh": True,
                        "tableId": _id,
                    })

                emit_action(
                    app_instance or self.host,
                    _a["name"],
                    ctx,
                    surface_id,
                    _id,
                )

            timer.timeout.connect(_tick)
            timer.start()

        if bindings is not None:
            bindings.bind_component(
                widget,
                surface_id=surface_id,
                comp_id=comp_id,
                comp_def=comp_def,
                renderer=renderer,
                item=item,
            )

        comp_props = resolved_comp_def["component"][c_type]
        self.populate_children(
            widget,
            comp_props,
            raw_props,
            resolved_comp_def,
            surface_id,
            surfaces,
            item,
            app_instance,
            seen_dialogs,
            renderer,
            comp_id,
        )
        return widget

    def _needs_visibility_host(self, comp_def: dict[str, Any]) -> bool:
        props = self._extract_props(comp_def)
        return any(
            key in props or key in comp_def
            for key in ("show_if", "hide_if", "required_permissions", "permissions")
        )

    def _extract_props(self, comp_def: dict[str, Any]) -> dict[str, Any]:
        component = comp_def.get("component")
        if not isinstance(component, dict) or not component:
            return {}
        c_type = next(iter(component.keys()))
        props = component.get(c_type)
        return props if isinstance(props, dict) else {}

    def _clear_visibility_host(self, host: QWidget) -> None:
        layout = host.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget() if item is not None else None
            if child is not None:
                child.setParent(None)
                child.deleteLater()

    def _build_visibility_host(
        self,
        surface_id: str,
        surfaces: dict,
        comp_id: str,
        comp_def: dict,
        item: Optional[dict],
        app_instance: Any,
        seen_dialogs: Optional[Set[str]],
    ) -> QWidget:
        host = QWidget()
        host.setObjectName(f"{comp_id}_wrap")
        host.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        def remount() -> None:
            self._clear_visibility_host(host)
            child = self.build_widget(
                surface_id,
                surfaces,
                comp_def=comp_def,
                item=item,
                app_instance=app_instance,
                seen_dialogs=seen_dialogs,
                wrap_visibility=False,
            )
            if child is not None:
                layout.addWidget(child)

        remount()
        self._bind_visibility_host(
            host,
            surface_id,
            comp_id,
            comp_def,
            item,
            remount,
            app_instance or self.host,
        )
        return host

    def _bind_visibility_host(
        self,
        host: QWidget,
        surface_id: str,
        comp_id: str,
        comp_def: dict,
        item: Optional[dict],
        callback: Any,
        runtime: Any,
    ) -> None:
        bindings = getattr(runtime, "bindings", None) or getattr(self.host, "bindings", None)
        binder = getattr(runtime, "binder", None)
        if bindings is None or binder is None:
            return

        props = self._extract_props(comp_def)
        paths: set[str] = set()
        data_paths: set[str] = set()
        for key in ("show_if", "hide_if"):
            rule = props.get(key, comp_def.get(key))
            if rule is not None:
                paths.update(
                    bindings._collect_watch_paths(
                        rule,
                        surface_id=surface_id,
                        comp_id=comp_id,
                        item=item,
                    )
                )
                if hasattr(bindings, "_collect_data_paths"):
                    data_paths.update(bindings._collect_data_paths(rule))

        required = (
            props.get("required_permissions")
            or comp_def.get("required_permissions")
            or comp_def.get("permissions")
            or props.get("permissions")
        )
        if required:
            paths.update({"/auth/role", "/auth/permissions"})

        if paths:
            binder.bind_many(sorted(paths), callback, owner=host, immediate=False)
        if data_paths and hasattr(bindings, "_bind_data_path"):
            for path in data_paths:
                bindings._bind_data_path(
                    surface_id,
                    path,
                    {
                        "kind": "callback",
                        "widget": host,
                        "callback": callback,
                    },
                )

    def populate_children(
        self,
        widget: QWidget,
        comp_props: dict,
        raw_props: dict,
        resolved_comp_def: dict,
        surface_id: str,
        surfaces: dict,
        item: Optional[dict],
        app_instance: Any,
        seen_dialogs: set[str] | None,
        renderer: BaseRenderer,
        comp_id: str,
    ):
        children_node = raw_props.get("children")
        if not children_node:
            children_node = resolved_comp_def.get("children") or comp_props.get(
                "children", {}
            )

        renderer.before_children_render(
            widget, comp_props, surface_id, self.host, comp_id
        )

        if isinstance(children_node, dict) and "explicitList" in children_node:
            children = children_node["explicitList"]
            layout = widget.layout()

            for child in children:
                if isinstance(child, dict):
                    child_widget = self.build_widget(
                        surface_id,
                        surfaces,
                        comp_def=child,
                        item=item,
                        app_instance=app_instance,
                        seen_dialogs=seen_dialogs,
                    )
                    child_def = child
                else:
                    child_widget = self.build_widget(
                        surface_id,
                        surfaces,
                        comp_id=child,
                        item=item,
                        app_instance=app_instance,
                        seen_dialogs=seen_dialogs,
                    )
                    child_def = (
                        surfaces.get(surface_id, {}).get("components", {}).get(child)
                    )
                    if child_def is None:
                        continue

                if child_widget and child_def:
                    child_type = list(child_def["component"].keys())[0]
                    if child_type == "Dialog":
                        continue
                    
                    if hasattr(renderer, "add_child_to_widget"):
                        renderer.add_child_to_widget(widget, child_widget)
                        continue

                    child_props = child_def["component"][child_type]
                    stretch = child_props.get("stretch", 0)
                    if isinstance(stretch, bool):
                        stretch = 1 if stretch else 0

                    if layout:
                        if isinstance(layout, QGridLayout):
                            # This is the problematic branch we just avoided with add_child_to_widget
                            layout.addWidget(child_widget)
                        elif isinstance(layout, QBoxLayout):
                            layout.addWidget(child_widget, stretch)
                        else:
                            layout.addWidget(child_widget)
                    elif isinstance(widget, QScrollArea):
                        cw = widget.widget()
                        if cw:
                            cw_layout = cw.layout()
                            if cw_layout:
                                cw_layout.addWidget(child_widget)
                    elif hasattr(widget, "addWidget") or isinstance(widget, QTabWidget):
                        if isinstance(widget, QTabWidget):
                            tabs = comp_props.get("tabs")
                            if not isinstance(tabs, list):
                                tabs = []
                            cid = child_def.get("id")
                            label = next(
                                (
                                    t.get("label")
                                    for t in tabs
                                    if isinstance(t, dict) and t.get("id") == cid
                                ),
                                cid,
                            )
                            widget.addTab(child_widget, str(label))
                        else:
                            widget.addWidget(child_widget)
                        if hasattr(widget, "indexOf") and hasattr(
                            widget, "setStretchFactor"
                        ):
                            idx = widget.indexOf(child_widget)
                            widget.setStretchFactor(idx, stretch)

        renderer.after_children_render(
            widget, raw_props.copy(), surface_id, self.host, comp_id
        )
        renderer.apply_post_children_effects(
            widget,
            comp_props,
            surface_id=surface_id,
            comp_id=comp_id,
        )
