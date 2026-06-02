from __future__ import annotations

from democrai.sdk.auth import permission_required
from uuid import uuid4

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.decorators import action


GRID_ID = "components_complex_grid_zone"
TOGGLE_ID = "components_complex_grid_edit_toggle"

INITIAL_WIDGETS = [
    {"id": "components_complex_grid_widget_1", "coords": [0, 0], "size": "square"},
    {"id": "components_complex_grid_widget_2", "coords": [0, 1], "size": "rect_h"},
    {"id": "components_complex_grid_widget_3", "coords": [1, 0], "size": "rect_v"},
]


def _surface_id(ctx: dict) -> str:
    return str(ctx.get("_surface_id") or "components_preview").strip() or "components_preview"


def _stream_id(ctx: dict) -> str | None:
    value = str(ctx.get("stream_id") or "").strip()
    return value or None


def _toast(title: str, text: str, variant: str = "info") -> dict:
    return sdk.effects.notify(
        "toast",
        {"title": title, "text": text, "variant": variant, "duration": 2200},
    )


def _mounted_child_ids(props: object) -> list[str]:
    if not isinstance(props, dict):
        return [item["id"] for item in INITIAL_WIDGETS]

    children = props.get("children")
    if not isinstance(children, list):
        return [item["id"] for item in INITIAL_WIDGETS]

    ids: list[str] = []
    for child in children:
        if isinstance(child, str) and child:
            ids.append(child)
        elif isinstance(child, dict):
            child_id = str(child.get("id") or "").strip()
            if child_id:
                ids.append(child_id)
    return ids


def _dashboard_widget(widget_id: str, grid_id: str, size: str, row: int | None, col: int | None):
    text = sdk.ui.Text(f"{widget_id}_text", f"id={widget_id} - size={size}")
    remove = sdk.ui.Button(
        f"{widget_id}_remove",
        "Remove",
        action="components.remove_widget",
        params={"widget_id": widget_id, "grid_id": grid_id},
        variant="destructive",
        btnsize="sm",
    )
    body = sdk.ui.Row(f"{widget_id}_body", [text, remove])
    body.set_property("spacing", 8)
    body.set_property("align", "center")

    widget = sdk.ui.DashboardWidget(
        widget_id,
        size=size,
        title=f"New {size.replace('_', ' ')}",
        children=[body],
    )
    widget.set_property("edit_mode", True)
    if row is not None and col is not None:
        widget.set_property("coords", [row, col])
    return widget


@action("add_widget")
@permission_required(["components.documentation.view"])
async def add_widget(ctx: dict) -> dict:
    size = str(ctx.get("size") or "square").strip() or "square"
    grid_id = str(ctx.get("grid_id") or GRID_ID).strip() or GRID_ID
    row = int(ctx["row"]) if "row" in ctx else None
    col = int(ctx["col"]) if "col" in ctx else None
    widget_id = f"{grid_id}_dyn_{uuid4().hex[:6]}"

    widget = _dashboard_widget(widget_id, grid_id, size, row, col)
    return sdk.effects.respond(
        sdk.effects.ui_collection_append(
            grid_id,
            "children",
            widget,
            surface_id=_surface_id(ctx),
        ),
        _toast("Grid insert", f"Added {widget_id}.", "success"),
    )


@action("move_widget")
@permission_required(["components.documentation.view"])
async def move_widget(ctx: dict) -> dict:
    widget_id = str(ctx.get("widget_id") or ctx.get("id") or "").strip()
    if not widget_id:
        return sdk.effects.respond()

    row = int(ctx.get("row", 0))
    col = int(ctx.get("col", 0))
    return sdk.effects.respond(
        sdk.effects.ui_property_update(
            widget_id,
            "coords",
            [row, col],
            surface_id=_surface_id(ctx),
        ),
        _toast("Grid drag & drop", f"Moved {widget_id} to row={row}, col={col}."),
    )


@action("remove_widget")
@permission_required(["components.documentation.view"])
async def remove_widget(ctx: dict) -> dict:
    widget_id = str(ctx.get("widget_id") or "").strip()
    grid_id = str(ctx.get("grid_id") or GRID_ID).strip() or GRID_ID
    if not widget_id:
        return sdk.effects.respond()

    return sdk.effects.respond(
        sdk.effects.ui_collection_remove(
            grid_id,
            "children",
            {"id": widget_id},
            surface_id=_surface_id(ctx),
        ),
        _toast("Grid remove", f"Removed {widget_id}.", "warning"),
    )


@action("toggle_edit_mode")
@permission_required(["components.documentation.view"])
async def toggle_edit_mode(ctx: dict) -> dict:
    checked = bool(ctx.get("checked", False))
    grid_id = str(ctx.get("grid_id") or GRID_ID).strip() or GRID_ID
    toggle_id = str(ctx.get("toggle_id") or TOGGLE_ID).strip() or TOGGLE_ID
    props = await sdk.effects.ask_current_component_props(
        _stream_id(ctx),
        grid_id,
        surface_id=_surface_id(ctx),
    )

    effects = [
        sdk.effects.ui_property_update(grid_id, "edit_mode", checked, surface_id=_surface_id(ctx)),
        sdk.effects.ui_property_update(toggle_id, "checked", checked, surface_id=_surface_id(ctx)),
        _toast("Grid mode", f"Edit mode {'enabled' if checked else 'disabled'}."),
    ]
    for child_id in _mounted_child_ids(props):
        effects.append(
            sdk.effects.ui_property_update(
                child_id,
                "edit_mode",
                checked,
                surface_id=_surface_id(ctx),
            )
        )
    return sdk.effects.respond(*effects)


@action("reset_grid")
@permission_required(["components.documentation.view"])
async def reset_grid(ctx: dict) -> dict:
    grid_id = str(ctx.get("grid_id") or GRID_ID).strip() or GRID_ID
    toggle_id = str(ctx.get("toggle_id") or TOGGLE_ID).strip() or TOGGLE_ID
    surface_id = _surface_id(ctx)
    initial_ids = [item["id"] for item in INITIAL_WIDGETS]

    effects = [
        sdk.effects.ui_property_update(grid_id, "children", initial_ids, action="set", surface_id=surface_id),
        sdk.effects.ui_property_update(grid_id, "edit_mode", True, surface_id=surface_id),
        sdk.effects.ui_property_update(toggle_id, "checked", True, surface_id=surface_id),
    ]
    for item in INITIAL_WIDGETS:
        effects.append(
            sdk.effects.ui_property_update(item["id"], "coords", item["coords"], surface_id=surface_id)
        )
        effects.append(
            sdk.effects.ui_property_update(item["id"], "edit_mode", True, surface_id=surface_id)
        )
    effects.append(_toast("Grid reset", "Grid restored to the initial widgets."))
    return sdk.effects.respond(*effects)
