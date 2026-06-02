from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk as sdk


def _field(
    field_type: str,
    name: str,
    label: str,
    *,
    value: Any = "",
    required: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": field_type,
        "name": name,
        "label": label,
        "value": value,
    }
    if required:
        payload["validations"] = [{"rule": "required", "message": f"{label} is required"}]
    return payload


async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    subject_kind = str(route_params.get("subject_kind") or "").strip()
    subject = str(route_params.get("subject") or "").strip()
    name = str(route_params.get("name") or "").strip()
    rows = await sdk.environment.list_variables(
        subject_kind=subject_kind,
        subject=subject,
    )
    row = next(
        (
            dict(item)
            for item in rows
            if str(item.get("name") or "").strip().upper() == name.upper()
        ),
        {},
    )

    builder = sdk.ui.load("utils/ui/yaml/environment/value")
    title = builder.get_component("environment_value_title")
    if title is not None and row:
        title.set_property("text", str(row.get("label") or row.get("name") or name))

    form = builder.get_component("environment_value_form")
    if form is not None:
        configured = bool(row.get("configured"))
        form.set_property(
            "model",
            [
                _field(
                    "password",
                    "value",
                    sdk.i18n.t("system.environment.value.secret"),
                    value="",
                    required=not configured,
                ),
                _field(
                    "toggle",
                    "enabled",
                    sdk.i18n.t("system.environment.table.enabled"),
                    value=bool(row.get("enabled", True)),
                ),
            ],
        )
        form.set_property("values", {"value": "", "enabled": bool(row.get("enabled", True))})
        form.set_property(
            "params",
            {
                "subject_kind": subject_kind,
                "subject": subject,
                "name": name,
                "configured": configured,
            },
        )
    return builder
