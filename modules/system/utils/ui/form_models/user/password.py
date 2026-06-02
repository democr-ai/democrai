from __future__ import annotations

from typing import Callable

def build_password_form_model(t: Callable[[str], str]) -> list[dict]:
    return [
        {
            "name": "new_password",
            "label": t("system.user.password.new.label"),
            "type": "password",
            "placeholder": t("system.user.password.new.placeholder"),
            "validations": [
                {"rule": "required", "message": t("system.user.password.new.required")},
                {
                    "rule": "min_length",
                    "value": 8,
                    "message": t("system.user.password.new.min_length"),
                },
            ],
        },
        {
            "name": "confirm_password",
            "label": t("system.user.password.confirm.label"),
            "type": "password",
            "placeholder": t("system.user.password.confirm.placeholder"),
            "validations": [
                {"rule": "required", "message": t("system.user.password.confirm.required")},
                {
                    "rule": "equals_field",
                    "field": "new_password",
                    "message": t("system.user.password.confirm.equals"),
                },
            ],
        },
    ]


__all__ = ["build_password_form_model"]
