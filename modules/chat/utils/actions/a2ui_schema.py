from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


SUPPORTED_COMPONENTS = {
    "Alert",
    "Badge",
    "Card",
    "Chart",
    "Collapsible",
    "DataTable",
    "Descriptions",
    "Grid",
    "List",
    "Markdown",
    "Progress",
    "SequenceDiagram",
    "Tabs",
    "Text",
    "Title",
}

CONTAINER_COMPONENTS = {"Card", "Grid", "Tabs"}

# The chat tool intentionally exposes a simpler type/props/children input than
# raw A2UI. Asking local models to generate the full nested A2UI envelope is too
# fragile; Python only wraps the simpler shape into the exact A2UI envelope and
# then validates the final component against this schema.


def lit(value: str) -> dict[str, str]:
    return {"literalString": value}


def _literal_string_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"literalString": {"type": "string"}},
        "required": ["literalString"],
        "additionalProperties": False,
    }


def _component_schema(component: str, props: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "component": {
                "type": "object",
                "properties": {component: props},
                "required": [component],
                "additionalProperties": False,
            },
            "children": {
                "type": "object",
                "properties": {
                    "explicitList": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/a2uiComponent"},
                    }
                },
                "required": ["explicitList"],
                "additionalProperties": False,
            },
        },
        "required": ["id", "component", "children"],
        "additionalProperties": False,
    }


def _props(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TEXT_LITERAL = _literal_string_schema()

TABLE_FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "field": {"type": "string", "minLength": 1},
        "label": {"type": "string", "minLength": 1},
        "type": {
            "type": "string",
            "enum": ["text", "number", "boolean", "date", "datetime", "badge"],
        },
        "editable": {"type": "boolean"},
    },
    "required": ["id", "field", "label", "type"],
    "additionalProperties": False,
}

LIST_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "title": {"type": "string"},
        "text": {"type": "string"},
        "value": {"type": ["string", "number", "boolean", "null"]},
    },
    "required": ["id"],
    "additionalProperties": False,
}

COMPONENT_SCHEMAS: dict[str, dict[str, Any]] = {
    "Alert": _props(
        ["title"],
        {
            "title": TEXT_LITERAL,
            "description": TEXT_LITERAL,
            "variant": {
                "type": "string",
                "enum": ["info", "success", "warning", "destructive", "default"],
            },
        },
    ),
    "Badge": _props(
        ["text"],
        {
            "text": TEXT_LITERAL,
            "variant": {
                "type": "string",
                "enum": ["default", "info", "success", "warning", "destructive"],
            },
        },
    ),
    "Card": _props(
        [],
        {
            "variant": {"type": "string", "enum": ["elevated", "outlined", "flat"]},
            "padding": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0},
                "minItems": 1,
                "maxItems": 4,
            },
            "max_width": {"type": "integer", "minimum": 120, "maximum": 1200},
            "data": {"type": "object"},
        },
    ),
    "Chart": _props(
        ["chartType", "data", "labels"],
        {
            "chartType": {"type": "string", "enum": ["bar", "line", "area"]},
            "data": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 1,
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "title": {"type": "string"},
            "max_height": {"type": "integer", "minimum": 120, "maximum": 800},
            "max_width": {"type": "integer", "minimum": 120, "maximum": 1200},
        },
    ),
    "Collapsible": _props(
        ["title", "content"],
        {
            "title": TEXT_LITERAL,
            "content": TEXT_LITERAL,
            "open": {"type": "boolean"},
        },
    ),
    "DataTable": _props(
        ["model", "rows"],
        {
            "model": {
                "type": "array",
                "items": TABLE_FIELD_SCHEMA,
                "minItems": 1,
            },
            "rows": {
                "type": "array",
                "items": {"type": "object"},
            },
            "paginated": {"type": "boolean"},
            "pagination": {"type": "boolean"},
            "page": {"type": "integer", "minimum": 0},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
            "total_rows": {"type": "integer", "minimum": 0},
            "show_row_numbers": {"type": "boolean"},
            "selectable": {"type": "boolean"},
            "virtual": {"type": "boolean"},
        },
    ),
    "Descriptions": _props(
        ["model", "data"],
        {
            "model": {
                "type": "array",
                "items": TABLE_FIELD_SCHEMA,
                "minItems": 1,
            },
            "data": {"type": "object"},
            "key_header": {"type": "string"},
            "value_header": {"type": "string"},
            "borders": {"type": "boolean"},
        },
    ),
    "Grid": _props(
        ["columns"],
        {
            "columns": {"type": "integer", "minimum": 1, "maximum": 4},
            "style": {"type": "string"},
        },
    ),
    "List": _props(
        ["dataSource", "template"],
        {
            "dataSource": {
                "type": "object",
                "properties": {
                    "type": {"const": "inline"},
                    "data": {
                        "type": "array",
                        "items": LIST_ITEM_SCHEMA,
                    },
                },
                "required": ["type", "data"],
                "additionalProperties": False,
            },
            "template": {"type": "string", "enum": ["text", "title_text"]},
            "orientation": {"type": "string", "enum": ["vertical", "horizontal"]},
            "selectable": {"type": "boolean"},
        },
    ),
    "Markdown": _props(["text"], {"text": TEXT_LITERAL}),
    "Progress": _props(
        ["value", "maximum", "label"],
        {
            "value": {"type": "integer", "minimum": 0},
            "maximum": {"type": "integer", "minimum": 1},
            "label": TEXT_LITERAL,
            "show_label": {"type": "boolean"},
        },
    ),
    "SequenceDiagram": _props(
        ["participants", "messages"],
        {
            "participants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "label": {"type": "string", "minLength": 1},
                    },
                    "required": ["id", "label"],
                    "additionalProperties": False,
                },
                "minItems": 1,
            },
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string", "minLength": 1},
                        "to": {"type": "string", "minLength": 1},
                        "text": {"type": "string", "minLength": 1},
                        "type": {"type": "string", "enum": ["sync", "reply"]},
                    },
                    "required": ["from", "to", "text", "type"],
                    "additionalProperties": False,
                },
                "minItems": 1,
            },
            "title": {"type": "string"},
            "height": {"type": "integer", "minimum": 220, "maximum": 900},
        },
    ),
    "Tabs": _props(
        ["tabs"],
        {
            "tabs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "label": {"type": "string", "minLength": 1},
                    },
                    "required": ["id", "label"],
                    "additionalProperties": False,
                },
                "minItems": 1,
                "maxItems": 6,
            },
        },
    ),
    "Text": _props(["text"], {"text": TEXT_LITERAL}),
    "Title": _props(
        ["text", "level"],
        {
            "text": TEXT_LITERAL,
            "level": {"type": "integer", "minimum": 1, "maximum": 6},
        },
    ),
}


