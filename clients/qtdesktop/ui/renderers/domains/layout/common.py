from __future__ import annotations

from typing import Any, Optional
from ...collection_patch import patch_collection

def _to_px(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if not v:
            return None
        if v.endswith("%"):
            return None
        if v.endswith("px"):
            v = v[:-2].strip()
        try:
            return int(float(v))
        except ValueError:
            return None
    return None


def _child_ref_id(child: Any) -> Any:
    if isinstance(child, str):
        return child
    if isinstance(child, dict):
        return child.get("id")
    return None


def _register_inline_component_tree(
    components: dict[str, Any],
    node: Any,
) -> None:
    if not isinstance(node, dict):
        return
    node_id = node.get("id")
    if isinstance(node_id, str) and node_id.strip():
        components[node_id] = node

    children_node = node.get("children")
    if not isinstance(children_node, dict):
        return
    explicit = children_node.get("explicitList")
    if not isinstance(explicit, list):
        return
    for child in explicit:
        _register_inline_component_tree(components, child)
    return None


def _find_comp_def(
    app_instance: Any,
    comp_id: str,
    surface_id: str,
) -> tuple[dict[str, Any] | None, str]:
    surface = app_instance.surfaces.get(surface_id, {})
    components = surface.get("components", {}) if isinstance(surface, dict) else {}
    comp_def = components.get(comp_id) if isinstance(components, dict) else None
    if isinstance(comp_def, dict):
        return comp_def, surface_id

    for sid, candidate_surface in app_instance.surfaces.items():
        comps = (
            candidate_surface.get("components", {})
            if isinstance(candidate_surface, dict)
            else {}
        )
        candidate = comps.get(comp_id) if isinstance(comps, dict) else None
        if isinstance(candidate, dict):
            return candidate, str(sid)
    return None, surface_id


def apply_children_collection_patch(
    widget: Any,
    prop: str,
    action: str,
    value: Any,
) -> bool:
    if prop != "children":
        return False

    app_instance = getattr(widget, "_app_instance", None)
    comp_id = str(getattr(widget, "_comp_id", "") or widget.objectName() or "")
    surface_id = str(getattr(widget, "_surface_id", "main") or "main")
    if app_instance is None or not comp_id:
        return False

    comp_def, resolved_surface_id = _find_comp_def(app_instance, comp_id, surface_id)
    if not isinstance(comp_def, dict):
        return False

    surfaces = getattr(app_instance, "_surfaces", None)
    rerender = getattr(surfaces, "rerender_component", None)
    if callable(rerender):
        rerender(comp_id)
        return True

    # Fallback if component controller is unavailable: rerender full surface root.
    surface_roots = getattr(app_instance, "_surface_roots", {})
    root_id = surface_roots.get(resolved_surface_id)
    render_tree = getattr(surfaces, "render_tree", None)
    if callable(render_tree) and isinstance(root_id, str) and root_id:
        render_tree(resolved_surface_id, root_id)
        return True
    return False
