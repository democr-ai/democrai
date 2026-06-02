from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from democrai.sdk.system import (
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_SUPER,
    ROLE_LEVEL_USER,
)


def user_role_options(module_sdk) -> list[dict[str, str]]:
    roles = module_sdk.models.roles.list(page=0, page_size=200, filters={}).get(
        "rows", []
    )
    return [
        {"label": str(role.get("name") or ""), "value": str(role.get("name") or "")}
        for role in roles
        if str(role.get("name") or "").strip()
    ]


def _with_defaults(
    fields: list[dict[str, Any]], defaults: dict[str, Any]
) -> list[dict[str, Any]]:
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


def build_user_form_model(
    role_options: list[dict[str, str]],
    *,
    t: Callable[[str], str],
    include_password: bool,
    defaults: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = [
        {
            "type": "row",
            "children": [
                {
                    "name": "username",
                    "label": t("system.user.form.username.label"),
                    "type": "text",
                    "placeholder": t("system.user.form.username.placeholder"),
                    "stretch": 1,
                    "validations": [
                        {
                            "rule": "required",
                            "message": t("system.user.form.username.required"),
                        },
                        {
                            "rule": "regex",
                            "pattern": "^[a-zA-Z0-9_.-]+$",
                            "message": t("system.user.form.username.regex"),
                        },
                    ],
                },
                {
                    "name": "email",
                    "label": t("system.user.form.email.label"),
                    "type": "email",
                    "placeholder": t("system.user.form.email.placeholder"),
                    "stretch": 1,
                    "validations": [
                        {
                            "rule": "regex",
                            "pattern": "^[^@]+@[^@]+\\.[^@]+$",
                            "message": t("system.user.form.email.regex"),
                        }
                    ],
                },
            ],
        },
        {
            "type": "row",
            "children": [
                {
                    "name": "role",
                    "label": t("system.user.form.role.label"),
                    "type": "select",
                    "stretch": 1,
                    "options": role_options,
                    "validations": [
                        {
                            "rule": "required",
                            "message": t("system.user.form.role.required"),
                        }
                    ],
                },
                {
                    "name": "access_level",
                    "label": t("system.user.form.access_level.label"),
                    "type": "select",
                    "stretch": 1,
                    "options": [
                        {
                            "label": t("system.user.form.access_level.super"),
                            "value": ROLE_LEVEL_SUPER,
                        },
                        {
                            "label": t("system.user.form.access_level.organization"),
                            "value": ROLE_LEVEL_ORGANIZATION,
                        },
                        {
                            "label": t("system.user.form.access_level.user"),
                            "value": ROLE_LEVEL_USER,
                        },
                    ],
                    "validations": [
                        {
                            "rule": "required",
                            "message": t("system.user.form.access_level.required"),
                        }
                    ],
                },
            ],
        },
    ]

    if include_password:
        fields.insert(
            1,
            {
                "type": "row",
                "children": [
                    {
                        "name": "password",
                        "label": t("system.user.form.password.label"),
                        "type": "password",
                        "placeholder": t("system.user.form.password.placeholder"),
                        "stretch": 1,
                        "validations": [
                            {
                                "rule": "required",
                                "message": t("system.user.form.password.required"),
                            },
                            {
                                "rule": "min_length",
                                "value": 8,
                                "message": t("system.user.form.password.min_length"),
                            },
                        ],
                    },
                    {
                        "name": "confirm_password",
                        "label": t("system.user.form.confirm_password.label"),
                        "type": "password",
                        "placeholder": t("system.user.form.confirm_password.placeholder"),
                        "stretch": 1,
                        "validations": [
                            {
                                "rule": "equals_field",
                                "field": "password",
                                "message": t("system.user.form.confirm_password.equals"),
                            }
                        ],
                    },
                ],
            },
        )

    return _with_defaults(fields, defaults or {})


__all__ = ["build_user_form_model", "user_role_options"]
