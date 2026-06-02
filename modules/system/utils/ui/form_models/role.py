from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


def _with_defaults(fields: list[dict[str, Any]], defaults: dict[str, Any]) -> list[dict[str, Any]]:
    if not defaults:
        return fields

    hydrated = deepcopy(fields)
    for field in hydrated:
        if field.get("type") == "row":
            for child in field.get("children") or []:
                name = str(child.get("name") or "")
                if name and name in defaults:
                    child["value"] = defaults[name]
            continue

        name = str(field.get("name") or "")
        if name and name in defaults:
            field["value"] = defaults[name]

    return hydrated


def build_role_form_model(
    t: Callable[[str], str],
    *,
    defaults: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = [
        {
            "name": "name",
            "label": t("system.role.form.name.label"),
            "type": "text",
            "placeholder": t("system.role.form.name.placeholder"),
            "validations": [
                {"rule": "required", "message": t("system.role.form.name.required")}
            ],
        },
        {
            "name": "description",
            "label": t("system.role.form.description.label"),
            "type": "text",
            "placeholder": t("system.role.form.description.placeholder"),
        },
    ]

    return _with_defaults(fields, defaults or {})


__all__ = ["build_role_form_model"]
