from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action


_UPDATED_ROWS = [
    {"id": 201, "name": "Updated queue", "role": "Admin", "status": "active", "team": "Runtime", "score": 99.1, "joined": "2024-03-12T00:00:00", "tags": ["updated"], "selectable": True},
    {"id": 202, "name": "Policy audit", "role": "Editor", "status": "pending", "team": "Security", "score": 84.0, "joined": "2024-03-15T00:00:00", "tags": ["security", "audit"], "selectable": True},
    {"id": 203, "name": "Release gate", "role": "Viewer", "status": "locked", "team": "Platform", "score": 76.5, "joined": "2024-03-20T00:00:00", "tags": ["gate"], "selectable": False},
]

_REMOTE_ROWS = [
    {"id": idx, "name": f"Remote user {idx:02d}", "role": ["Admin", "Editor", "Viewer"][idx % 3], "status": ["active", "pending", "locked"][idx % 3], "team": ["Platform", "Runtime", "Security", "Research"][idx % 4], "score": round(70 + idx * 1.3, 1), "joined": f"2024-04-{(idx % 20) + 1:02d}T00:00:00", "tags": ["remote", f"batch-{idx % 3}"], "selectable": idx % 5 != 0}
    for idx in range(1, 25)
]


def _state_update(sdk, scope: str, values: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages([{"stateUpdate": {"scope": scope, "values": values}}])
    )


def _data_update(sdk, surface_id: str, data: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [sdk.ui.Builder.build_data_model_update_payload(surface_id=surface_id, data=data)]
        )
    )


def _payload_text(ctx: dict) -> str:
    payload = {
        key: value
        for key, value in ctx.items()
        if not str(key).startswith("_")
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > 900:
        text = f"{text[:900]}..."
    return text


def _filtered_rows(ctx: dict) -> list[dict]:
    filters = ctx.get("filters") or {}
    rows = list(_REMOTE_ROWS)
    for field, value in filters.items():
        if value is None or value == "":
            continue
        rows = [row for row in rows if str(value).lower() in str(row.get(field, "")).lower()]

    sort = ctx.get("sort") or {}
    field = str(sort.get("field") or ctx.get("sortField") or "").strip()
    reverse = str(sort.get("direction") or ctx.get("sortDirection") or "asc").lower() == "desc"
    if field:
        rows = sorted(rows, key=lambda row: row.get(field), reverse=reverse)
    return rows


def _next_appended_row(rows: list[dict]) -> dict:
    next_id = max((int(row.get("id") or 0) for row in rows if isinstance(row, dict)), default=203) + 1
    return {
        "id": next_id,
        "name": f"Direct append {next_id}",
        "role": "Viewer",
        "status": "active",
        "team": "Console",
        "score": 81.8,
        "joined": "2024-03-25T00:00:00",
        "tags": ["direct"],
        "selectable": True,
    }


@action("datatable_update")
@permission_required(["components.documentation.view"])
async def datatable_update(ctx: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_complex/datatable/rows": _UPDATED_ROWS,
                "/components_complex/datatable/total": len(_UPDATED_ROWS),
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_complex/datatable/rows": _UPDATED_ROWS,
                "/components_complex/datatable/total": len(_UPDATED_ROWS),
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_complex": {"datatable_model": {"rows": _UPDATED_ROWS, "total": len(_UPDATED_ROWS)}}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_datatable_direct",
                "rows",
                _UPDATED_ROWS,
                action="set",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_datatable_direct",
                "total_rows",
                len(_UPDATED_ROWS),
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_datatable_direct",
                "page",
                0,
                surface_id=surface_id,
            ),
        )
    if mode == "direct_append":
        stream_id = str(ctx.get("stream_id") or "").strip() or None
        props = await sdk.effects.ask_current_component_props(
            stream_id,
            "components_complex_datatable_direct",
            surface_id=surface_id,
        )
        rows = props.get("rows") if isinstance(props, dict) else []
        current_rows = rows if isinstance(rows, list) else []
        appended_row = _next_appended_row(current_rows)
        return sdk.effects.respond(
            sdk.effects.ui_collection_append(
                "components_complex_datatable_direct",
                "rows",
                appended_row,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_datatable_direct",
                "total_rows",
                len(current_rows) + 1,
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()


@action("datatable_remote")
@permission_required(["components.documentation.view"])
async def datatable_remote(ctx: dict, sdk) -> dict:
    table_id = str(ctx.get("tableId") or "components_complex_datatable_remote")
    page = int(ctx.get("page") or 0)
    page_size = int(ctx.get("pageSize") or ctx.get("page_size") or 5)
    rows = _filtered_rows(ctx)
    start = page * page_size
    page_rows = rows[start:start + page_size]
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    return sdk.effects.respond(
        sdk.effects.ui_property_update(table_id, "rows", page_rows, action="set", surface_id=surface_id),
        sdk.effects.ui_property_update(table_id, "page", page, surface_id=surface_id),
        sdk.effects.ui_property_update(table_id, "page_size", page_size, surface_id=surface_id),
        sdk.effects.ui_property_update(table_id, "total_rows", len(rows), surface_id=surface_id),
    )


@action("datatable_event")
@permission_required(["components.documentation.view"])
async def datatable_event(ctx: dict, sdk) -> dict:
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "DataTable event",
                "text": _payload_text(ctx),
                "variant": "info",
                "duration": 3000,
            },
        )
    )
