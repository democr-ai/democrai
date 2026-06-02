from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


def build_organization_form_model(
    t: Callable[[str], str],
    *,
    defaults: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = [
        {
            "name": "name",
            "label": t("system.organization.form.name.label"),
            "type": "text",
            "placeholder": t("system.organization.form.name.placeholder"),
            "validations": [
                {
                    "rule": "required",
                    "message": t("system.organization.form.name.required"),
                }
            ],
        },
        {
            "name": "description",
            "label": t("system.organization.form.description.label"),
            "type": "textarea",
            "placeholder": t("system.organization.form.description.placeholder"),
        },
    ]
    if not defaults:
        return fields

    hydrated = deepcopy(fields)
    for field in hydrated:
        name = str(field.get("name") or "")
        if name and name in defaults:
            field["value"] = defaults[name]
    return hydrated
