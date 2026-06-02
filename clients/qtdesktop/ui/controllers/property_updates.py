from __future__ import annotations

import os
from typing import Any

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QScrollArea, QTextEdit
from ..renderers.collection_patch import patch_collection
from .log_safety import summarize_log_value


def _literal_text(value: Any) -> str:
    if isinstance(value, dict) and "literalString" in value:
        return str(value.get("literalString") or "")
    return "" if value is None else str(value)


def _collection_items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _child_ref_id(child: Any) -> Any:
    if isinstance(child, str):
        return child
    if isinstance(child, dict):
        return child.get("id")
    return None


def _register_inline_component_tree(components: dict[str, Any], node: Any) -> None:
    if not isinstance(node, dict):
        return
    node_id = node.get("id")
    if (
        isinstance(node_id, str)
        and node_id.strip()
        and isinstance(node.get("component"), dict)
    ):
        components[node_id] = node
    children_node = node.get("children")
    if not isinstance(children_node, dict):
        return
    explicit = children_node.get("explicitList")
    if not isinstance(explicit, list):
        return
    for child in explicit:
        _register_inline_component_tree(components, child)


def _set_deep_value(target: dict[str, Any], path: str, value: Any, action: str) -> None:
    segments = [segment for segment in str(path or "").split(".") if segment]
    if not segments:
        return

    cursor: Any = target
    for segment in segments[:-1]:
        current = cursor.get(segment) if isinstance(cursor, dict) else None
        if not isinstance(current, dict):
            current = {}
            cursor[segment] = current
        cursor = current

    leaf = segments[-1]
    current_leaf = cursor.get(leaf) if isinstance(cursor, dict) else None
    if action == "append" and isinstance(current_leaf, str):
        cursor[leaf] = f"{current_leaf}{'' if value is None else str(value)}"
        return
    if action == "append" and current_leaf is None and leaf in {"text", "value"}:
        cursor[leaf] = "" if value is None else str(value)
        return
    if action in {"append", "remove", "replace", "set"} and isinstance(
        current_leaf, list
    ):
        patch = patch_collection(current_leaf, action, value)
        if patch.handled:
            cursor[leaf] = patch.items
            return
    cursor[leaf] = value


