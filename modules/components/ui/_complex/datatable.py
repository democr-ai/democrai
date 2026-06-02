from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_MODEL = [
    {"field": "id", "header": "ID", "type": "int", "width": 64, "editable": False, "sortable": True},
    {"field": "name", "header": "Name", "type": "str", "editable": True, "filterable": True, "filter_type": "text", "sortable": True},
    {"field": "role", "header": "Role", "type": "enum", "editable": True, "filterable": True, "filter_type": "select", "options": ["Admin", "Editor", "Viewer", "Guest"]},
    {"field": "status", "header": "Status", "type": "str", "editable": False, "filterable": True, "filter_type": "select", "options": ["active", "pending", "locked"]},
    {"field": "team", "header": "Team", "type": "str", "editable": False, "filterable": True, "filter_type": "text"},
    {"field": "score", "header": "Score", "type": "float", "editable": True, "sortable": True},
    {"field": "joined", "header": "Joined", "type": "str", "editable": False, "transform": "date|%Y-%m-%d"},
    {"field": "tags", "header": "Tags", "type": "str", "editable": False, "transform": "join_list|, |upper"},
]

_ROWS = [
    {"id": 101, "name": "Ada Lovelace", "role": "Admin", "status": "active", "team": "Platform", "score": 98.4, "joined": "2024-01-10T00:00:00", "tags": ["owner", "release"], "selectable": True},
    {"id": 102, "name": "Grace Hopper", "role": "Editor", "status": "active", "team": "Runtime", "score": 91.2, "joined": "2024-01-18T00:00:00", "tags": ["runtime", "review"], "selectable": True},
    {"id": 103, "name": "Katherine Johnson", "role": "Viewer", "status": "pending", "team": "Research", "score": 86.7, "joined": "2024-02-02T00:00:00", "tags": ["analysis"], "selectable": True},
    {"id": 104, "name": "Margaret Hamilton", "role": "Admin", "status": "locked", "team": "Safety", "score": 94.1, "joined": "2024-02-14T00:00:00", "tags": ["safety", "locked"], "selectable": False},
    {"id": 105, "name": "Dorothy Vaughan", "role": "Editor", "status": "active", "team": "Operations", "score": 88.9, "joined": "2024-03-01T00:00:00", "tags": ["ops"], "selectable": True},
]

_UPDATED_ROWS = [
    {"id": 201, "name": "Updated queue", "role": "Admin", "status": "active", "team": "Runtime", "score": 99.1, "joined": "2024-03-12T00:00:00", "tags": ["updated"], "selectable": True},
    {"id": 202, "name": "Policy audit", "role": "Editor", "status": "pending", "team": "Security", "score": 84.0, "joined": "2024-03-15T00:00:00", "tags": ["security", "audit"], "selectable": True},
    {"id": 203, "name": "Release gate", "role": "Viewer", "status": "locked", "team": "Platform", "score": 76.5, "joined": "2024-03-20T00:00:00", "tags": ["gate"], "selectable": False},
]

