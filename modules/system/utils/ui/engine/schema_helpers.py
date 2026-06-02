from __future__ import annotations

from typing import Any


def _json_type_to_form_type(prop: dict[str, Any]) -> str:
    fmt = str(prop.get("format") or "").strip().lower()
    if fmt == "file":
        return "file"
    json_type = str(prop.get("type") or "string").strip().lower()
    if json_type in ("integer", "number"):
        return "number"
    if json_type == "boolean":
        return "checkbox"
    if json_type == "array":
        return "text"
    return "text"


def schema_to_form_model(
    schema: dict[str, Any],
    *,
    initial_values: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert a flat JSON Schema to an SDUI Form model list.

    Supports types: string, integer, number, boolean, array, and format=file.
    Does not recurse into nested objects — callers must ensure schemas are flat.
    """
    properties = dict(schema.get("properties") or {})
    required = set(schema.get("required") or [])
    order: list[str] = list(schema.get("propertyOrder") or properties.keys())
    values = dict(initial_values or {})

    fields: list[dict[str, Any]] = []
    for name in order:
        if name not in properties:
            continue
        prop = dict(properties[name])
        field: dict[str, Any] = {
            "name": name,
            "label": str(prop.get("title") or name),
            "type": _json_type_to_form_type(prop),
        }
        description = str(prop.get("description") or "").strip()
        if description:
            field["placeholder"] = description
        if name in required:
            field["validations"] = [{"rule": "required"}]
        if name in values and values[name] is not None:
            field["value"] = values[name]
        fields.append(field)
    return fields
