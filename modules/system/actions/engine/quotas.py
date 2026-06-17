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
from modules.system.utils.actions.engine.quotas import (
    quota_counter_rows,
    quota_limit_rows,
)


COUNTERS_TABLE_ID = "engine_quota_counters_table"
LIMITS_TABLE_ID = "engine_quota_limits_table"


class CounterFormPayload(BaseModel):
    name: str = Field(min_length=1)
    period_count: int = Field(ge=1)
    period_unit: str = Field(min_length=1)

    @field_validator("name", "period_unit")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value is required")
        return cleaned


class SaveCounterPayload(BaseModel):
    engine_quota_counter_form: CounterFormPayload


class UpdateCounterPayload(SaveCounterPayload):
    counter_id: int


class LimitFormPayload(BaseModel):
    counter_id: int
    engine_row_id: int | None = None
    scope_type: str | None = None
    metric_type: str = Field(min_length=1)
    limit_value: int = Field(ge=0)


class SaveLimitPayload(BaseModel):
    scope: str
    subject_id: int
    engine_quota_limit_form: LimitFormPayload


class UpdateLimitPayload(SaveLimitPayload):
    limit_id: int


class RowItemPayload(BaseModel):
    id: int
    subject_scope: str | None = None
    subject_id: int | None = None


class DeleteCounterPayload(BaseModel):
    item: RowItemPayload


class DeleteLimitPayload(BaseModel):
    item: RowItemPayload


def _toast(module_sdk, variant: str, title_key: str, text_key: str) -> dict[str, Any]:
    return module_sdk.effects.notify(
        "toast",
        {
            "title": module_sdk.i18n.t(title_key),
            "text": module_sdk.i18n.t(text_key),
            "variant": variant,
            "duration": 2600,
        },
    )


def _success(module_sdk, title_key: str, text_key: str, *effects: dict[str, Any]):
    return module_sdk.effects.respond(
        _toast(module_sdk, "success", title_key, text_key),
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
        *effects,
    )


def _error(module_sdk, title_key: str, text_key: str):
    return module_sdk.effects.respond(
        _toast(module_sdk, "destructive", title_key, text_key),
    )


def _counter_table_payload(module_sdk, ctx: dict[str, Any]) -> dict[str, Any]:
    page, page_size, filters, sort = datatable_remote_request(ctx)
    listing = module_sdk.engines.list_quota_counters(
        page=page,
        page_size=page_size,
        filters=filters,
        sort=sort,
    )
    rows = quota_counter_rows(module_sdk, rows=list((listing or {}).get("rows") or []))
    return datatable_payload(
        {**(listing or {}), "rows": rows},
        page=page,
        page_size=page_size,
        filters=filters,
        sort=sort,
    )


def _limit_listing(
    module_sdk,
    *,
    scope: str,
    subject_id: int,
    page: int,
    page_size: int,
):
    if scope == "global":
        return module_sdk.engines.list_engine_global_quota_limits(
            engine_registry_id=subject_id,
            page=page,
            page_size=page_size,
        )
    if scope == "organization":
        return module_sdk.engines.list_organization_engine_quota_limits(
            organization_id=subject_id,
            page=page,
            page_size=page_size,
        )
    if scope == "role":
        return module_sdk.engines.list_role_engine_quota_limits(
            role_id=subject_id,
            page=page,
            page_size=page_size,
        )
    if scope == "user":
        return module_sdk.engines.list_user_engine_quota_limits(
            user_id=subject_id,
            page=page,
            page_size=page_size,
        )
    raise ValueError("unsupported quota scope")


def _limit_table_payload(module_sdk, ctx: dict[str, Any]) -> dict[str, Any]:
    page, page_size, filters, sort = datatable_remote_request(ctx)
    scope = str(ctx.get("scope") or "").strip()
    subject_id = int(ctx.get("subject_id") or 0)
    listing = _limit_listing(
        module_sdk,
        scope=scope,
        subject_id=subject_id,
        page=page,
        page_size=page_size,
    )
    rows = quota_limit_rows(
        module_sdk,
        rows=list((listing or {}).get("rows") or []),
        subject_scope=scope,
        subject_id=subject_id,
    )
    return datatable_payload(
        {**(listing or {}), "rows": rows},
        page=page,
        page_size=page_size,
        filters=filters,
        sort=sort,
    )