A2UI_COMPONENT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$defs": {
        "a2uiComponent": {
            "oneOf": [
                _component_schema(component, props)
                for component, props in sorted(COMPONENT_SCHEMAS.items())
            ]
        }
    },
    "$ref": "#/$defs/a2uiComponent",
}


A2UI_COMPONENT_EXAMPLES: dict[str, list[dict[str, Any]]] = {
    "Badge": [
        {
            "id": "badge_status",
            "component": {"Badge": {"text": lit("completed"), "variant": "success"}},
            "children": {"explicitList": []},
        },
        {
            "id": "badge_count",
            "component": {"Badge": {"text": lit("3 pending"), "variant": "info"}},
            "children": {"explicitList": []},
        },
    ],
    "Card": [
        {
            "id": "card_summary",
            "component": {"Card": {"variant": "outlined", "max_width": 500}},
            "children": {
                "explicitList": [
                    {
                        "id": "card_summary_title",
                        "component": {"Title": {"text": lit("Summary"), "level": 4}},
                        "children": {"explicitList": []},
                    },
                    {
                        "id": "card_summary_text",
                        "component": {
                            "Text": {"text": lit("Three resources are active and one is queued.")}
                        },
                        "children": {"explicitList": []},
                    },
                ]
            },
        },
        {
            "id": "card_note",
            "component": {"Card": {"variant": "flat", "padding": [12]}},
            "children": {
                "explicitList": [
                    {
                        "id": "card_note_body",
                        "component": {"Markdown": {"text": lit("**Note:** values are scoped to this chat.")}},
                        "children": {"explicitList": []},
                    }
                ]
            },
        },
    ],
    "Chart": [
        {
            "id": "chart_messages",
            "component": {
                "Chart": {
                    "chartType": "bar",
                    "data": [4, 8, 3],
                    "labels": ["User", "Assistant", "Tools"],
                    "title": "Message distribution",
                    "max_width": 500,
                    "max_height": 300,
                }
            },
            "children": {"explicitList": []},
        },
        {
            "id": "chart_trend",
            "component": {
                "Chart": {
                    "chartType": "line",
                    "data": [2, 5, 9, 7],
                    "labels": ["09:00", "10:00", "11:00", "12:00"],
                    "title": "Activity trend",
                    "max_width": 500,
                }
            },
            "children": {"explicitList": []},
        },
    ],
    "Collapsible": [
        {
            "id": "collapse_details",
            "component": {
                "Collapsible": {
                    "title": lit("Details"),
                    "content": lit("This section keeps secondary information collapsed until needed."),
                    "open": False,
                }
            },
            "children": {"explicitList": []},
        }
    ],
    "DataTable": [
        {
            "id": "table_resources",
            "component": {
                "DataTable": {
                    "model": [
                        {"id": "name", "field": "name", "label": "Name", "type": "text"},
                        {"id": "status", "field": "status", "label": "Status", "type": "badge"},
                        {"id": "count", "field": "count", "label": "Count", "type": "number"},
                    ],
                    "rows": [
                        {"id": "row_1", "name": "Messages", "status": "active", "count": 12},
                        {"id": "row_2", "name": "Attachments", "status": "pending", "count": 2},
                    ],
                    "paginated": False,
                    "pagination": False,
                }
            },
            "children": {"explicitList": []},
        }
    ],
    "Descriptions": [
        {
            "id": "details_thread",
            "component": {
                "Descriptions": {
                    "model": [
                        {"id": "title", "field": "title", "label": "Title", "type": "text"},
                        {"id": "messages", "field": "messages", "label": "Messages", "type": "number"},
                    ],
                    "data": {"title": "Current chat", "messages": 12},
                    "key_header": "Property",
                    "value_header": "Value",
                    "borders": True,
                }
            },
            "children": {"explicitList": []},
        }
    ],
    "Grid": [
        {
            "id": "grid_metrics",
            "component": {"Grid": {"columns": 3, "style": "max-width: 760px;"}},
            "children": {
                "explicitList": [
                    {
                        "id": "grid_metric_messages",
                        "component": {"Card": {"variant": "outlined", "padding": [12]}},
                        "children": {
                            "explicitList": [
                                {
                                    "id": "grid_metric_messages_label",
                                    "component": {"Text": {"text": lit("Messages")}},
                                    "children": {"explicitList": []},
                                },
                                {
                                    "id": "grid_metric_messages_value",
                                    "component": {"Title": {"text": lit("12"), "level": 3}},
                                    "children": {"explicitList": []},
                                },
                            ]
                        },
                    }
                ]
            },
        }
    ],
    "List": [
        {
            "id": "list_tasks",
            "component": {
                "List": {
                    "template": "title_text",
                    "orientation": "vertical",
                    "selectable": False,
                    "dataSource": {
                        "type": "inline",
                        "data": [
                            {"id": "task_1", "title": "Retrieve documents", "text": "Search extracted markdown."},
                            {"id": "task_2", "title": "Render summary", "text": "Show a concise result."},
                        ],
                    },
                }
            },
            "children": {"explicitList": []},
        },
        {
            "id": "list_labels",
            "component": {
                "List": {
                    "template": "text",
                    "dataSource": {
                        "type": "inline",
                        "data": [
                            {"id": "label_1", "title": "online"},
                            {"id": "label_2", "title": "queued"},
                        ],
                    },
                }
            },
            "children": {"explicitList": []},
        },
    ],
    "Markdown": [
        {
            "id": "markdown_answer",
            "component": {"Markdown": {"text": lit("### Result\n- First point\n- Second point")}},
            "children": {"explicitList": []},
        }
    ],
    "Progress": [
        {
            "id": "progress_ingestion",
            "component": {
                "Progress": {
                    "value": 65,
                    "maximum": 100,
                    "label": lit("Ingestion progress"),
                    "show_label": True,
                }
            },
            "children": {"explicitList": []},
        }
    ],
    "SequenceDiagram": [
        {
            "id": "sequence_retrieve",
            "component": {
                "SequenceDiagram": {
                    "title": "Retrieve flow",
                    "height": 420,
                    "participants": [
                        {"id": "user", "label": "User"},
                        {"id": "chat", "label": "Chat Agent"},
                        {"id": "knowledge", "label": "Knowledge"},
                    ],
                    "messages": [
                        {"from": "user", "to": "chat", "text": "Ask about attachment", "type": "sync"},
                        {"from": "chat", "to": "knowledge", "text": "search documents", "type": "sync"},
                        {"from": "knowledge", "to": "chat", "text": "matches", "type": "reply"},
                        {"from": "chat", "to": "user", "text": "answer", "type": "reply"},
                    ],
                }
            },
            "children": {"explicitList": []},
        }
    ],
    "Tabs": [
        {
            "id": "tabs_report",
            "component": {
                "Tabs": {
                    "tabs": [
                        {"id": "tab_summary", "label": "Summary"},
                        {"id": "tab_details", "label": "Details"},
                    ]
                }
            },
            "children": {
                "explicitList": [
                    {
                        "id": "tab_summary",
                        "component": {"Markdown": {"text": lit("Summary content.")}},
                        "children": {"explicitList": []},
                    },
                    {
                        "id": "tab_details",
                        "component": {"Markdown": {"text": lit("Detailed content.")}},
                        "children": {"explicitList": []},
                    },
                ]
            },
        }
    ],
    "Text": [
        {
            "id": "text_status",
            "component": {"Text": {"text": lit("The operation completed successfully.")}},
            "children": {"explicitList": []},
        }
    ],
    "Title": [
        {
            "id": "title_section",
            "component": {"Title": {"text": lit("Runtime statistics"), "level": 3}},
            "children": {"explicitList": []},
        }
    ],
}