_REMOTE_ROWS = [
    {"id": idx, "name": f"Remote user {idx:02d}", "role": ["Admin", "Editor", "Viewer"][idx % 3], "status": ["active", "pending", "locked"][idx % 3], "team": ["Platform", "Runtime", "Security", "Research"][idx % 4], "score": round(70 + idx * 1.3, 1), "joined": f"2024-04-{(idx % 20) + 1:02d}T00:00:00", "tags": ["remote", f"batch-{idx % 3}"], "selectable": idx % 5 != 0}
    for idx in range(1, 25)
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/datatable"), components=True)

    for scope in ("page", "global"):
        builder.set_store("/components_complex/datatable/rows", _ROWS, scope=scope)
        builder.set_store("/components_complex/datatable/total", len(_ROWS), scope=scope)

    builder.set_data(
        "/components_complex/datatable_model",
        {
            "model": _MODEL,
            "rows": _ROWS,
            "total": len(_ROWS),
            "remote_rows": _REMOTE_ROWS[:5],
            "remote_total": len(_REMOTE_ROWS),
        },
    )
    builder.set_data(
        "/components_complex/datatable_bindings",
        [
            {"binding": "Literal", "yaml": "rows:\n  - {id: 101, name: Ada Lovelace, ...}", "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "rows: {type: store, scope: page, path: /components_complex/datatable/rows}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "rows: {type: store, scope: global, path: /components_complex/datatable/rows}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": 'rows: "@data/components_complex/datatable_model/rows"', "source": "builder.set_data(...)"},
            {"binding": "Direct update", "yaml": "capabilities: [rows.set, rows.append, rows.remove, rows.replace, total_rows.set]", "source": "sdk.effects.ui_property_update / ui_collection_*"},
            {"binding": "Remote service", "yaml": "remote_service: components.datatable_remote", "source": "Backend action returns rows/page/total_rows"},
        ],
    )
    builder.set_data(
        "/components_complex/datatable_properties",
        [
            {"property": "model", "type": "list[ColumnDef]", "usage": sdk.i18n.t("components.complex.datatable.property.model")},
            {"property": "rows", "type": "list[dict]", "usage": sdk.i18n.t("components.complex.datatable.property.rows")},
            {"property": "page / page_size / total_rows", "type": "int", "usage": sdk.i18n.t("components.complex.datatable.property.pagination")},
            {"property": "remote_service", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.datatable.property.remote_service")},
            {"property": "on_page_change / on_filter_change", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.datatable.property.page_actions")},
            {"property": "on_cell_edit", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.datatable.property.cell_edit")},
            {"property": "on_row_add", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.datatable.property.row_add")},
            {"property": "row_actions", "type": "list[ActionDef]", "usage": sdk.i18n.t("components.complex.datatable.property.row_actions")},
            {"property": "selection_actions", "type": "list[ActionDef]", "usage": sdk.i18n.t("components.complex.datatable.property.selection_actions")},
            {"property": "sort / filters", "type": "dict", "usage": sdk.i18n.t("components.complex.datatable.property.sort_filters")},
            {"property": "show_row_numbers / selectable / virtual", "type": "bool", "usage": sdk.i18n.t("components.complex.datatable.property.flags")},
        ],
    )
    builder.set_data(
        "/components_complex/datatable_model_schema",
        {
            "columns": [
                {"key": "field", "type": "str", "required": sdk.i18n.t("components.complex.datatable.model.required.yes"), "usage": sdk.i18n.t("components.complex.datatable.model.key.field")},
                {"key": "header", "type": "str", "required": sdk.i18n.t("components.complex.datatable.model.required.yes"), "usage": sdk.i18n.t("components.complex.datatable.model.key.header")},
                {"key": "type", "type": "str", "required": sdk.i18n.t("components.complex.datatable.model.required.no"), "usage": sdk.i18n.t("components.complex.datatable.model.key.type")},
                {"key": "editable", "type": "bool | rule", "required": sdk.i18n.t("components.complex.datatable.model.required.no"), "usage": sdk.i18n.t("components.complex.datatable.model.key.editable")},
                {"key": "filterable", "type": "bool", "required": sdk.i18n.t("components.complex.datatable.model.required.no"), "usage": sdk.i18n.t("components.complex.datatable.model.key.filterable")},
                {"key": "filter_type", "type": "str", "required": sdk.i18n.t("components.complex.datatable.model.required.no"), "usage": sdk.i18n.t("components.complex.datatable.model.key.filter_type")},
                {"key": "options", "type": "list[str]", "required": sdk.i18n.t("components.complex.datatable.model.required.no"), "usage": sdk.i18n.t("components.complex.datatable.model.key.options")},
                {"key": "sortable", "type": "bool", "required": sdk.i18n.t("components.complex.datatable.model.required.no"), "usage": sdk.i18n.t("components.complex.datatable.model.key.sortable")},
                {"key": "width", "type": "int", "required": sdk.i18n.t("components.complex.datatable.model.required.no"), "usage": sdk.i18n.t("components.complex.datatable.model.key.width")},
                {"key": "transform", "type": "str", "required": sdk.i18n.t("components.complex.datatable.model.required.no"), "usage": sdk.i18n.t("components.complex.datatable.model.key.transform")},
            ],
            "field_types": [
                {"type": "str", "display": sdk.i18n.t("components.complex.datatable.model.field.text_display"), "editable": sdk.i18n.t("components.complex.datatable.model.field.text_edit"), "payload": sdk.i18n.t("components.complex.datatable.model.field.text_payload")},
                {"type": "int", "display": sdk.i18n.t("components.complex.datatable.model.field.text_display"), "editable": sdk.i18n.t("components.complex.datatable.model.field.text_edit"), "payload": sdk.i18n.t("components.complex.datatable.model.field.text_payload")},
                {"type": "float", "display": sdk.i18n.t("components.complex.datatable.model.field.text_display"), "editable": sdk.i18n.t("components.complex.datatable.model.field.text_edit"), "payload": sdk.i18n.t("components.complex.datatable.model.field.text_payload")},
                {"type": "bool", "display": sdk.i18n.t("components.complex.datatable.model.field.bool_display"), "editable": sdk.i18n.t("components.complex.datatable.model.field.bool_edit"), "payload": sdk.i18n.t("components.complex.datatable.model.field.bool_payload")},
                {"type": "enum", "display": sdk.i18n.t("components.complex.datatable.model.field.enum_display"), "editable": sdk.i18n.t("components.complex.datatable.model.field.enum_edit"), "payload": sdk.i18n.t("components.complex.datatable.model.field.enum_payload")},
            ],
            "filters": [
                {"type": "text", "control": sdk.i18n.t("components.complex.datatable.model.filter.text_control"), "payload": sdk.i18n.t("components.complex.datatable.model.filter.text_payload")},
                {"type": "select", "control": sdk.i18n.t("components.complex.datatable.model.filter.select_control"), "payload": sdk.i18n.t("components.complex.datatable.model.filter.select_payload")},
                {"type": "boolean", "control": sdk.i18n.t("components.complex.datatable.model.filter.boolean_control"), "payload": sdk.i18n.t("components.complex.datatable.model.filter.boolean_payload")},
                {"type": "date", "control": sdk.i18n.t("components.complex.datatable.model.filter.text_control"), "payload": sdk.i18n.t("components.complex.datatable.model.filter.string_payload")},
                {"type": "number", "control": sdk.i18n.t("components.complex.datatable.model.filter.text_control"), "payload": sdk.i18n.t("components.complex.datatable.model.filter.string_payload")},
            ],
            "formatters": [
                {"formatter": "upper", "syntax": "upper", "usage": sdk.i18n.t("components.complex.datatable.model.formatter.upper")},
                {"formatter": "lower", "syntax": "lower", "usage": sdk.i18n.t("components.complex.datatable.model.formatter.lower")},
                {"formatter": "title", "syntax": "title", "usage": sdk.i18n.t("components.complex.datatable.model.formatter.title")},
                {"formatter": "truncate", "syntax": "truncate|N", "usage": sdk.i18n.t("components.complex.datatable.model.formatter.truncate")},
                {"formatter": "date", "syntax": "date|FORMAT", "usage": sdk.i18n.t("components.complex.datatable.model.formatter.date")},
                {"formatter": "join_list", "syntax": "join_list|SEP|INNER", "usage": sdk.i18n.t("components.complex.datatable.model.formatter.join_list")},
                {"formatter": "join_objects", "syntax": "join_objects|KEY|SEP|INNER", "usage": sdk.i18n.t("components.complex.datatable.model.formatter.join_objects")},
                {"formatter": "get_stub", "syntax": "get_stub|STUB|FIELD", "usage": sdk.i18n.t("components.complex.datatable.model.formatter.get_stub")},
            ],
        },
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_datatable_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