@action("list_engine_quota_counters")
@permission_required(["system.engine.manage"])
async def list_engine_quota_counters(ctx: dict[str, Any], session: dict, module_sdk):
    payload = _counter_table_payload(module_sdk, ctx)
    return module_sdk.effects.respond(
        *datatable_update_effects(module_sdk, COUNTERS_TABLE_ID, payload)
    )


@action("list_engine_quota_limits")
@permission_required(["system.engine.manage"])
async def list_engine_quota_limits(ctx: dict[str, Any], session: dict, module_sdk):
    payload = _limit_table_payload(module_sdk, ctx)
    return module_sdk.effects.respond(
        *datatable_update_effects(module_sdk, LIMITS_TABLE_ID, payload)
    )


@action("create_engine_quota_counter")
@validate(SaveCounterPayload, strip_extra=True)
@permission_required(["system.engine.manage"])
async def create_engine_quota_counter(ctx: dict[str, Any], session: dict, module_sdk):
    try:
        module_sdk.engines.create_quota_counter(ctx["engine_quota_counter_form"])
    except Exception as exc:
        module_sdk.system.log(f"[system.engine.quotas] create counter failed: {exc}", "error")
        return _error(
            module_sdk,
            "system.engine.quotas.toast.counter_error.title",
            "system.engine.quotas.toast.counter_error.text",
        )
    return _success(
        module_sdk,
        "system.engine.quotas.toast.counter_saved.title",
        "system.engine.quotas.toast.counter_saved.text",
        *datatable_update_effects(
            module_sdk,
            COUNTERS_TABLE_ID,
            _counter_table_payload(module_sdk, {"page": 0, "pageSize": 25}),
        ),
    )


@action("update_engine_quota_counter")
@validate(UpdateCounterPayload, strip_extra=True)
@permission_required(["system.engine.manage"])
async def update_engine_quota_counter(ctx: dict[str, Any], session: dict, module_sdk):
    try:
        module_sdk.engines.update_quota_counter(
            counter_id=ctx["counter_id"],
            payload=ctx["engine_quota_counter_form"],
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.engine.quotas] update counter failed: {exc}", "error")
        return _error(
            module_sdk,
            "system.engine.quotas.toast.counter_error.title",
            "system.engine.quotas.toast.counter_error.text",
        )
    return _success(
        module_sdk,
        "system.engine.quotas.toast.counter_saved.title",
        "system.engine.quotas.toast.counter_saved.text",
        *datatable_update_effects(
            module_sdk,
            COUNTERS_TABLE_ID,
            _counter_table_payload(module_sdk, {"page": 0, "pageSize": 25}),
        ),
    )


@action("delete_engine_quota_counter")
@validate(DeleteCounterPayload, strip_extra=True)
@permission_required(["system.engine.manage"])
async def delete_engine_quota_counter(ctx: dict[str, Any], session: dict, module_sdk):
    try:
        module_sdk.engines.delete_quota_counter(counter_id=ctx["item"]["id"])
    except Exception as exc:
        module_sdk.system.log(f"[system.engine.quotas] delete counter failed: {exc}", "error")
        return _error(
            module_sdk,
            "system.engine.quotas.toast.counter_delete_error.title",
            "system.engine.quotas.toast.counter_delete_error.text",
        )
    return module_sdk.effects.respond(
        _toast(
            module_sdk,
            "success",
            "system.engine.quotas.toast.counter_deleted.title",
            "system.engine.quotas.toast.counter_deleted.text",
        ),
        *datatable_update_effects(
            module_sdk,
            COUNTERS_TABLE_ID,
            _counter_table_payload(module_sdk, {"page": 0, "pageSize": 25}),
        ),
    )


@action("create_engine_quota_limit")
@validate(SaveLimitPayload, strip_extra=True)
@permission_required(["system.engine.manage"])
async def create_engine_quota_limit(ctx: dict[str, Any], session: dict, module_sdk):
    try:
        _create_limit(module_sdk, ctx)
    except Exception as exc:
        module_sdk.system.log(f"[system.engine.quotas] create limit failed: {exc}", "error")
        return _error(
            module_sdk,
            "system.engine.quotas.toast.limit_error.title",
            "system.engine.quotas.toast.limit_error.text",
        )
    return _success(
        module_sdk,
        "system.engine.quotas.toast.limit_saved.title",
        "system.engine.quotas.toast.limit_saved.text",
        *datatable_update_effects(
            module_sdk,
            LIMITS_TABLE_ID,
            _limit_table_payload(
                module_sdk,
                {
                    "scope": ctx["scope"],
                    "subject_id": ctx["subject_id"],
                    "page": 0,
                    "pageSize": 25,
                },
            ),
        ),
    )