class PropertyUpdateController:
    """Coalesce and apply incremental property updates to live widgets."""

    def __init__(self, window: Any) -> None:
        """Bind update state stored on the window instance."""
        self.window = window
        self._strict_capabilities = os.getenv(
            "DEMOCRAI_UI_STRICT_CAPABILITIES", "0"
        ).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def enqueue(self, update: dict) -> None:
        """Queue property updates, merging append operations when possible."""
        if not self.is_update_allowed(update):
            return
        comp_id = update.get("componentId")
        prop = update.get("propertyName")
        value = update.get("value")
        if not comp_id:
            return

        comp_key = str(comp_id)
        prop_key = str(prop)
        key = (comp_key, prop_key)
        action = update.get("action", "set")

        pending = self.window._pending_property_updates.get(key)
        if action == "append" and prop_key in {"text", "value"}:
            append_value = "" if value is None else str(value)
            if pending and pending.get("action") == "append":
                pending["value"] = f"{pending.get('value', '')}{append_value}"
            else:
                self.window._pending_property_updates[key] = {
                    "componentId": comp_key,
                    "propertyName": prop_key,
                    "action": "append",
                    "value": append_value,
                }
        elif action in {"append", "remove", "replace"}:
            # Collection patches must preserve arrival order; coalescing by
            # component/property drops intermediate remove/replace events.
            patch_key = (comp_key, prop_key, len(self.window._pending_property_updates))
            self.window._pending_property_updates[patch_key] = {
                "componentId": comp_key,
                "propertyName": prop_key,
                "action": action,
                "value": value,
            }
        else:
            self.window._pending_property_updates[key] = {
                "componentId": comp_key,
                "propertyName": prop_key,
                "action": action,
                "value": value,
            }

        if not self.window._property_flush_timer.isActive():
            self.window._property_flush_timer.start()

    def flush(self) -> None:
        """Apply all pending updates collected during the current frame."""
        if not self.window._pending_property_updates:
            return
        updates = list(self.window._pending_property_updates.values())
        self.window._pending_property_updates.clear()
        for update in updates:
            self.apply(update)

    def apply(self, update: dict) -> None:
        """Apply one normalized update payload to the target widget."""
        if not self.is_update_allowed(update):
            return
        comp_id = update.get("componentId")
        prop = update.get("propertyName")
        value = update.get("value")
        action = update.get("action", "set")
        comp_key = str(comp_id)
        prop_key = str(prop)
        surface_id = update.get("surfaceId")

        self._update_component_model_property(
            comp_key,
            prop_key,
            value,
            action,
            str(surface_id) if surface_id else None,
        )
        widget = self.window._get_widget_by_id(comp_key)
        if not widget:
            return

        renderer = self._resolve_renderer(comp_key)
        if renderer is None:
            renderer = self._resolve_renderer_from_widget(widget)
        if renderer is not None:
            strategy = renderer.binding_strategies().get(prop_key)
            if strategy == renderer.COMPONENT and action == "set":
                self._update_component_definition_property(comp_key, prop_key, value)
                bindings = getattr(self.window, "bindings", None)
                schedule = getattr(bindings, "_schedule_component_rerender", None)
                if callable(schedule):
                    schedule(comp_key)
                    return
                rerender = getattr(
                    getattr(self.window, "_surfaces", None), "rerender_component", None
                )
                if callable(rerender):
                    rerender(comp_key)
                    return
        if renderer and renderer.apply_collection_patch(
            widget, prop_key, action, value
        ):
            return
        if action in {
            "append",
            "remove",
            "replace",
        } and self._apply_generic_collection_patch(
            widget=widget,
            comp_id=comp_key,
            prop_key=prop_key,
            action=action,
            value=value,
            renderer=renderer,
        ):
            return

        if prop_key == "dataSource":
            renderer = self.window.renderer.registry.get("List")
            if renderer and hasattr(renderer, "_populate_list"):
                if value and isinstance(value, dict):
                    renderer._populate_list(widget, value.get("data", []))
            return

        if prop_key == "text" or prop_key == "value":
            self.window._debug(
                f"Handling {prop_key} update for {comp_id} (action={action})"
            )

            current = ""
            if action == "append":
                if hasattr(widget, "text"):
                    current = widget.text()  # type: ignore
                elif hasattr(widget, "toPlainText"):
                    current = widget.toPlainText()  # type: ignore
                elif hasattr(widget, "_current_text"):
                    current = widget._current_text  # type: ignore

            text_value = _literal_text(value)
            new_val = current + text_value if action == "append" else text_value

            if hasattr(widget, "setText"):
                fmt = None
                if isinstance(widget, QLabel):
                    fmt = widget.textFormat()

                widget.setText(new_val)  # type: ignore

                if fmt is not None and isinstance(widget, QLabel):
                    widget.setTextFormat(fmt)
            elif hasattr(widget, "setPlainText"):
                widget.setPlainText(new_val)  # type: ignore
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(new_val)
            elif renderer is not None:
                renderer.update_widget_property(widget, prop_key, value)
                return

            if hasattr(widget, "_current_text"):
                widget._current_text = new_val  # type: ignore

            if isinstance(widget, (QTextEdit, QPlainTextEdit)):
                sb = widget.verticalScrollBar()
                sb.setValue(sb.maximum())
            return

        if prop_key == "scroll" and value == "bottom":
            target = widget
            while target and not isinstance(target, QScrollArea):
                target = target.parentWidget()

            if target and isinstance(target, QScrollArea):
                sb = target.verticalScrollBar()
                sb.setValue(sb.maximum())
                self.window._debug(f"Scrolled {comp_id} (or parent) to bottom")
            return

        if renderer is not None:
            try:
                renderer.update_widget_property(widget, prop_key, value)
            except Exception as exc:
                print(
                    f"[PROPERTY_TRACE] apply_exception comp_id={comp_key!r} "
                    f"property_name={prop_key!r} action={action!r} "
                    f"value={summarize_log_value(value)!r} "
                    f"error={exc!r}",
                    flush=True,
                )
                raise

    def _apply_generic_collection_patch(
        self,
        *,
        widget: Any,
        comp_id: str,
        prop_key: str,
        action: str,
        value: Any,
        renderer: Any,
    ) -> bool:
        comp_def = self._find_component_definition(comp_id)
        if not comp_def:
            return False
        component = comp_def.get("component")
        if not isinstance(component, dict) or not component:
            return False
        c_type = next(iter(component.keys()))
        props = component.get(c_type)
        if not isinstance(props, dict):
            return False

        current = props.get(prop_key)
        if not isinstance(current, list):
            return False
        if renderer is None:
            return False

        strategy = renderer.binding_strategies().get(prop_key)
        if strategy == renderer.COMPONENT:
            rerender = getattr(
                getattr(self.window, "_surfaces", None), "rerender_component", None
            )
            if callable(rerender):
                rerender(comp_id)
                return True
            return False

        renderer.update_widget_property(widget, prop_key, current)
        return True

    def _update_component_model_property(
        self,
        comp_id: str,
        prop_key: str,
        value: Any,
        action: str,
        surface_id: str | None = None,
    ) -> bool:
        found = self._find_component_definition_with_surface(comp_id, surface_id)
        if found is None:
            return False
        comp_def, surface = found
        components = surface.get("components", {})
        if not isinstance(components, dict):
            return False

        if prop_key == "scroll":
            return False

        if prop_key == "children" or prop_key.startswith("children."):
            return self._update_component_model_children(
                comp_def=comp_def,
                components=components,
                prop_key=prop_key,
                value=value,
                action=action,
            )

        component = comp_def.get("component")
        if not isinstance(component, dict) or not component:
            return False
        c_type = next(iter(component.keys()))
        props = component.get(c_type)
        if not isinstance(props, dict):
            return False

        if (
            prop_key == "dataSource"
            and action in {"append", "remove", "replace"}
            and isinstance(props.get("dataSource"), dict)
            and isinstance(props["dataSource"].get("data"), list)
        ):
            patch = patch_collection(props["dataSource"]["data"], action, value)
            if patch.handled:
                props["dataSource"]["data"] = patch.items
                return True

        _set_deep_value(props, prop_key, value, action)
        self._register_model_value_components(components, value)
        return True

    def _update_component_model_children(
        self,
        *,
        comp_def: dict[str, Any],
        components: dict[str, Any],
        prop_key: str,
        value: Any,
        action: str,
    ) -> bool:
        children_node = comp_def.setdefault("children", {})
        if not isinstance(children_node, dict):
            children_node = {}
            comp_def["children"] = children_node

        if prop_key == "children":
            current = children_node.setdefault("explicitList", [])
            if not isinstance(current, list):
                current = []
                children_node["explicitList"] = current
            patch = patch_collection(current, action, value, id_getter=_child_ref_id)
            if not patch.handled:
                return False
            children_node["explicitList"] = patch.items
            self._register_model_value_components(components, patch.items)
            return True

        nested_path = prop_key[len("children.") :]
        if nested_path == "explicitList":
            current = children_node.setdefault("explicitList", [])
            if not isinstance(current, list):
                current = []
                children_node["explicitList"] = current
            patch = patch_collection(current, action, value, id_getter=_child_ref_id)
            if not patch.handled:
                return False
            children_node["explicitList"] = patch.items
            self._register_model_value_components(components, patch.items)
            return True

        _set_deep_value(children_node, nested_path, value, action)
        self._register_model_value_components(components, value)
        return True

    def _register_model_value_components(
        self,
        components: dict[str, Any],
        value: Any,
    ) -> None:
        for item in _collection_items(value):
            _register_inline_component_tree(components, item)

    def _update_component_definition_property(
        self,
        comp_id: str,
        prop_key: str,
        value: Any,
    ) -> bool:
        comp_def = self._find_component_definition(comp_id)
        if not comp_def:
            return False
        component = comp_def.get("component")
        if not isinstance(component, dict) or not component:
            return False
        c_type = next(iter(component.keys()))
        props = component.get(c_type)
        if not isinstance(props, dict):
            return False
        props[prop_key] = value
        return True

    def _resolve_renderer(self, comp_id: str):
        comp_def = self._find_component_definition(comp_id)
        if not comp_def:
            return None
        component = comp_def.get("component")
        if not isinstance(component, dict) or not component:
            return None
        c_type = next(iter(component.keys()))
        return self.window.renderer.registry.get(c_type)

    def _resolve_renderer_from_widget(self, widget: Any):
        if widget is None or not hasattr(widget, "property"):
            return None
        comp_type = widget.property("_comp_type")
        if not comp_type:
            return None
        return self.window.renderer.registry.get(str(comp_type))

    def is_update_allowed(self, update: dict) -> bool:
        comp_id = update.get("componentId")
        prop = update.get("propertyName")
        action = update.get("action", "set")
        if not comp_id or not prop:
            return True

        comp_def = self._find_component_definition(
            str(comp_id), update.get("surfaceId")
        )
        if not comp_def:
            return True

        allowed = self._component_capabilities(comp_def)
        if not allowed:
            return not self._strict_capabilities

        prop_key = str(prop)
        action_key = str(action or "set")
        candidates = {
            f"{prop_key}.{action_key}",
            f"{prop_key}.*",
            f"*.{action_key}",
            "*.*",
        }
        if any(candidate in allowed for candidate in candidates):
            return True
        self._warn_denied(comp_id=str(comp_id), capability=f"{prop_key}.{action_key}")
        return False

    def _find_component_definition(
        self, comp_id: str, surface_id: str | None = None
    ) -> dict[str, Any] | None:
        if surface_id:
            surface = self.window.surfaces.get(str(surface_id))
            if isinstance(surface, dict):
                comp_def = surface.get("components", {}).get(comp_id)
                if isinstance(comp_def, dict):
                    return comp_def
        for surface in self.window.surfaces.values():
            comp_def = surface.get("components", {}).get(comp_id)
            if isinstance(comp_def, dict):
                return comp_def
        return None

    def _find_component_definition_with_surface(
        self, comp_id: str, surface_id: str | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if surface_id:
            surface = self.window.surfaces.get(str(surface_id))
            if isinstance(surface, dict):
                comp_def = surface.get("components", {}).get(comp_id)
                if isinstance(comp_def, dict):
                    return comp_def, surface
        for surface in self.window.surfaces.values():
            if not isinstance(surface, dict):
                continue
            comp_def = surface.get("components", {}).get(comp_id)
            if isinstance(comp_def, dict):
                return comp_def, surface
        return None

    def _component_capabilities(self, comp_def: dict[str, Any]) -> set[str]:
        component = comp_def.get("component")
        if not isinstance(component, dict) or not component:
            return set()
        c_type = next(iter(component.keys()))
        props = component.get(c_type)
        if not isinstance(props, dict):
            return set()
        caps = props.get("capabilities")
        if not isinstance(caps, list):
            return set()
        return {str(cap).strip() for cap in caps if str(cap).strip()}

    def _warn_denied(self, *, comp_id: str, capability: str) -> None:
        warn = getattr(self.window, "_warn", None)
        message = f"Blocked property update for {comp_id}: capability '{capability}' not allowed"
        if callable(warn):
            warn(message)
            return
        self.window._debug(message)
