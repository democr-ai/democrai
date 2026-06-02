from __future__ import annotations

from democrai.sdk.auth import permission_required
from uuid import uuid4

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.decorators import action


def _surface_id(ctx: dict) -> str:
    return str(ctx.get("_surface_id") or "main").strip() or "main"


def _dynamic_row(item_id: str, label: str):
    text = sdk.ui.Text(f"dynamic_append_text_{item_id}", label)
    remove = sdk.ui.Button(
        f"dynamic_remove_btn_{item_id}",
        "Remove",
        action="components.dynamic_remove_item",
        params={"item_id": item_id},
        variant="danger",
    )
    row = sdk.ui.Row(f"dynamic_append_row_{item_id}", [text, remove])
    row.set_property("spacing", 10)
    row.set_property("align", "left")
    row.set_property("style", "margin-bottom: 4px;")
    return row


def _component_children(component: dict | None) -> list:
    if not isinstance(component, dict):
        return []
    children_node = component.get("children")
    if not isinstance(children_node, dict):
        return []
    children = children_node.get("explicitList")
    return children if isinstance(children, list) else []


async def _first_child_id(ctx: dict) -> str:
    stream_id = str(ctx.get("stream_id") or "").strip() or None
    component = await sdk.effects.ask_current_component(
        stream_id,
        "dynamic_append_container",
        surface_id=_surface_id(ctx),
    )
    children = _component_children(component)
    if not children:
        return "dynamic_seed_row"

    first_child = children[0]
    if isinstance(first_child, str):
        return first_child
    if isinstance(first_child, dict):
        return str(first_child.get("id") or "").strip()
    return ""


async def _mounted_child_ids(ctx: dict, container_id: str) -> list[str]:
    stream_id = str(ctx.get("stream_id") or "").strip() or None
    component = await sdk.effects.ask_current_component(
        stream_id,
        container_id,
        surface_id=_surface_id(ctx),
    )
    children = _component_children(component)
    if not children:
        return ["dynamic_seed_row"] if container_id == "dynamic_append_container" else []

    child_ids: list[str] = []
    for child in children:
        if isinstance(child, str) and child:
            child_ids.append(child)
        elif isinstance(child, dict):
            child_id = str(child.get("id") or "").strip()
            if child_id:
                child_ids.append(child_id)
    return child_ids


@action("dynamic_append_item")
@permission_required(["components.documentation.view"])
async def dynamic_append_item(ctx: dict, session: dict) -> dict:
    item_id = uuid4().hex[:8]
    row = _dynamic_row(item_id, f"Element {item_id}")
    return sdk.effects.respond(
        sdk.effects.ui_collection_append(
            "dynamic_append_container",
            "children",
            row,
            surface_id=_surface_id(ctx),
        )
    )


@action("dynamic_remove_item")
@permission_required(["components.documentation.view"])
async def dynamic_remove_item(ctx: dict, session: dict) -> dict:
    item_id = str(ctx.get("item_id") or "").strip()
    row_id = "dynamic_seed_row" if item_id == "seed" else f"dynamic_append_row_{item_id}"
    return sdk.effects.respond(
        sdk.effects.ui_collection_remove(
            "dynamic_append_container",
            "children",
            {"id": row_id},
            surface_id=_surface_id(ctx),
        )
    )


@action("dynamic_replace_same_id")
@permission_required(["components.documentation.view"])
async def dynamic_replace_same_id(ctx: dict, session: dict) -> dict:
    target_id = await _first_child_id(ctx)
    if not target_id:
        return sdk.effects.respond()

    item_id = target_id.removeprefix("dynamic_append_row_")
    row = _dynamic_row(item_id, "Substitution with the same row id")
    row.id = target_id
    return sdk.effects.respond(
        sdk.effects.ui_collection_replace(
            "dynamic_append_container",
            "children",
            {"id": target_id, "item": row},
            surface_id=_surface_id(ctx),
        )
    )


@action("dynamic_replace_new_id")
@permission_required(["components.documentation.view"])
async def dynamic_replace_new_id(ctx: dict, session: dict) -> dict:
    target_id = await _first_child_id(ctx)
    if not target_id:
        return sdk.effects.respond()

    item_id = f"new_{uuid4().hex[:6]}"
    row = _dynamic_row(item_id, f"Replacement with new id {item_id}")
    return sdk.effects.respond(
        sdk.effects.ui_collection_replace(
            "dynamic_append_container",
            "children",
            {"id": target_id, "item": row},
            surface_id=_surface_id(ctx),
        )
    )


@action("dynamic_set_children")
@permission_required(["components.documentation.view"])
async def dynamic_set_children(ctx: dict, session: dict) -> dict:
    effects = [
        sdk.effects.ui_collection_remove(
            "dynamic_append_container",
            "children",
            {"id": child_id},
            surface_id=_surface_id(ctx),
        )
        for child_id in await _mounted_child_ids(ctx, "dynamic_append_container")
    ]
    rows = [
        _dynamic_row("set_1", "Set Item 1"),
        _dynamic_row("set_2", "Set Item 2"),
    ]
    effects.extend(
        [
            sdk.effects.ui_collection_append(
                "dynamic_append_container",
                "children",
                row,
                surface_id=_surface_id(ctx),
            )
            for row in rows
        ]
    )
    return sdk.effects.respond(*effects)


@action("dynamic_remove_first_by_index")
@permission_required(["components.documentation.view"])
async def dynamic_remove_first_by_index(ctx: dict, session: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_collection_remove(
            "dynamic_append_container",
            "children",
            {"index": 0},
            surface_id=_surface_id(ctx),
        )
    )


@action("dynamic_replace_content")
@permission_required(["components.documentation.view"])
async def dynamic_replace_content(ctx: dict, session: dict) -> dict:
    item_id = uuid4().hex[:8]
    text = sdk.ui.Text(
        f"dynamic_replace_text_{item_id}",
        f"Replacement content {item_id}",
    )
    effects = [
        sdk.effects.ui_collection_remove(
            "dynamic_replace_container",
            "children",
            {"id": child_id},
            surface_id=_surface_id(ctx),
        )
        for child_id in await _mounted_child_ids(ctx, "dynamic_replace_container")
    ]
    effects.append(
        sdk.effects.ui_collection_append(
            "dynamic_replace_container",
            "children",
            text,
            surface_id=_surface_id(ctx),
        )
    )
    return sdk.effects.respond(*effects)