@action("update_engine_quota_limit")
@validate(UpdateLimitPayload, strip_extra=True)
@permission_required(["system.engine.manage"])
async def update_engine_quota_limit(ctx: dict[str, Any], session: dict, module_sdk):
    try:
        _update_limit(module_sdk, ctx)
    except Exception as exc:
        module_sdk.system.log(f"[system.engine.quotas] update limit failed: {exc}", "error")
        return _error(
            module_sdk,
            "system.engine.quotas.toast.limit_error.title",
            "system.engine.quotas.toast.limit_error.text",
        )
    return _success(
        module_sdk,
        "system.engine.quotas.toast.limit_saved.title",
        "system.engine.quotas.toast.limit_saved.text",
        *datatable_update_effects(
            module_sdk,
            LIMITS_TABLE_ID,
            _limit_table_payload(
                module_sdk,
                {
                    "scope": ctx["scope"],
                    "subject_id": ctx["subject_id"],
                    "page": 0,
                    "pageSize": 25,
                },
            ),
        ),
    )


@action("delete_engine_quota_limit")
@validate(DeleteLimitPayload, strip_extra=True)
@permission_required(["system.engine.manage"])
async def delete_engine_quota_limit(ctx: dict[str, Any], session: dict, module_sdk):
    item = dict(ctx["item"])
    try:
        module_sdk.engines.delete_engine_quota_limit(limit_id=item["id"])
    except Exception as exc:
        module_sdk.system.log(f"[system.engine.quotas] delete limit failed: {exc}", "error")
        return _error(
            module_sdk,
            "system.engine.quotas.toast.limit_delete_error.title",
            "system.engine.quotas.toast.limit_delete_error.text",
        )
    return module_sdk.effects.respond(
        _toast(
            module_sdk,
            "success",
            "system.engine.quotas.toast.limit_deleted.title",
            "system.engine.quotas.toast.limit_deleted.text",
        ),
        *datatable_update_effects(
            module_sdk,
            LIMITS_TABLE_ID,
            _limit_table_payload(
                module_sdk,
                {
                    "scope": item.get("subject_scope"),
                    "subject_id": item.get("subject_id"),
                    "page": 0,
                    "pageSize": 25,
                },
            ),
        ),
    )


def _create_limit(module_sdk, ctx: dict[str, Any]) -> None:
    scope = str(ctx["scope"]).strip()
    subject_id = int(ctx["subject_id"])
    payload = dict(ctx["engine_quota_limit_form"])
    if scope == "global":
        module_sdk.engines.create_engine_global_quota_limit(
            engine_registry_id=subject_id,
            payload=payload,
        )
        return
    if scope == "organization":
        module_sdk.engines.create_organization_engine_quota_limit(
            organization_id=subject_id,
            payload=payload,
        )
        return
    if scope == "role":
        module_sdk.engines.create_role_engine_quota_limit(
            role_id=subject_id,
            payload=payload,
        )
        return
    if scope == "user":
        module_sdk.engines.create_user_engine_quota_limit(
            user_id=subject_id,
            payload=payload,
        )
        return
    raise ValueError("unsupported quota scope")


def _update_limit(module_sdk, ctx: dict[str, Any]) -> None:
    scope = str(ctx["scope"]).strip()
    subject_id = int(ctx["subject_id"])
    limit_id = int(ctx["limit_id"])
    payload = dict(ctx["engine_quota_limit_form"])
    if scope == "global":
        module_sdk.engines.update_engine_global_quota_limit(
            engine_registry_id=subject_id,
            limit_id=limit_id,
            payload=payload,
        )
        return
    if scope == "organization":
        module_sdk.engines.update_organization_engine_quota_limit(
            organization_id=subject_id,
            limit_id=limit_id,
            payload=payload,
        )
        return
    if scope == "role":
        module_sdk.engines.update_role_engine_quota_limit(
            role_id=subject_id,
            limit_id=limit_id,
            payload=payload,
        )
        return
    if scope == "user":
        module_sdk.engines.update_user_engine_quota_limit(
            user_id=subject_id,
            limit_id=limit_id,
            payload=payload,
        )
        return
    raise ValueError("unsupported quota scope")