class A2UIValidationError(ValueError):
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}" if path else message)


def validate_a2ui_component(component: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    payload = deepcopy(component)
    validator = Draft202012Validator(A2UI_COMPONENT_SCHEMA)
    error = next(validator.iter_errors(payload), None)
    if error is not None:
        raise _validation_error(error)
    _validate_component_tree(payload, "component")
    component_kind = _component_kind(payload)
    return component_kind, payload


def _validation_error(error: ValidationError) -> A2UIValidationError:
    leaf = _best_error(error)
    path = ".".join(str(item) for item in leaf.absolute_path)
    return A2UIValidationError(path or "component", leaf.message)


def _best_error(error: ValidationError) -> ValidationError:
    if not error.context:
        return error
    return max((_best_error(item) for item in error.context), key=lambda item: len(item.absolute_path))


def _component_kind(component: dict[str, Any]) -> str:
    component_map = component["component"]
    return next(iter(component_map.keys()))


def _component_props(component: dict[str, Any]) -> dict[str, Any]:
    return component["component"][_component_kind(component)]


def _validate_component_tree(component: dict[str, Any], path: str) -> None:
    kind = _component_kind(component)
    children = component["children"]["explicitList"]
    if kind not in CONTAINER_COMPONENTS and children:
        raise A2UIValidationError(
            f"{path}.children.explicitList",
            f"{kind} does not support nested children in the chat component tool",
        )
    if kind == "Chart":
        props = _component_props(component)
        if len(props["data"]) != len(props["labels"]):
            raise A2UIValidationError(
                f"{path}.component.Chart.labels",
                "labels length must match data length",
            )
    if kind == "Progress":
        props = _component_props(component)
        if int(props["value"]) > int(props["maximum"]):
            raise A2UIValidationError(
                f"{path}.component.Progress.value",
                "value must be lower than or equal to maximum",
            )
    if kind == "Tabs":
        props = _component_props(component)
        tab_ids = {str(item["id"]) for item in props["tabs"]}
        child_ids = {str(item["id"]) for item in children}
        missing = sorted(tab_ids - child_ids)
        if missing:
            raise A2UIValidationError(
                f"{path}.component.Tabs.tabs",
                f"tabs reference missing child ids: {', '.join(missing)}",
            )
    if kind == "SequenceDiagram":
        props = _component_props(component)
        participant_ids = {str(item["id"]) for item in props["participants"]}
        for index, message in enumerate(props["messages"]):
            if message["from"] not in participant_ids:
                raise A2UIValidationError(
                    f"{path}.component.SequenceDiagram.messages.{index}.from",
                    "message source must reference a participant id",
                )
            if message["to"] not in participant_ids:
                raise A2UIValidationError(
                    f"{path}.component.SequenceDiagram.messages.{index}.to",
                    "message target must reference a participant id",
                )
    for index, child in enumerate(children):
        _validate_component_tree(child, f"{path}.children.explicitList.{index}")


def chat_component_id(prefix: str = "a2ui") -> str:
    return f"chat_{prefix}_{uuid4().hex[:10]}"
