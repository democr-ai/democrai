from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action, validate

from modules.system.utils.actions.datatable import (
    datatable_payload,
    datatable_remote_request,
    datatable_update_effects,
)


TABLE_ID = "environment_variable_table"


class EnvironmentValueFormPayload(BaseModel):
    value: str = ""
    enabled: bool = True


class SaveEnvironmentVariablePayload(BaseModel):
    subject_kind: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    name: str = Field(min_length=1)
    configured: bool
    environment_value_form: EnvironmentValueFormPayload

    @field_validator("subject_kind", "subject", "name")
    @classmethod
    def _clean_route_value(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("route value is required")
        return cleaned


class EnvironmentRowItemPayload(BaseModel):
    id: int


class DeleteEnvironmentVariablePayload(BaseModel):
    item: EnvironmentRowItemPayload


def _toast(module_sdk, variant: str, title: str, text: str) -> dict[str, Any]:
    return module_sdk.effects.notify(
        "toast",
        {
            "title": title,
            "variant": variant,
            "text": text,
            "duration": 2400,
        },
    )


async def _table_effects(module_sdk, ctx: dict[str, Any]):
    page, page_size, filters, sort = datatable_remote_request(ctx)
    listing = module_sdk.models.environment_variable_registry.list(
        page=page,
        page_size=page_size,
        filters=filters,
        sort=sort,
    )
    payload = datatable_payload(
        listing,
        page=page,
        page_size=page_size,
        filters=filters,
        sort=sort,
    )
    return datatable_update_effects(module_sdk, TABLE_ID, payload)


@action("list_environment_variables")
@permission_required(["system.environment.list"])
async def list_environment_variables(ctx: dict[str, Any], session: dict, module_sdk):
    return module_sdk.effects.respond(*(await _table_effects(module_sdk, ctx)))


@action("save_environment_variable")
@validate(SaveEnvironmentVariablePayload, strip_extra=True)
@permission_required(["system.environment.manage"])
async def save_environment_variable(ctx: dict[str, Any], session: dict, module_sdk):
    payload = ctx["environment_value_form"]
    value = payload["value"]
    configured = ctx["configured"]
    if not value and not configured:
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                module_sdk.i18n.t("system.environment.toast.missing_value.title"),
                module_sdk.i18n.t("system.environment.toast.missing_value.text"),
            )
        )
    try:
        await module_sdk.environment.set_value(
            subject_kind=ctx["subject_kind"],
            subject=ctx["subject"],
            name=ctx["name"],
            value=value if value else None,
            enabled=payload["enabled"],
        )
    except Exception as exc:
        module_sdk.system.log(
            f"Unable to save environment variable: {type(exc).__name__}: {exc}",
            "error",
        )
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                module_sdk.i18n.t("system.environment.toast.save_error.title"),
                module_sdk.i18n.t("system.environment.toast.save_error.text"),
            )
        )

    return module_sdk.effects.respond(
        _toast(
            module_sdk,
            "success",
            module_sdk.i18n.t("system.environment.toast.saved.title"),
            module_sdk.i18n.t("system.environment.toast.saved.text"),
        ),
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
        module_sdk.effects.render(),
    )


@action("delete_environment_variable")
@validate(DeleteEnvironmentVariablePayload, strip_extra=True)
@permission_required(["system.environment.manage"])
async def delete_environment_variable(ctx: dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    try:
        await module_sdk.environment.delete_value(variable_id=item["id"])
    except Exception:
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                module_sdk.i18n.t("system.environment.toast.delete_error.title"),
                module_sdk.i18n.t("system.environment.toast.delete_error.text"),
            )
        )

    return module_sdk.effects.respond(
        _toast(
            module_sdk,
            "success",
            module_sdk.i18n.t("system.environment.toast.deleted.title"),
            module_sdk.i18n.t("system.environment.toast.deleted.text"),
        ),
        module_sdk.effects.render(),
    )
