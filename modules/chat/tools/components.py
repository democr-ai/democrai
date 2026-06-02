from __future__ import annotations

from typing import Any

from democrai.sdk.decorators import tool

from modules.chat.utils.actions.components import (
    normalize_component_payload,
)
from modules.chat.utils.actions.a2ui_schema import (
    A2UIValidationError,
    lit,
)


def _component_result(
    *,
    component_type: str,
    props: dict[str, Any],
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        component_kind, payload = normalize_component_payload(
            component_type, props, children
        )
    except A2UIValidationError as exc:
        return {
            "status": "error",
            "error": "invalid_component_schema",
            "path": exc.path,
            "message": exc.message,
            "components_tool": "chat.show-component",
        }
    return {
        "status": "ok",
        "component_kind": component_kind,
        "components": [payload],
    }


CALLABLE_COMPONENT_TOOLS = [
    {
        "component": "Alert",
        "tool": "chat.show-alert",
        "use": "notice, warning, success, or error message",
    },
    {"component": "Badge", "tool": "chat.show-badge", "use": "compact status label"},
    {
        "component": "Card",
        "tool": "chat.show-card",
        "use": "compact title and markdown body",
    },
    {
        "component": "Chart",
        "tool": "chat.show-chart",
        "use": "bar, line, or area chart",
    },
    {
        "component": "Collapsible",
        "tool": "chat.show-collapse",
        "use": "expandable title and text",
    },
    {
        "component": "DataTable",
        "tool": "chat.show-table",
        "use": "explicit columns and rows",
    },
    {
        "component": "Descriptions",
        "tool": "chat.show-descriptions",
        "use": "key/value inspection block",
    },
    {
        "component": "Grid",
        "tool": "chat.show-metric-grid",
        "use": "dashboard metric cards",
    },
    {
        "component": "List",
        "tool": "chat.show-list",
        "use": "vertical list of title/text items",
    },
    {
        "component": "Markdown",
        "tool": "chat.show-markdown",
        "use": "formatted markdown block",
    },
    {
        "component": "Progress",
        "tool": "chat.show-progress",
        "use": "single progress indicator",
    },
    {
        "component": "SequenceDiagram",
        "tool": "chat.show-sequence-diagram",
        "use": "service or request flow",
    },
    {"component": "Tabs", "tool": "chat.show-tabs", "use": "multiple text sections"},
    {"component": "Text", "tool": "chat.show-text", "use": "plain text block"},
    {"component": "Title", "tool": "chat.show-title", "use": "section heading"},
]


@tool(
    "show-alert",
    title="Show alert",
    description="Generate one alert with title, text, and variant.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "text": {"type": "string"},
            "variant": {
                "type": "string",
                "enum": ["info", "success", "warning", "destructive", "default"],
            },
        },
        "required": ["title"],
        "additionalProperties": False,
    },
)
def show_alert(
    title: str,
    text: str = "",
    variant: str = "info",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    props = {"title": lit(title), "variant": variant}
    if text:
        props["description"] = lit(text)
    return _component_result(
        component_type="Alert",
        props=props,
    )


@tool(
    "show-badge",
    title="Show badge",
    description="Generate one compact badge.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "variant": {
                "type": "string",
                "enum": ["default", "info", "success", "warning", "destructive"],
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)
def show_badge(
    text: str,
    variant: str = "default",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _component_result(
        component_type="Badge",
        props={"text": lit(text), "variant": variant},
    )


@tool(
    "show-chart",
    title="Show chart",
    description=(
        "Generate one compact chart component for a chart, graph, trend, or small "
        "visual summary."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "chart_type": {"type": "string", "enum": ["bar", "line", "area"]},
            "labels": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "data": {"type": "array", "items": {"type": "number"}, "minItems": 1},
        },
        "required": ["chart_type", "labels", "data"],
        "additionalProperties": False,
    },
)
def show_chart(
    chart_type: str,
    labels: list[str],
    data: list[float],
    title: str = "",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chart = {
        "type": "Chart",
        "props": {
            "chartType": chart_type,
            "labels": labels,
            "data": data,
            "title": title,
            "max_width": 500,
            "max_height": 300,
        },
    }
    return _component_result(
        component_type="Card",
        props={"variant": "outlined", "max_width": 540},
        children=[chart],
    )


@tool(
    "show-table",
    title="Show table",
    description=("Generate one DataTable from explicit columns and rows."),
    input_schema={
        "type": "object",
        "properties": {
            "columns": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "minLength": 1},
                        "label": {"type": "string", "minLength": 1},
                        "type": {
                            "type": "string",
                            "enum": [
                                "string",
                                "text",
                                "number",
                                "boolean",
                                "date",
                                "datetime",
                                "badge",
                            ],
                        },
                    },
                    "required": ["field", "label", "type"],
                    "additionalProperties": False,
                },
            },
            "rows": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["columns", "rows"],
        "additionalProperties": False,
    },
)
def show_table(
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    invalid_index = next(
        (
            index
            for index, column in enumerate(columns)
            if "field" not in column or "label" not in column or "type" not in column
        ),
        None,
    )
    if invalid_index is not None:
        return {
            "status": "error",
            "error": "invalid_column",
            "path": f"columns.{invalid_index}",
            "message": "column requires field, label, and type",
        }
    model = [
        {
            "id": column["field"],
            "field": column["field"],
            "label": column["label"],
            "type": column["type"] if column["type"] != "string" else "text",
        }
        for column in columns
    ]
    return _component_result(
        component_type="DataTable",
        props={
            "model": model,
            "rows": rows,
            "paginated": False,
            "pagination": False,
        },
    )


@tool(
    "show-list",
    title="Show list",
    description=(
        "Generate one simple list for bullets, tasks, compact items, or ordered "
        "summaries."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["title"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    },
)
def show_list(
    items: list[dict[str, str]],
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _component_result(
        component_type="List",
        props={
            "template": "title_text",
            "orientation": "vertical",
            "selectable": False,
            "dataSource": {
                "type": "inline",
                "data": [
                    {"id": f"item_{index + 1}", **item}
                    for index, item in enumerate(items)
                ],
            },
        },
    )


@tool(
    "show-card",
    title="Show card",
    description=(
        "Generate one compact card with a title and markdown body for short "
        "summaries, notes, and highlighted results."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "body": {"type": "string", "minLength": 1},
            "variant": {"type": "string", "enum": ["elevated", "outlined", "flat"]},
        },
        "required": ["title", "body"],
        "additionalProperties": False,
    },
)
def show_card(
    title: str,
    body: str,
    variant: str = "outlined",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _component_result(
        component_type="Card",
        props={"variant": variant, "max_width": 640},
        children=[
            {"type": "Title", "props": {"text": lit(title), "level": 4}},
            {"type": "Markdown", "props": {"text": lit(body)}},
        ],
    )


@tool(
    "show-collapse",
    title="Show collapse",
    description=(
        "Generate one Collapsible block with a title and text body. Use it when the "
        "user asks for collapsible details, expandable notes, or secondary text."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "text": {"type": "string", "minLength": 1},
            "open": {"type": "boolean"},
        },
        "required": ["title", "text"],
        "additionalProperties": False,
    },
)
def show_collapse(
    title: str,
    text: str,
    open: bool = False,
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _component_result(
        component_type="Collapsible",
        props={"title": lit(title), "content": lit(text), "open": bool(open)},
    )


@tool(
    "show-metric-grid",
    title="Show metric grid",
    description=(
        "Generate one compact metric summary from name/value pairs. Prefer this for "
        "dashboard-style numeric summaries instead of composing several components."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "metrics": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "value": {"type": ["string", "number", "boolean"]},
                    },
                    "required": ["label", "value"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["metrics"],
        "additionalProperties": False,
    },
)
def show_metric_grid(
    metrics: list[dict[str, Any]],
    title: str = "",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    invalid_index = next(
        (
            index
            for index, item in enumerate(metrics)
            if "label" not in item or "value" not in item
        ),
        None,
    )
    if invalid_index is not None:
        return {
            "status": "error",
            "error": "invalid_metric",
            "path": f"metrics.{invalid_index}",
            "message": "metric requires label and value",
        }
    metric_cards = [
        {
            "type": "Card",
            "props": {"variant": "outlined", "padding": [12]},
            "children": [
                {
                    "type": "Text",
                    "props": {"text": lit(str(item["label"]))},
                },
                {
                    "type": "Title",
                    "props": {"text": lit(str(item["value"])), "level": 3},
                },
            ],
        }
        for item in metrics
    ]
    grid = {
        "type": "Grid",
        "props": {
            "columns": min(3, max(1, len(metrics))),
            "style": "max-width: 760px;",
        },
        "children": metric_cards,
    }
    children = []
    if title:
        children.append({"type": "Title", "props": {"text": lit(title), "level": 4}})
    children.append(grid)
    return _component_result(
        component_type="Grid",
        props={"columns": 1, "style": "max-width: 760px;"},
        children=children,
    )


@tool(
    "show-descriptions",
    title="Show descriptions",
    description="Generate one key/value descriptions block.",
    input_schema={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "value": {"type": ["string", "number", "boolean"]},
                    },
                    "required": ["label", "value"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    },
)
def show_descriptions(
    items: list[dict[str, Any]],
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = [
        {
            "id": f"field_{index + 1}",
            "field": f"field_{index + 1}",
            "label": str(item["label"]),
            "type": "text",
        }
        for index, item in enumerate(items)
    ]
    data = {
        f"field_{index + 1}": str(item["value"]) for index, item in enumerate(items)
    }
    return _component_result(
        component_type="Descriptions",
        props={"model": model, "data": data, "borders": True},
    )


@tool(
    "show-markdown",
    title="Show markdown",
    description="Generate one markdown block.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)
def show_markdown(
    text: str,
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _component_result(
        component_type="Markdown",
        props={"text": lit(text)},
    )


@tool(
    "show-progress",
    title="Show progress",
    description="Generate one progress indicator.",
    input_schema={
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "value": {"type": "integer", "minimum": 0},
            "maximum": {"type": "integer", "minimum": 1},
        },
        "required": ["value", "maximum"],
        "additionalProperties": False,
    },
)
def show_progress(
    value: int,
    maximum: int,
    label: str = "",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    props: dict[str, Any] = {
        "value": value,
        "maximum": maximum,
        "label": lit(label or "Progress"),
        "show_label": bool(label),
    }
    return _component_result(
        component_type="Progress",
        props=props,
    )


@tool(
    "show-sequence-diagram",
    title="Show sequence diagram",
    description="Generate one sequence diagram from participants and messages.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "participants": {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "label": {"type": "string", "minLength": 1},
                    },
                    "required": ["id", "label"],
                    "additionalProperties": False,
                },
            },
            "messages": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string", "minLength": 1},
                        "to": {"type": "string", "minLength": 1},
                        "text": {"type": "string", "minLength": 1},
                        "type": {"type": "string", "enum": ["sync", "async", "reply"]},
                    },
                    "required": ["from", "to", "text"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["participants", "messages"],
        "additionalProperties": False,
    },
)
def show_sequence_diagram(
    participants: list[dict[str, str]],
    messages: list[dict[str, str]],
    title: str = "",
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_messages = [
        {**message, "type": str(message.get("type") or "sync")} for message in messages
    ]
    return _component_result(
        component_type="SequenceDiagram",
        props={
            "title": title,
            "height": 420,
            "participants": participants,
            "messages": resolved_messages,
        },
    )


@tool(
    "show-tabs",
    title="Show tabs",
    description="Generate one tab block with simple markdown content.",
    input_schema={
        "type": "object",
        "properties": {
            "tabs": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "text": {"type": "string", "minLength": 1},
                    },
                    "required": ["label", "text"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["tabs"],
        "additionalProperties": False,
    },
)
def show_tabs(
    tabs: list[dict[str, str]],
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tab_defs = [
        {"id": f"tab_{index + 1}", "label": str(tab["label"])}
        for index, tab in enumerate(tabs)
    ]
    children = [
        {
            "id": tab_defs[index]["id"],
            "type": "Markdown",
            "props": {"text": lit(str(tab["text"]))},
        }
        for index, tab in enumerate(tabs)
    ]
    return _component_result(
        component_type="Tabs",
        props={"tabs": tab_defs},
        children=children,
    )


@tool(
    "show-text",
    title="Show text",
    description="Generate one plain text block.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)
def show_text(
    text: str,
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _component_result(
        component_type="Text",
        props={"text": lit(text)},
    )


@tool(
    "show-title",
    title="Show title",
    description="Generate one title heading.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "level": {"type": "integer", "minimum": 1, "maximum": 6},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)
def show_title(
    text: str,
    level: int = 3,
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _component_result(
        component_type="Title",
        props={"text": lit(text), "level": level},
    )


@tool(
    "show-component",
    title="List chat UI component tools",
    description=(
        "Return the chat UI components that can be rendered and the dedicated tool "
        "to call for each one. This tool does not render or save anything."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)
def show_component() -> dict[str, Any]:
    return {
        "status": "ok",
        "components": CALLABLE_COMPONENT_TOOLS,
    }
